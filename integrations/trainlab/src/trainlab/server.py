"""Loopback-only dashboard. Only operator-registered experiment files may run."""
from __future__ import annotations

import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .runner import LabError, compare_runs, contained_file, list_runs, load_config, run_experiment, verify_run


class Dashboard(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, runs: Path, experiments: Path | None, port: int = 8765):
        super().__init__(("127.0.0.1", port), Handler)
        self.runs = runs.resolve()
        self.experiments = experiments.resolve() if experiments is not None else None
        self.token = secrets.token_urlsafe(32)
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="trainlab")
        self.lock = threading.Lock()
        self.active = None

    def recipes(self):
        result = []
        if self.experiments is not None:
            for path in sorted(self.experiments.glob("*.json")):
                try:
                    config = load_config(contained_file(self.experiments, path.name))
                    result.append({"id": path.name, **{key: config[key] for key in (
                        "name", "description", "command", "seed", "source_kind", "timeout_seconds")}})
                except (LabError, OSError):
                    continue
        return result

    def server_close(self):
        super().server_close()
        self.pool.shutdown(wait=True, cancel_futures=True)


class Handler(BaseHTTPRequestHandler):
    server: Dashboard

    def log_message(self, *args):
        # Do not print query strings or experiment metadata in access logs.
        pass

    def _send(self, status, data, mime="application/json"):
        if mime == "application/json":
            data = json.dumps(data, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def _local(self):
        port = self.server.server_port
        hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        origin = self.headers.get("Origin")
        return self.headers.get("Host") in hosts and (
            origin is None or origin in {"http://" + host for host in hosts}
        )

    def do_GET(self):
        if not self._local():
            return self._send(403, {"error": "Local same-origin access required."})
        url = urlsplit(self.path)
        try:
            if url.path == "/api/state":
                job_error = None
                if self.server.active is not None and self.server.active.done():
                    error = self.server.active.exception()
                    if error is not None:
                        job_error = "Experiment could not start. Check the registered recipe and its input files."
                return self._send(200, {"runs": list_runs(self.server.runs), "experiments": self.server.recipes(),
                                        "token": self.server.token, "job_error": job_error,
                                        "busy": self.server.active is not None and not self.server.active.done()})
            if url.path in ("/api/compare", "/api/verify", "/api/log"):
                query = parse_qs(url.query)
                runs = {run["id"]: run for run in list_runs(self.server.runs)}
                if url.path == "/api/compare":
                    ids = query.get("id", [])
                    if len(set(ids)) != len(ids) or any(key not in runs for key in ids):
                        raise LabError("select distinct existing runs")
                    return self._send(200, compare_runs([runs[key] for key in ids]))
                run_id = query.get("id", [""])[0]
                if run_id not in runs:
                    raise LabError("unknown run")
                directory = self.server.runs / run_id
                if url.path == "/api/verify":
                    return self._send(200, verify_run(directory))
                name = query.get("name", [""])[0]
                if name not in ("stdout.log", "stderr.log"):
                    raise LabError("unknown log")
                path = contained_file(directory, name)
                with path.open("rb") as source:
                    source.seek(max(0, path.stat().st_size - 65536))
                    body = source.read(65536).decode("utf-8", errors="replace")
                return self._send(200, {"text": body, "truncated": path.stat().st_size > 65536})
            files = {"/": ("index.html", "text/html; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if url.path in files:
                name, mime = files[url.path]
                return self._send(200, (Path(__file__).parent / "static" / name).read_bytes(), mime)
            return self._send(404, {"error": "Not found"})
        except (LabError, OSError, ValueError, KeyError) as exc:
            return self._send(400, {"error": str(exc)})

    def do_POST(self):
        if not self._local() or not secrets.compare_digest(self.headers.get("X-TrainLab-Token", ""), self.server.token):
            return self._send(403, {"error": "Local same-origin token required."})
        if self.path != "/api/run" or self.server.experiments is None:
            return self._send(404, {"error": "Experiment execution is not enabled."})
        try:
            if self.headers.get("Content-Type") != "application/json":
                raise LabError("application/json required")
            size = int(self.headers.get("Content-Length", "0"))
            if not 0 < size <= 4096:
                raise LabError("invalid request size")
            body = json.loads(self.rfile.read(size))
            if not isinstance(body, dict) or set(body) != {"experiment"}:
                raise LabError("select one registered experiment")
            name = body["experiment"]
            if name not in {recipe["id"] for recipe in self.server.recipes()}:
                raise LabError("unknown experiment")
            path = contained_file(self.server.experiments, name)
            with self.server.lock:
                if self.server.active is not None and not self.server.active.done():
                    return self._send(409, {"error": "An experiment is already running. Wait for it to finish."})
                self.server.active = self.server.pool.submit(run_experiment, path, self.server.runs)
            return self._send(202, {"status": "accepted"})
        except (LabError, OSError, ValueError, TypeError) as exc:
            return self._send(400, {"error": str(exc)})
