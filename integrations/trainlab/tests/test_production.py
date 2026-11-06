from __future__ import annotations

import base64
import io
import json
import tempfile
import unittest
from pathlib import Path
from wsgiref.util import setup_testing_defaults

from trainlab.production import ProductionApp, create_credentials
from trainlab.runner import LabError


class ProductionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = self.root / "users.json"
        create_credentials(self.auth, "operator", "a-long-test-password")
        self.app = ProductionApp(
            self.root / "runs", None, auth_file=self.auth, public_origin="https://lab.example.com"
        )
        self.addCleanup(self.app.close)

    def request(
        self, path, *, auth=None, method="GET", body=b"", origin=None, host="lab.example.com"
    ):
        env = {}
        setup_testing_defaults(env)
        env.update(
            PATH_INFO=path,
            REQUEST_METHOD=method,
            HTTP_HOST=host,
            CONTENT_LENGTH=str(len(body)),
            CONTENT_TYPE="application/json",
            **{"wsgi.input": io.BytesIO(body)},
        )
        if auth is not None:
            env["HTTP_AUTHORIZATION"] = "Basic " + base64.b64encode(auth.encode()).decode()
        if origin is not None:
            env["HTTP_ORIGIN"] = origin
        status = []
        headers = []
        data = b"".join(self.app(env, lambda s, h: (status.append(s), headers.extend(h))))
        return int(status[0].split()[0]), dict(headers), data

    def test_auth_covers_static_and_api_routes_without_credential_disclosure(self):
        for path in ("/", "/app.js", "/api/state", "/api/verify"):
            status, headers, data = self.request(path)
            self.assertEqual(status, 401)
            self.assertIn("Basic", headers["WWW-Authenticate"])
            self.assertNotIn(b"token", data)
        self.assertEqual(self.request("/api/state", auth="operator:wrong-password")[0], 401)
        status, _, data = self.request("/api/state", auth="operator:a-long-test-password")
        self.assertEqual(status, 200)
        self.assertIn("token", json.loads(data))
        self.assertNotIn(b"password", data)

    def test_host_origin_and_csrf_boundaries_survive_authentication(self):
        auth = "operator:a-long-test-password"
        self.assertEqual(self.request("/api/state", auth=auth, host="evil.example")[0], 403)
        self.assertEqual(
            self.request("/api/state", auth=auth, origin="https://evil.example")[0], 403
        )
        self.assertEqual(
            self.request(
                "/api/run", auth=auth, method="POST", body=b"{}", origin="https://lab.example.com"
            )[0],
            403,
        )

    def test_public_configuration_fails_closed(self):
        for kwargs in (
            {"auth_file": None, "public_origin": "https://lab.example.com"},
            {"auth_file": self.auth, "public_origin": "http://lab.example.com"},
            {"auth_file": self.auth, "public_origin": "https://user:secret@lab.example.com"},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(LabError):
                ProductionApp(self.root / "other", None, **kwargs)

    def test_aggregate_health_is_available_without_experiment_metadata(self):
        status, _, data = self.request("/healthz", host="127.0.0.1:8765")
        self.assertEqual(status, 200)
        self.assertNotIn(b"token", data)
        self.assertNotIn(b"experiments", data)

    def test_credentials_are_hashed_private_and_never_overwritten(self):
        raw = self.auth.read_text()
        self.assertNotIn("a-long-test-password", raw)
        with self.assertRaises(LabError):
            create_credentials(self.auth, "operator", "another-long-password")
        with self.assertRaises(LabError):
            create_credentials(self.root / "short.json", "operator", "short")
        if __import__("os").name == "posix":
            self.assertEqual(self.auth.stat().st_mode & 0o777, 0o600)
