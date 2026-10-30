from __future__ import annotations

import http.client
import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from trainlab.runner import run_experiment
from trainlab.server import Dashboard


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        (self.root / "data.txt").write_text("constructed")
        (self.root / "train.py").write_text(
            "import os,json,time; from pathlib import Path; time.sleep(0.1); "
            "p=Path(os.environ['TRAINLAB_OUTPUT_DIR']); "
            "(p/'metrics.json').write_text(json.dumps({'loss':0.5})); (p/'model.json').write_text('{}')"
        )
        self.config = {"schema":"trainlab.experiment.v1", "name":"Constructed HTTP test", "description":"Fixture only", "command":[sys.executable,"train.py"], "seed":7, "timeout_seconds":5, "source_kind":"CONSTRUCTED", "split_identity":"fixture", "inputs":["data.txt","train.py"], "artifacts":["model.json"], "metrics":{"loss":"min"}, "budget":{"updates":1}}
        (self.root / "recipe.json").write_text(json.dumps(self.config))
        self.server = Dashboard(self.root / "runs", self.root, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=5)
        self.server.server_close()

    def request(self, path, method="GET", body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        self.addCleanup(connection.close)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()

    def test_dashboard_static_routes_and_no_directory_access(self):
        for path in ("/", "/style.css", "/app.js"):
            status, headers, data = self.request(path)
            self.assertEqual(status, 200)
            self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
            self.assertTrue(data)
        self.assertEqual(self.request('/../../data.txt')[0], 404)
        self.assertEqual(self.request('/runs')[0], 404)

    def test_cross_origin_and_rebinding_requests_rejected(self):
        for headers in ({'Host':'evil.example'}, {'Origin':'https://evil.example'}):
            self.assertEqual(self.request('/api/state', headers=headers)[0], 403)
        self.assertEqual(self.request('/api/run', 'POST', '{}', {'Content-Type':'application/json'})[0], 403)

    def test_registered_launch_and_comparison(self):
        body = json.loads(self.request('/api/state')[2])
        self.assertEqual(len(body['experiments']), 1)
        headers={'Content-Type':'application/json', 'X-TrainLab-Token':body['token']}
        self.assertEqual(self.request('/api/run', 'POST', json.dumps({'experiment':'recipe.json'}), headers)[0], 202)
        self.assertEqual(self.request('/api/run', 'POST', json.dumps({'experiment':'recipe.json'}), headers)[0], 409)
        self.server.active.result(timeout=5)
        run = json.loads(self.request('/api/state')[2])['runs'][0]
        self.assertEqual(run['status'], 'succeeded')
        status, _, payload = self.request('/api/verify?id='+run['id'])
        self.assertEqual(status,200)
        self.assertTrue(json.loads(payload)['valid'])
        second=run_experiment(self.root/'recipe.json', self.root/'runs')
        status,_,payload=self.request('/api/compare?id='+run['id']+'&id='+second['id'])
        self.assertEqual(status,200)
        self.assertTrue(json.loads(payload)['matched_declared_conditions'])
        self.assertEqual(self.request('/api/log?id='+run['id']+'&name=../data.txt')[0],400)
        self.assertEqual(self.request('/api/log?id='+run['id']+'&name=stdout.log')[0],200)

    def test_unknown_recipes_and_browser_commands_rejected(self):
        token=json.loads(self.request('/api/state')[2])['token']
        headers={'Content-Type':'application/json','X-TrainLab-Token':token}
        for payload in ({'experiment':'../recipe.json'}, {'experiment':'recipe.json','command':['echo','hello']}, {'experiment':['recipe.json']}):
            self.assertEqual(self.request('/api/run','POST',json.dumps(payload),headers)[0],400)

    def test_invalid_saved_records_do_not_break_workspace(self):
        path=self.root/'runs'/'broken'
        path.mkdir(parents=True)
        (path/'run.json').write_text('{"schema":"trainlab.run.v1","id":"broken"}')
        state=json.loads(self.request('/api/state')[2])
        self.assertEqual(state['runs'],[])

    def test_start_failure_visible_in_state(self):
        (self.root/'data.txt').unlink()
        token=json.loads(self.request('/api/state')[2])['token']
        self.request('/api/run','POST',json.dumps({'experiment':'recipe.json'}),{'Content-Type':'application/json','X-TrainLab-Token':token})
        with self.assertRaises(ValueError): self.server.active.result(timeout=5)
        state=json.loads(self.request('/api/state')[2])
        self.assertIn('could not start',state['job_error'])


if __name__ == '__main__':
    unittest.main()
