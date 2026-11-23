"""Research observatory using TrainLab's existing HTTP/security boundary."""

from __future__ import annotations

import sqlite3
import time
from contextlib import closing
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from trainlab.server import Workspace

from .adapters import compute_observation
from .core import Controller, LabError
from .evidence import direct, retrieve


def database_health(path: Path) -> dict:
    """Bounded, read-only storage probe; no claim about worker or evidence validity."""
    try:
        if path.is_symlink() or not path.is_file():
            raise OSError("unavailable database")
        deadline = time.monotonic() + 1.0
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=1)) as db:
            db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            if db.execute("PRAGMA quick_check(1)").fetchone() != ("ok",):
                raise sqlite3.DatabaseError("invalid database")
            # Prepare every core observatory projection without loading records.
            # quick_check alone also succeeds for an unrelated/empty SQLite file.
            for query in (
                "SELECT id,objective,cap_seconds,cap_microusd,allow_paid,charged_seconds,"
                "charged_microusd,reserved_seconds,reserved_microusd,observed_seconds,"
                "overshoot_seconds FROM programs LIMIT 0",
                "SELECT id,kind,slots,rate_microusd FROM resources LIMIT 0",
                "SELECT id,role,resource,principal FROM workers LIMIT 0",
                "SELECT id,session,host,pid,last_seen,state,task FROM worker_activity LIMIT 0",
                "SELECT id,session,host,pid,last_seen,state,workers,children "
                "FROM supervisor_activity LIMIT 0",
                "SELECT id,program,spec,pin,snapshot_pin FROM protocols LIMIT 0",
                "SELECT id,principal FROM authors LIMIT 0",
                "SELECT id,protocol,role,descriptor,dependencies,status,owner,token,lease_until,"
                "attempt,max_attempts,seconds,slots,reserved_cost,checkpoint,result "
                "FROM tasks LIMIT 0",
                "SELECT task,attempt,owner,started,finished,status,result,checkpoint "
                "FROM attempts LIMIT 0",
                "SELECT sequence,at,kind,payload,previous,hash FROM events LIMIT 0",
                "SELECT run_id,task,attempt,record_pin FROM executions LIMIT 0",
                "SELECT id,kind,body,pin FROM nodes LIMIT 0",
                "SELECT source,relation,target FROM links LIMIT 0",
            ):
                db.execute(query).fetchone()
            tables = {row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "autonomous_lanes" in tables:
                db.execute("SELECT id,pin,phase,reason FROM autonomous_lanes LIMIT 0")
            if "autonomous_rounds" in tables:
                db.execute("SELECT lane,n,profile,protocol,decision FROM autonomous_rounds LIMIT 0")
        return {"status": "ok"}
    except (OSError, sqlite3.Error):
        return {"status": "degraded", "reason": "research database unavailable or invalid"}


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
            if url.path == "/healthz":
                status, health, mime = self.trainlab.dispatch("GET", "/healthz", headers)
                health["research_database"] = database_health(self.lab.db_path)
                if health["research_database"]["status"] != "ok":
                    status, health["status"] = 503, "degraded"
                return status, health, mime
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
        except sqlite3.Error:
            return (
                503,
                {"error": "Research database unavailable. Inspect service storage."},
                "application/json",
            )
        except (LabError, OSError, ValueError):
            return (
                400,
                {"error": "Invalid request or unavailable research evidence."},
                "application/json",
            )
