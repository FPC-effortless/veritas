"""Research observatory using TrainLab's existing HTTP/security boundary."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from trainlab.server import Workspace

from .adapters import compute_observation
from .core import Controller, LabError
from .evidence import direct, retrieve


class LabWorkspace:
    brand = "Research Lab OS"
    body_limit = 4096

    def __init__(self, runs, experiments=None, *, log_limit=16 * 1024 * 1024, forge_workspace=None):
        self.lab = Controller(runs)
        self.trainlab = Workspace(
            self.lab.root / "runs", None, log_limit=log_limit, forge_workspace=forge_workspace
        )
        self.token = self.trainlab.token
        self.active = None

    def close(self):
        self.trainlab.close()

    def dispatch(self, method, path, headers, body=b""):
        url = urlsplit(path)
        query = parse_qs(url.query)
        if method != "GET":
            return (
                405,
                {"error": "Research observatory is read-only; use the operator CLI."},
                "application/json",
            )
        try:
            if url.path == "/api/lab/state":
                state = self.lab.status()
                state["compute_observation"] = compute_observation()
                state["director"] = direct(self.lab)
                return 200, state, "application/json"
            if url.path == "/api/lab/knowledge":
                return 200, retrieve(self.lab, query.get("q", [""])[0]), "application/json"
            if url.path == "/api/lab/synthesis":
                return 200, self.lab.synthesize(query.get("id", [""])[0]), "application/json"
            if url.path == "/trainlab/":
                return self.trainlab.dispatch("GET", "/", headers)
            static = {
                "/": ("index.html", "text/html; charset=utf-8"),
                "/lab.js": ("lab.js", "text/javascript; charset=utf-8"),
                "/lab.css": ("lab.css", "text/css; charset=utf-8"),
            }
            if url.path in static:
                filename, mime = static[url.path]
                return 200, (Path(__file__).parent / "static" / filename).read_bytes(), mime
            return self.trainlab.dispatch(method, path, headers, body)
        except (LabError, OSError, ValueError):
            return (
                400,
                {"error": "Invalid request or unavailable research evidence."},
                "application/json",
            )
