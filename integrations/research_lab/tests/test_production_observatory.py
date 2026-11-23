"""The hosted observatory must protect evidence and report database failure."""

import base64
import contextlib
import importlib.util
import io
import json
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from research_lab.__main__ import main
from research_lab.server import LabWorkspace
from trainlab.production import ProductionApp, create_credentials


class ObservatoryProductionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.workspace = LabWorkspace(self.root / "lab")
        self.addCleanup(self.workspace.close)
        self.workspace.lab.program("private-research-name", "private objective", 60, 0)

    def test_health_covers_database_without_disclosing_research(self):
        status, body, _ = self.workspace.dispatch("GET", "/healthz", {})
        self.assertEqual(status, 200)
        self.assertEqual(body["research_database"]["status"], "ok")
        self.assertNotIn("private-research-name", json.dumps(body))
        self.assertNotIn("private objective", json.dumps(body))
        self.assertNotIn(str(self.root), json.dumps(body))

    def test_missing_database_is_unhealthy_and_is_not_recreated(self):
        self.workspace.lab.db_path.unlink()
        status, body, _ = self.workspace.dispatch("GET", "/healthz", {})
        self.assertEqual(status, 503)
        self.assertEqual(body["status"], "degraded")
        self.assertFalse(self.workspace.lab.db_path.exists())

    def test_corruption_degrades_health_and_returns_a_controlled_api_failure(self):
        self.workspace.lab.db_path.write_bytes(b"corrupt database private contents")
        status, body, _ = self.workspace.dispatch("GET", "/healthz", {})
        self.assertEqual(status, 503)
        self.assertEqual(body["research_database"]["status"], "degraded")
        status, body, _ = self.workspace.dispatch("GET", "/api/lab/state", {})
        self.assertEqual(status, 503)
        self.assertNotIn("private", json.dumps(body))
        self.assertNotIn(str(self.root), json.dumps(body))

    def test_missing_required_table_is_not_a_healthy_empty_lab(self):
        from research_lab.core import Controller

        for table in ("tasks", "nodes", "worker_activity", "attempts"):
            with self.subTest(table=table):
                with self.workspace.lab.connect() as database:
                    database.execute("DROP TABLE " + table)
                self.assertEqual(self.workspace.dispatch("GET", "/healthz", {})[0], 503)
                Controller(self.workspace.lab.root)

    def test_missing_required_column_is_unhealthy(self):
        with self.workspace.lab.connect() as database:
            database.execute("ALTER TABLE programs RENAME COLUMN objective TO missing_objective")
        self.assertEqual(self.workspace.dispatch("GET", "/healthz", {})[0], 503)

    def test_cli_database_errors_are_controlled(self):
        self.workspace.lab.db_path.write_bytes(b"corrupt database")
        errors = io.StringIO()
        with contextlib.redirect_stderr(errors):
            result = main(["--root", str(self.workspace.lab.root), "status"])
        self.assertEqual(result, 1)
        self.assertNotIn("Traceback", errors.getvalue())

    def test_local_mode_rejects_unapplied_remote_security_options(self):
        for options in (
            ["--host", "0.0.0.0"],
            ["--auth-file", "credentials.json"],
            ["--public-origin", "https://lab.example.test"],
        ):
            with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(main([
                    "--root", str(self.workspace.lab.root), "serve", *options
                ]), 1)

    def test_production_startup_never_recreates_or_repairs_missing_research(self):
        credentials = self.root / "startup-operator.json"
        create_credentials(credentials, "operator", "constructed-password-123")
        missing_root = self.root / "absent-lab"
        with contextlib.redirect_stderr(io.StringIO()):
            result = main(["--root", str(missing_root), "serve", "--production",
                           "--auth-file", str(credentials)])
        self.assertEqual(result, 1)
        self.assertFalse(missing_root.exists())
        with self.workspace.lab.connect() as database:
            database.execute("DROP TABLE nodes")
        with contextlib.redirect_stderr(io.StringIO()):
            result = main(["--root", str(self.workspace.lab.root), "serve", "--production",
                           "--auth-file", str(credentials)])
        self.assertEqual(result, 1)
        with self.workspace.lab.connect() as database:
            self.assertIsNone(database.execute(
                "SELECT name FROM sqlite_master WHERE name='nodes'"
            ).fetchone())

    def test_shared_production_boundary_and_read_only_routes(self):
        credentials = self.root / "operator.json"
        create_credentials(credentials, "operator", "constructed-password-123")
        application = ProductionApp(
            self.workspace.lab.root,
            None,
            auth_file=credentials,
            public_origin="https://lab.example.test",
            workspace_factory=LabWorkspace,
        )
        self.addCleanup(application.close)
        authorization = "Basic " + base64.b64encode(
            b"operator:constructed-password-123"
        ).decode()

        def request(path, *, authenticated=False, method="GET", origin=None):
            environ = {
                "REQUEST_METHOD": method,
                "PATH_INFO": path,
                "HTTP_HOST": "lab.example.test",
                "CONTENT_LENGTH": "0",
                "wsgi.input": io.BytesIO(),
            }
            if authenticated:
                environ["HTTP_AUTHORIZATION"] = authorization
            if origin:
                environ["HTTP_ORIGIN"] = origin
            response = {}
            payload = b"".join(application(environ, lambda s, h: response.update(
                status=int(s.split()[0]), headers=dict(h)
            )))
            return response["status"], response["headers"], payload

        self.assertEqual(request("/api/lab/state")[0], 401)
        status, headers, payload = request("/api/lab/state", authenticated=True)
        self.assertEqual(status, 200)
        self.assertIn(b"private-research-name", payload)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["Strict-Transport-Security"], "max-age=31536000")
        self.assertEqual(request("/api/lab/state", authenticated=True,
                                 origin="https://foreign.example")[0], 403)
        self.assertEqual(request("/api/run", authenticated=True, method="POST")[0], 405)
        self.assertEqual(request("/healthz")[0], 200)
        application.workspace.lab.db_path.write_bytes(b"broken")
        status, _, payload = request("/healthz")
        self.assertEqual(status, 503)
        self.assertNotIn(b"private-research-name", payload)

    @unittest.skipUnless(importlib.util.find_spec("waitress"), "optional server runtime required")
    def test_actual_production_cli_http_shutdown_and_restart(self):
        credentials = self.root / "service-operator.json"
        create_credentials(credentials, "operator", "constructed-password-123")
        authorization = "Basic " + base64.b64encode(
            b"operator:constructed-password-123"
        ).decode()

        def request(url, *, authenticated=False, method="GET", origin=None):
            headers = {"Authorization": authorization} if authenticated else {}
            if origin:
                headers["Origin"] = origin
            req = urllib.request.Request(url, method=method, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=2) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as response:
                return response.code, response.read()

        for restart in range(2):
            with self.subTest(restart=restart), socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            base = f"http://127.0.0.1:{port}"
            with (self.root / "service.log").open("ab") as log:
                process = subprocess.Popen(
                    [sys.executable, "-m", "research_lab", "--root",
                     str(self.workspace.lab.root), "serve", "--production",
                     "--port", str(port), "--auth-file", str(credentials)],
                    stdout=log,
                    stderr=log,
                )
                try:
                    deadline = time.monotonic() + 10
                    while True:
                        try:
                            status, _ = request(base + "/healthz")
                            self.assertEqual(status, 200)
                            break
                        except (OSError, urllib.error.URLError):
                            if process.poll() is not None or time.monotonic() > deadline:
                                self.fail("production observatory did not start")
                            time.sleep(0.05)
                    self.assertEqual(request(base + "/api/lab/state")[0], 401)
                    status, body = request(base + "/api/lab/state", authenticated=True)
                    self.assertEqual(status, 200)
                    self.assertEqual(json.loads(body)["programs"][0]["id"],
                                     "private-research-name")
                    self.assertEqual(request(base + "/api/run", authenticated=True,
                                             method="POST")[0], 405)
                    self.assertEqual(request(base + "/api/lab/state", authenticated=True,
                                             origin="https://foreign.example")[0], 403)
                    if restart:
                        self.workspace.lab.db_path.write_bytes(b"invalid database")
                        status, body = request(base + "/healthz")
                        self.assertEqual(status, 503)
                        self.assertNotIn(b"private-research-name", body)
                    process.terminate()
                    self.assertEqual(process.wait(timeout=10), 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
