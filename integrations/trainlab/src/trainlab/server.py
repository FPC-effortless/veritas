"""Shared dashboard application and loopback-only development HTTP adapter."""

from __future__ import annotations

import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .runner import (
    LabError,
    compare_runs,
    contained_file,
    list_runs,
    load_config,
    run_experiment,
    verify_run,
)

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
}


class Workspace:
    brand = "TrainLab"
    body_limit = 4096

    def __init__(
        self,
        runs: Path,
        experiments: Path | None,
        *,
        log_limit=16 * 1024 * 1024,
        forge_workspace: Path | None = None,
    ):
        self.runs = runs.resolve()
        self.runs.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.experiments = experiments.resolve() if experiments is not None else None
        self.log_limit = log_limit
        self.token = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trainlab")
        self.lock = threading.Lock()
        self.active = None
        self.cancel = threading.Event()
        self.forge = None
        if forge_workspace is not None:
            try:
                from forge_data.workbench import ForgeWorkspace
            except ImportError as error:
                raise LabError("install the Forge package to enable its workbench") from error
            self.forge = ForgeWorkspace(forge_workspace, None)
            self.forge.trainlab_url = "/"
            self.body_limit = self.forge.body_limit

    def close(self):
        self.cancel.set()
        self.pool.shutdown(wait=True, cancel_futures=True)
        if self.forge is not None:
            self.forge.close()

    def recipes(self):
        result = []
        if self.experiments is not None:
            for path in sorted(self.experiments.glob("*.json")):
                try:
                    config = load_config(contained_file(self.experiments, path.name))
                    result.append(
                        {
                            "id": path.name,
                            **{
                                key: config[key]
                                for key in (
                                    "name",
                                    "description",
                                    "command",
                                    "seed",
                                    "source_kind",
                                    "timeout_seconds",
                                )
                            },
                        }
                    )
                except (LabError, OSError):
                    continue
        return result

    def dispatch(self, method, path, headers, body=b""):
        """Host/origin/auth checks are the HTTP adapter's responsibility."""
        from .operations import store_health

        url = urlsplit(path)
        if self.forge is not None and (
            url.path in ("/forge", "/forge/") or url.path.startswith(("/forge/", "/api/forge/"))
        ):
            return self.forge.dispatch(method, path, headers, body)
        try:
            if method == "GET":
                if url.path == "/healthz":
                    health = store_health(self.runs)
                    if self.forge is not None:
                        forge_status, forge_health, _ = self.forge.dispatch("GET", "/healthz", {})
                        health["forge"] = forge_health
                        if forge_status != 200:
                            health["status"] = "degraded"
                    return (200 if health["status"] == "ok" else 503), health, "application/json"
                if url.path == "/api/state":
                    job_error = None
                    if (
                        self.active is not None
                        and self.active.done()
                        and self.active.exception() is not None
                    ):
                        job_error = (
                            "Experiment could not start. "
                            "Check the registered recipe and its input files."
                        )
                    return (
                        200,
                        {
                            "runs": list_runs(self.runs),
                            "experiments": self.recipes(),
                            "token": self.token,
                            "job_error": job_error,
                            "busy": self.active is not None and not self.active.done(),
                            "forge_enabled": self.forge is not None,
                        },
                        "application/json",
                    )
                if url.path in ("/api/compare", "/api/verify", "/api/log"):
                    query = parse_qs(url.query)
                    runs = {run["id"]: run for run in list_runs(self.runs)}
                    if url.path == "/api/compare":
                        ids = query.get("id", [])
                        if len(set(ids)) != len(ids) or any(key not in runs for key in ids):
                            raise LabError("select distinct existing runs")
                        return 200, compare_runs([runs[key] for key in ids]), "application/json"
                    run_id = query.get("id", [""])[0]
                    if run_id not in runs:
                        raise LabError("unknown run")
                    directory = self.runs / run_id
                    if url.path == "/api/verify":
                        return 200, verify_run(directory), "application/json"
                    name = query.get("name", [""])[0]
                    if name not in ("stdout.log", "stderr.log"):
                        raise LabError("unknown log")
                    file = contained_file(directory, name)
                    size = file.stat().st_size
                    with file.open("rb") as source:
                        source.seek(max(0, size - 65536))
                        text = source.read(65536).decode("utf-8", errors="replace")
                    return 200, {"text": text, "truncated": size > 65536}, "application/json"
                files = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                    "/style.css": ("style.css", "text/css; charset=utf-8"),
                }
                if url.path in files:
                    name, mime = files[url.path]
                    return 200, (Path(__file__).parent / "static" / name).read_bytes(), mime
                return 404, {"error": "Not found"}, "application/json"
            if method != "POST":
                return 405, {"error": "Method not allowed"}, "application/json"
            if not secrets.compare_digest(headers.get("X-TrainLab-Token", ""), self.token):
                return 403, {"error": "Local same-origin token required."}, "application/json"
            if url.path != "/api/run" or self.experiments is None:
                return 404, {"error": "Experiment execution is not enabled."}, "application/json"
            if headers.get("Content-Type") != "application/json" or not 0 < len(body) <= 4096:
                raise LabError("bounded application/json request required")
            payload = json.loads(body)
            if not isinstance(payload, dict) or set(payload) != {"experiment"}:
                raise LabError("select one registered experiment")
            name = payload["experiment"]
            if name not in {recipe["id"] for recipe in self.recipes()}:
                raise LabError("unknown experiment")
            recipe = contained_file(self.experiments, name)
            with self.lock:
                if self.cancel.is_set():
                    return 503, {"error": "Service is shutting down."}, "application/json"
                if self.active is not None and not self.active.done():
                    return (
                        409,
                        {"error": "An experiment is already running. Wait for it to finish."},
                        "application/json",
                    )
                self.active = self.pool.submit(
                    run_experiment, recipe, self.runs, log_limit=self.log_limit, cancel=self.cancel
                )
            return 202, {"status": "accepted"}, "application/json"
        except (LabError, OSError, ValueError, KeyError, TypeError):
            # Detailed source paths or exception text can contain operator data.
            return (
                400,
                {"error": "Invalid request or unavailable saved record."},
                "application/json",
            )


def local_request(headers, port, public_origin=None):
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {"http://" + host for host in hosts}
    if public_origin:
        hosts.add(urlsplit(public_origin).netloc)
        origins.add(public_origin)
    return headers.get("Host") in hosts and (
        headers.get("Origin") is None or headers.get("Origin") in origins
    )


class Dashboard(ThreadingHTTPServer):
    """Development/local adapter. Use the optional production WSGI server remotely."""

    daemon_threads = True

    def __init__(
        self,
        runs: Path,
        experiments: Path | None,
        port=8765,
        *,
        workspace_factory=Workspace,
        forge_workspace=None,
    ):
        ThreadingHTTPServer.__init__(self, ("127.0.0.1", port), Handler)
        options = {"forge_workspace": forge_workspace} if forge_workspace is not None else {}
        try:
            self.workspace = workspace_factory(runs, experiments, **options)
        except BaseException:
            ThreadingHTTPServer.server_close(self)
            raise

    @property
    def active(self):
        return self.workspace.active

    @property
    def token(self):
        return self.workspace.token

    def dispatch(self, *args):
        return self.workspace.dispatch(*args)

    def server_close(self):
        ThreadingHTTPServer.server_close(self)
        self.workspace.close()


class Handler(BaseHTTPRequestHandler):
    server: Dashboard

    def log_message(self, *args):
        pass

    def _send(self, status, data, mime="application/json"):
        if mime == "application/json":
            data = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        for key, value in {
            **SECURITY_HEADERS,
            "Content-Type": mime,
            "Content-Length": str(len(data)),
        }.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, method):
        if not local_request(self.headers, self.server.server_port):
            return self._send(403, {"error": "Local same-origin access required."})
        try:
            self.connection.settimeout(10)
            body = b""
            if method == "POST":
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= self.server.workspace.body_limit:
                    return self._send(400, {"error": "Invalid request size."})
                body = self.rfile.read(size)
                if len(body) != size:
                    return self._send(400, {"error": "Incomplete request body."})
            self._send(*self.server.dispatch(method, self.path, self.headers, body))
        except (ValueError, TimeoutError):
            self._send(400, {"error": "Invalid or incomplete request."})

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")
