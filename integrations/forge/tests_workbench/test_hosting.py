from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from wsgiref.util import setup_testing_defaults

from forge_data.workbench import ForgeWorkspace
from test_workbench import fixture
from trainlab.production import ProductionApp, create_credentials


class HostingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        auth = self.root / "users.json"
        create_credentials(auth, "operator", "long-fixture-password")
        (self.root / "recipes").mkdir()
        self.app = ProductionApp(
            self.root / "runs",
            self.root / "recipes",
            auth_file=auth,
            public_origin="https://lab.example.com",
            forge_workspace=self.root / "forge",
        )
        self.addCleanup(self.app.close)

    def request(self, path, payload=None, *, authenticate=True, token=None, origin=None):
        env = {}
        setup_testing_defaults(env)
        env.update(
            PATH_INFO=path,
            REQUEST_METHOD="GET" if payload is None else "POST",
            HTTP_HOST="lab.example.com",
        )
        if authenticate:
            env["HTTP_AUTHORIZATION"] = (
                "Basic " + base64.b64encode(b"operator:long-fixture-password").decode()
            )
        body = b"" if payload is None else json.dumps(payload).encode()
        env.update(
            CONTENT_LENGTH=str(len(body)),
            CONTENT_TYPE="application/json",
            **{"wsgi.input": io.BytesIO(body)},
        )
        if token:
            env["HTTP_X_TRAINLAB_TOKEN"] = token
        if origin:
            env["HTTP_ORIGIN"] = origin
        statuses = []
        data = b"".join(
            self.app(env, lambda status, headers: statuses.append(int(status.split()[0])))
        )
        return statuses[0], data

    def test_authentication_covers_both_workbenches(self):
        for path in (
            "/forge/",
            "/forge/app.js",
            "/forge/style.css",
            "/forge/shared.css",
            "/api/forge/state",
            "/",
        ):
            self.assertEqual(self.request(path, authenticate=False)[0], 401, path)
        status, body = self.request("/api/state")
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(body)["forge_enabled"])
        self.assertEqual(self.request("/forge/")[0], 200)

    def test_forge_upload_larger_than_trainlab_command_body_is_allowed_with_its_token(self):
        payload = fixture()
        self.assertGreater(len(json.dumps(payload)), 4096)
        token = json.loads(self.request("/api/forge/state")[1])["token"]
        self.assertEqual(self.request("/api/forge/releases", payload, token=token)[0], 202)
        self.app.workspace.forge.active.result(timeout=10)
        core_token = json.loads(self.request("/api/state")[1])["token"]
        self.assertEqual(
            self.request("/api/run", {"experiment": "x" * 5000}, token=core_token)[0], 400
        )

    def test_csrf_and_origin_controls_apply_to_uploads(self):
        token = json.loads(self.request("/api/forge/state")[1])["token"]
        self.assertEqual(self.request("/api/forge/releases", fixture())[0], 403)
        self.assertEqual(
            self.request(
                "/api/forge/releases", fixture(), token=token, origin="https://evil.example"
            )[0],
            403,
        )
        self.assertEqual(self.request("/api/forge/releases", fixture(), token="wrong")[0], 403)

    def test_combined_health_is_aggregate_and_contains_no_session_or_source_rows(self):
        status, body = self.request("/healthz", authenticate=False)
        self.assertEqual(status, 200)
        value = json.loads(body)
        self.assertEqual(value["forge"]["datasets"], 0)
        self.assertNotIn(b"token", body)
        self.assertNotIn(b"operator", body)
        self.assertNotIn(b"source_jsonl", body)

    def test_standalone_forge_uses_same_auth_adapter_and_its_own_root_page(self):
        app = ProductionApp(
            self.root / "standalone",
            None,
            auth_file=self.root / "users.json",
            public_origin="https://lab.example.com",
            workspace_factory=ForgeWorkspace,
        )
        self.addCleanup(app.close)
        previous = self.app
        self.app = app
        try:
            self.assertEqual(self.request("/", authenticate=False)[0], 401)
            status, body = self.request("/")
            self.assertEqual(status, 200)
            self.assertIn(b"Forge \xc2\xb7 Dataset workspace", body)
            self.assertIsNone(json.loads(self.request("/api/forge/state")[1])["trainlab_url"])
        finally:
            self.app = previous


if __name__ == "__main__":
    unittest.main()
