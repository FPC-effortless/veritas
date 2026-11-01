"""Frozen protocols, a transactional queue and explicit research evidence state.

Workers are trusted local operator processes. Identity separation is an operational
assertion; SQLite hashes cannot attest a person, remote execution or source rights.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from trainlab.runner import LabError, contained_file, digest, load_config, read_json, write_json


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def identity(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def name(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", value):
        raise LabError("expected bounded identifier")
    return value


def number(value, *, minimum=0):
    if type(value) not in (int, float) or not math.isfinite(value) or value < minimum:
        raise LabError("expected finite nonnegative number")
    return value


def text_list(value, minimum=1):
    if (
        not isinstance(value, list)
        or not minimum <= len(value) <= 128
        or any(not isinstance(x, str) or not x.strip() or len(x) > 8000 for x in value)
    ):
        raise LabError("expected bounded nonempty text list")


PROTOCOL_FIELDS = {
    "schema",
    "id",
    "program",
    "author",
    "question",
    "hypothesis",
    "alternatives",
    "predictions",
    "controls",
    "ablations",
    "metric",
    "direction",
    "minimum_effect",
    "seeds",
    "resource",
    "slots",
    "max_attempts",
    "stopping_rule",
    "scope",
    "priority",
    "source_commit",
    "limitations",
    "next_test",
    "candidate",
    "control",
    "replication_tolerance",
    "replay_artifacts",
}
AGENT_ROLES = {"director", "literature", "theory", "design", "engineering", "synthesis"}
ROLES = {"experiment", "replication", "review", *AGENT_ROLES}


def validate_protocol(p):
    if not isinstance(p, dict) or set(p) != PROTOCOL_FIELDS:
        raise LabError("unknown or missing protocol fields")
    if p["schema"] != "research_lab.protocol.v1":
        raise LabError("unsupported protocol schema")
    for key in ("id", "program", "author", "resource", "metric"):
        name(p[key])
    for key in ("question", "hypothesis", "stopping_rule", "next_test"):
        if not isinstance(p[key], str) or not p[key].strip() or len(p[key]) > 8000:
            raise LabError("missing bounded scientific protocol text")
    for key in ("alternatives", "predictions", "controls", "ablations", "limitations"):
        text_list(p[key], minimum=2 if key in ("alternatives", "predictions") else 1)
    if p["direction"] not in ("min", "max"):
        raise LabError("invalid metric direction")
    number(p["minimum_effect"])
    number(p["priority"])
    number(p["replication_tolerance"])
    text_list(p["replay_artifacts"])
    seeds = p["seeds"]
    if (
        not isinstance(seeds, list)
        or not 3 <= len(seeds) <= 32
        or any(type(x) is not int or not 0 <= x <= 2**32 - 1 for x in seeds)
        or len(set(seeds)) != len(seeds)
    ):
        raise LabError("protocol requires at least three distinct fixed seeds")
    for key, maximum in (("slots", 1024), ("max_attempts", 10)):
        if type(p[key]) is not int or not 1 <= p[key] <= maximum:
            raise LabError("invalid slots or maximum attempts")
    if p["scope"] not in ("ENGINEERING_ONLY", "SYNTHETIC_RESEARCH", "AUTHENTIC_CANDIDATE"):
        raise LabError("unknown evidence scope")
    if not isinstance(p["source_commit"], str) or not re.fullmatch(
        "[a-f0-9]{40}", p["source_commit"]
    ):
        raise LabError("source commit must be pinned")


class Controller:
    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db_path = self.root / "lab.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS programs (
                    id TEXT PRIMARY KEY, objective TEXT NOT NULL,
                    cap_seconds REAL NOT NULL, cap_microusd INTEGER NOT NULL,
                    allow_paid INTEGER NOT NULL,
                    charged_seconds REAL NOT NULL DEFAULT 0,
                    charged_microusd INTEGER NOT NULL DEFAULT 0,
                    reserved_seconds REAL NOT NULL DEFAULT 0,
                    reserved_microusd INTEGER NOT NULL DEFAULT 0,
                    observed_seconds REAL NOT NULL DEFAULT 0,
                    overshoot_seconds REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS resources (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, slots INTEGER NOT NULL,
                    rate_microusd INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workers (
                    id TEXT PRIMARY KEY, role TEXT NOT NULL,
                    resource TEXT NOT NULL REFERENCES resources(id),
                    principal TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS protocols (
                    id TEXT PRIMARY KEY, program TEXT NOT NULL REFERENCES programs(id),
                    spec TEXT NOT NULL, pin TEXT NOT NULL, snapshot_pin TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS authors (
                    id TEXT PRIMARY KEY, principal TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, protocol TEXT NOT NULL REFERENCES protocols(id),
                    role TEXT NOT NULL, descriptor TEXT NOT NULL, dependencies TEXT NOT NULL,
                    status TEXT NOT NULL, owner TEXT REFERENCES workers(id),
                    token TEXT, lease_until REAL, attempt INTEGER NOT NULL DEFAULT 0,
                    max_attempts INTEGER NOT NULL, seconds REAL NOT NULL, slots INTEGER NOT NULL,
                    reserved_cost INTEGER NOT NULL DEFAULT 0,
                    checkpoint TEXT NOT NULL DEFAULT '{}', result TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    task TEXT NOT NULL REFERENCES tasks(id), attempt INTEGER NOT NULL,
                    owner TEXT NOT NULL, started REAL NOT NULL, finished REAL,
                    status TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}',
                    checkpoint TEXT NOT NULL DEFAULT '{}',
                    PRIMARY KEY(task,attempt)
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, at REAL NOT NULL,
                    kind TEXT NOT NULL, payload TEXT NOT NULL, previous TEXT NOT NULL,
                    hash TEXT NOT NULL UNIQUE
                );
                CREATE TABLE IF NOT EXISTS executions (
                    run_id TEXT PRIMARY KEY, task TEXT NOT NULL REFERENCES tasks(id),
                    attempt INTEGER NOT NULL, record_pin TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS nodes (
                    id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL,
                    pin TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS links (
                    source TEXT NOT NULL REFERENCES nodes(id), relation TEXT NOT NULL,
                    target TEXT NOT NULL REFERENCES nodes(id),
                    PRIMARY KEY(source,relation,target)
                );
            """)

    def connect(self):
        db = sqlite3.connect(self.db_path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=30000")
        return db

    @contextmanager
    def transaction(self):
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def _event(self, db, kind, payload):
        previous = db.execute("SELECT hash FROM events ORDER BY sequence DESC LIMIT 1").fetchone()
        prior = previous[0] if previous else "0" * 64
        at = time.time()
        pin = identity([at, kind, payload, prior])
        db.execute(
            "INSERT INTO events(at,kind,payload,previous,hash) VALUES (?,?,?,?,?)",
            (at, kind, canonical(payload), prior, pin),
        )

    def program(self, program_id, objective, cap_seconds, cap_microusd, *, allow_paid=False):
        name(program_id)
        number(cap_seconds, minimum=0.001)
        if type(cap_microusd) is not int or cap_microusd < 0 or type(allow_paid) is not bool:
            raise LabError("invalid program cost authorization")
        if not isinstance(objective, str) or not objective.strip() or len(objective) > 8000:
            raise LabError("expected bounded research objective")
        with self.transaction() as db:
            prior = db.execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
            values = [objective, cap_seconds, cap_microusd, int(allow_paid)]
            if prior:
                if [
                    prior[k] for k in ("objective", "cap_seconds", "cap_microusd", "allow_paid")
                ] != values:
                    raise LabError("program is immutable; create an explicitly amended program")
                return
            db.execute(
                "INSERT INTO programs(id,objective,cap_seconds,cap_microusd,allow_paid) "
                "VALUES (?,?,?,?,?)",
                (program_id, *values),
            )
            self._event(db, "program_registered", {"id": program_id, "caps": values})

    def resource(self, resource_id, kind, slots, rate_microusd):
        name(resource_id)
        if kind not in ("cpu", "gpu") or type(slots) is not int or not 1 <= slots <= 1024:
            raise LabError("invalid resource inventory")
        if type(rate_microusd) is not int or rate_microusd < 0:
            raise LabError("invalid metering rate")
        with self.transaction() as db:
            prior = db.execute("SELECT * FROM resources WHERE id=?", (resource_id,)).fetchone()
            if prior:
                if [prior[k] for k in ("kind", "slots", "rate_microusd")] != [
                    kind,
                    slots,
                    rate_microusd,
                ]:
                    raise LabError("resource inventory is immutable; register a new identity")
                return
            db.execute(
                "INSERT INTO resources VALUES (?,?,?,?)", (resource_id, kind, slots, rate_microusd)
            )
            self._event(
                db, "resource_registered", {"id": resource_id, "kind": kind, "slots": slots}
            )

    def worker(self, worker_id, role, resource, *, principal=None):
        name(worker_id)
        name(principal or worker_id)
        if role not in ROLES:
            raise LabError("unsupported research worker role")
        with self.transaction() as db:
            values = (worker_id, role, resource, principal or worker_id)
            author = db.execute("SELECT principal FROM authors WHERE id=?", (worker_id,)).fetchone()
            if author and author[0] != values[3]:
                raise LabError("worker cannot change frozen author principal")
            prior = db.execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
            if prior and tuple(prior) != values:
                raise LabError("worker identity is immutable")
            db.execute("INSERT OR IGNORE INTO workers VALUES (?,?,?,?)", values)

    def _freeze_author(self, db, author):
        prior = db.execute("SELECT principal FROM authors WHERE id=?", (author,)).fetchone()
        if prior:
            return prior[0]
        worker = db.execute("SELECT principal FROM workers WHERE id=?", (author,)).fetchone()
        principal = worker[0] if worker else author
        db.execute("INSERT INTO authors VALUES (?,?)", (author, principal))
        return principal

    def snapshot(self, protocol_id):
        return self.root / "snapshots" / name(protocol_id)

    def register(self, protocol, recipes_root):
        p = json.loads(canonical(protocol))
        validate_protocol(p)
        recipes_root = Path(recipes_root).resolve()
        configs = {
            arm: load_config(contained_file(recipes_root, p[arm]))
            for arm in ("candidate", "control")
        }
        for cfg in configs.values():
            if cfg["metrics"].get(p["metric"]) != p["direction"]:
                raise LabError("protocol and recipe metric disagree")
            if p["scope"] == "ENGINEERING_ONLY" and cfg["source_kind"] != "CONSTRUCTED":
                raise LabError("engineering fixture source kind mismatch")
            if not set(p["replay_artifacts"]).issubset(cfg["artifacts"]):
                raise LabError("replay artifacts must be declared recipe artifacts")
        if configs["candidate"]["split_identity"] != configs["control"]["split_identity"]:
            raise LabError("candidate/control splits must match")
        pin = identity(p)
        with self.transaction() as db:
            prior = db.execute("SELECT pin FROM protocols WHERE id=?", (p["id"],)).fetchone()
            if prior:
                if prior[0] != pin:
                    raise LabError("protocol is immutable; register an amendment under a new id")
                self._verify_snapshot(db, p["id"])
                return pin
            program = db.execute("SELECT * FROM programs WHERE id=?", (p["program"],)).fetchone()
            resource = db.execute("SELECT * FROM resources WHERE id=?", (p["resource"],)).fetchone()
            if not program or not resource or resource["slots"] < p["slots"]:
                raise LabError("missing program or insufficient registered resource")
            if resource["rate_microusd"] and not program["allow_paid"]:
                raise LabError("paid compute requires an explicit program authorization")
            self._freeze_author(db, p["author"])
            snapshots = self.root / "snapshots"
            snapshots.mkdir(exist_ok=True)
            destination = self.snapshot(p["id"])
            if destination.exists():
                raise LabError("orphan snapshot exists; preserve and inspect before registering")
            with tempfile.TemporaryDirectory(dir=snapshots) as temporary:
                stage = Path(temporary) / "source"
                stage.mkdir()
                inputs = set().union(*(set(c["inputs"]) for c in configs.values()))
                if (
                    sum(contained_file(recipes_root, x).stat().st_size for x in inputs)
                    > 128 * 1024 * 1024
                ):
                    raise LabError("snapshot input closure exceeds 128 MiB")
                for item in sorted(inputs):
                    source = contained_file(recipes_root, item)
                    target = stage / item
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
                jobs = []
                for arm, config in configs.items():
                    for seed in p["seeds"]:
                        filename = f"lab-{arm}-{seed}.json"
                        if filename in inputs or filename in ("protocol.json", "snapshot.json"):
                            raise LabError("reserved snapshot filename")
                        write_json(stage / filename, {**config, "seed": seed})
                        jobs.append(
                            (f"{p['id']}.{arm}.{seed}", filename, config["timeout_seconds"])
                        )
                if {"protocol.json", "snapshot.json"} & inputs:
                    raise LabError("reserved snapshot filename")
                write_json(stage / "protocol.json", p)
                manifest = {
                    x.relative_to(stage).as_posix(): digest(x)
                    for x in sorted(stage.rglob("*"))
                    if x.is_file()
                }
                write_json(stage / "snapshot.json", manifest)
                snapshot_pin = identity(manifest)
                stage.rename(destination)
            db.execute(
                "INSERT INTO protocols VALUES (?,?,?,?,?)",
                (p["id"], p["program"], canonical(p), pin, snapshot_pin),
            )
            experiment_ids = [item[0] for item in jobs]
            for task_id, recipe, seconds in jobs:
                self._task(db, p, task_id, "experiment", {"recipe": recipe}, [], seconds)
            replica_id = p["id"] + ".replication"
            self._task(
                db, p, replica_id, "replication", {}, experiment_ids, sum(x[2] for x in jobs)
            )
            self._task(db, p, p["id"] + ".review", "review", {}, [*experiment_ids, replica_id], 30)
            self._event(
                db, "protocol_frozen", {"id": p["id"], "pin": pin, "snapshot_pin": snapshot_pin}
            )
        return pin

    def _task(self, db, p, task_id, role, descriptor, dependencies, seconds):
        db.execute(
            "INSERT INTO tasks(id,protocol,role,descriptor,dependencies,status,"
            "max_attempts,seconds,slots) VALUES (?,?,?,?,?,'queued',?,?,?)",
            (
                task_id,
                p["id"],
                role,
                canonical(descriptor),
                canonical(dependencies),
                p["max_attempts"],
                seconds,
                p["slots"],
            ),
        )

    def protocol(self, protocol_id):
        with self.connect() as db:
            row = db.execute("SELECT spec FROM protocols WHERE id=?", (protocol_id,)).fetchone()
        if not row:
            raise LabError("unknown protocol")
        return json.loads(row[0])

    def _verify_snapshot(self, db, protocol_id, *, root=None):
        row = db.execute("SELECT * FROM protocols WHERE id=?", (protocol_id,)).fetchone()
        root = self.snapshot(protocol_id) if root is None else Path(root)
        manifest = read_json(contained_file(root, "snapshot.json"))
        if identity(manifest) != row["snapshot_pin"]:
            raise LabError("snapshot manifest changed")
        inventory = {
            x.relative_to(root).as_posix() for x in root.rglob("*") if x.is_file() or x.is_symlink()
        }
        if inventory != {*manifest, "snapshot.json"}:
            raise LabError("snapshot inventory contains unpinned or missing files")
        for filename, pin in manifest.items():
            if digest(contained_file(root, filename)) != pin:
                raise LabError("snapshot input changed")
        if read_json(root / "protocol.json") != json.loads(row["spec"]):
            raise LabError("snapshot protocol changed")
        return row

    @staticmethod
    def _decode_task(row):
        result = dict(row)
        for key in ("descriptor", "dependencies", "checkpoint", "result"):
            result[key] = json.loads(result[key])
        return result

    def task(self, task_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise LabError("unknown task")
        return self._decode_task(row)

    def claim(self, worker_id, *, lease_seconds=30, now=None, task_id=None):
        number(lease_seconds, minimum=1)
        now = time.time() if now is None else number(now)
        with self.transaction() as db:
            worker = db.execute("SELECT * FROM workers WHERE id=?", (worker_id,)).fetchone()
            if not worker:
                raise LabError("unknown worker")
            resource = db.execute(
                "SELECT * FROM resources WHERE id=?", (worker["resource"],)
            ).fetchone()
            active = db.execute(
                "SELECT t.slots,p.spec FROM tasks t JOIN protocols p "
                "ON t.protocol=p.id WHERE t.status IN ('running','lost')"
            ).fetchall()
            used = sum(
                x["slots"]
                for x in active
                if json.loads(x["spec"])["resource"] == worker["resource"]
            )
            rows = db.execute(
                "SELECT t.*, p.spec FROM tasks t JOIN protocols p ON t.protocol=p.id "
                "WHERE t.status='queued' AND t.role=?",
                (worker["role"],),
            ).fetchall()
            rows = sorted(rows, key=lambda r: (-json.loads(r["spec"])["priority"], r["id"]))
            for row in rows:
                if task_id is not None and row["id"] != task_id:
                    continue
                p = json.loads(row["spec"])
                if p["resource"] != worker["resource"] or used + row["slots"] > resource["slots"]:
                    continue
                dependencies = [
                    db.execute("SELECT * FROM tasks WHERE id=?", (key,)).fetchone()
                    for key in json.loads(row["dependencies"])
                ]
                if any(x["status"] in ("failed", "blocked") for x in dependencies):
                    db.execute("UPDATE tasks SET status='blocked' WHERE id=?", (row["id"],))
                    self._event(db, "dependency_blocked", {"task": row["id"]})
                    continue
                if any(x["status"] != "succeeded" for x in dependencies):
                    continue
                if row["role"] in ("review", "replication"):
                    author = db.execute(
                        "SELECT principal FROM authors WHERE id=?", (p["author"],)
                    ).fetchone()
                    authors = {author[0] if author else p["author"]}
                    for dep in dependencies:
                        if dep["owner"]:
                            authors.add(
                                db.execute(
                                    "SELECT principal FROM workers WHERE id=?", (dep["owner"],)
                                ).fetchone()[0]
                            )
                    if worker["principal"] in authors:
                        continue
                program = db.execute(
                    "SELECT * FROM programs WHERE id=?", (p["program"],)
                ).fetchone()
                seconds = row["seconds"] * row["slots"]
                cost = math.ceil(seconds * resource["rate_microusd"])
                if (
                    program["charged_seconds"] + program["reserved_seconds"] + seconds
                    > program["cap_seconds"]
                    or program["charged_microusd"] + program["reserved_microusd"] + cost
                    > program["cap_microusd"]
                ):
                    continue
                self._verify_snapshot(db, row["protocol"])
                token = uuid.uuid4().hex
                db.execute(
                    "UPDATE programs SET reserved_seconds=reserved_seconds+?,"
                    "reserved_microusd=reserved_microusd+? WHERE id=?",
                    (seconds, cost, p["program"]),
                )
                db.execute(
                    "UPDATE tasks SET status='running',owner=?,token=?,lease_until=?,"
                    "attempt=attempt+1,reserved_cost=? WHERE id=?",
                    (worker_id, token, now + lease_seconds, cost, row["id"]),
                )
                db.execute(
                    "INSERT INTO attempts(task,attempt,owner,started,status) VALUES (?,?,?,?,?)",
                    (row["id"], row["attempt"] + 1, worker_id, now, "running"),
                )
                self._event(
                    db,
                    "task_claimed",
                    {"task": row["id"], "worker": worker_id, "attempt": row["attempt"] + 1},
                )
                claimed = db.execute("SELECT * FROM tasks WHERE id=?", (row["id"],)).fetchone()
                return self._decode_task(claimed)
        return None

    def _owned(self, db, task_id, token):
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if (
            not row
            or row["status"] != "running"
            or row["token"] != token
            or row["lease_until"] < time.time()
        ):
            raise LabError("task lease is stale or owned by another worker")
        return row

    def heartbeat(self, task_id, token, *, lease_seconds=30):
        number(lease_seconds, minimum=1)
        with self.transaction() as db:
            self._owned(db, task_id, token)
            db.execute(
                "UPDATE tasks SET lease_until=? WHERE id=?", (time.time() + lease_seconds, task_id)
            )

    def checkpoint(self, task_id, token, context):
        payload = canonical(context)
        if len(payload.encode()) > 65536:
            raise LabError("checkpoint context exceeds 64 KiB")
        with self.transaction() as db:
            self._owned(db, task_id, token)
            db.execute("UPDATE tasks SET checkpoint=? WHERE id=?", (payload, task_id))
            row = db.execute("SELECT attempt FROM tasks WHERE id=?", (task_id,)).fetchone()
            db.execute(
                "UPDATE attempts SET checkpoint=? WHERE task=? AND attempt=?",
                (payload, task_id, row[0]),
            )
            self._event(db, "checkpoint_saved", {"task": task_id, "context_pin": identity(context)})

    def finish(self, task_id, token, status, result, elapsed_seconds):
        if status not in ("succeeded", "failed"):
            raise LabError("unsupported terminal status")
        number(elapsed_seconds)
        with self.transaction() as db:
            row = self._owned(db, task_id, token)
            if status == "succeeded":
                self._verify_snapshot(db, row["protocol"])
                from .execution import validate_completion

                validate_completion(self, self._decode_task(row), result)
                run_refs = (
                    [result] if "run_id" in result else list(result.get("replays", {}).values())
                )
                if len({r["run_id"] for r in run_refs}) != len(run_refs):
                    raise LabError("a replay execution cannot satisfy multiple seed/arm cells")
                for receipt in run_refs:
                    try:
                        db.execute(
                            "INSERT INTO executions VALUES (?,?,?,?)",
                            (receipt["run_id"], task_id, row["attempt"], receipt["record_pin"]),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise LabError(
                            "an execution receipt is already bound to another completion"
                        ) from exc
                if row["role"] in AGENT_ROLES:
                    from .agents import index_agent_output

                    index_agent_output(self, self._decode_task(row), result, db=db)
            self._settle(db, row, status, result, elapsed_seconds)

    def _settle(self, db, row, status, result, elapsed_seconds):
        p = json.loads(
            db.execute("SELECT spec FROM protocols WHERE id=?", (row["protocol"],)).fetchone()[0]
        )
        resource = db.execute("SELECT * FROM resources WHERE id=?", (p["resource"],)).fetchone()
        reserved = row["seconds"] * row["slots"]
        charged = min(elapsed_seconds, row["seconds"]) * row["slots"]
        cost = min(row["reserved_cost"], math.ceil(charged * resource["rate_microusd"]))
        observed = elapsed_seconds * row["slots"]
        overshoot = max(0, observed - reserved)
        db.execute(
            "UPDATE programs SET reserved_seconds=reserved_seconds-?,"
            "reserved_microusd=reserved_microusd-?,charged_seconds=charged_seconds+?,"
            "charged_microusd=charged_microusd+?,observed_seconds=observed_seconds+?,"
            "overshoot_seconds=overshoot_seconds+? WHERE id=?",
            (reserved, row["reserved_cost"], charged, cost, observed, overshoot, p["program"]),
        )
        db.execute(
            "UPDATE tasks SET status=?,result=?,token=NULL,lease_until=NULL WHERE id=?",
            (status, canonical(result), row["id"]),
        )
        db.execute(
            "UPDATE attempts SET finished=?,status=?,result=? WHERE task=? AND attempt=?",
            (time.time(), status, canonical(result), row["id"], row["attempt"]),
        )
        self._event(
            db,
            "task_finished",
            {
                "task": row["id"],
                "status": status,
                "result_pin": identity(result),
                "charged_seconds": charged,
                "observed_seconds": observed,
                "reserved_seconds": reserved,
                "overshoot_seconds": overshoot,
            },
        )

    def expire(self, *, now=None):
        now = time.time() if now is None else number(now)
        with self.transaction() as db:
            rows = db.execute(
                "SELECT id FROM tasks WHERE status='running' AND lease_until<?", (now,)
            ).fetchall()
            for row in rows:
                db.execute("UPDATE tasks SET status='lost',token=NULL WHERE id=?", (row[0],))
                self._event(db, "worker_liveness_unknown", {"task": row[0]})
        return len(rows)

    def recover(self, task_id, *, confirmed_stopped=False):
        if confirmed_stopped is not True:
            raise LabError("unknown execution must be confirmed stopped before recovery")
        with self.transaction() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if not row or row["status"] != "lost":
                raise LabError("only a lost task can be recovered")
            self._settle(
                db,
                row,
                "failed",
                {"error": "lost worker; conservatively charged full reservation"},
                row["seconds"],
            )
            if row["attempt"] < row["max_attempts"]:
                db.execute("UPDATE tasks SET status='queued' WHERE id=?", (task_id,))
            self._event(db, "stopped_execution_recovered", {"task": task_id})

    def status(self):
        with self.connect() as db:
            data = {
                table: [dict(row) for row in db.execute(f"SELECT * FROM {table}")]
                for table in (
                    "programs",
                    "resources",
                    "workers",
                    "authors",
                    "protocols",
                    "tasks",
                    "attempts",
                    "executions",
                )
            }
        for row in data["tasks"]:
            row.pop("token", None)
            for key in ("descriptor", "dependencies", "checkpoint", "result"):
                row[key] = json.loads(row[key])
        for row in data["protocols"]:
            row["spec"] = json.loads(row["spec"])
        for row in data["attempts"]:
            for key in ("checkpoint", "result"):
                row[key] = json.loads(row[key])
        data["scientific_qualification"] = "NOT_QUALIFIED"
        data["metering_scope"] = "LOCAL_RESERVED_SLOT_WALL_SECONDS_AND_DECLARED_RATES"
        return data

    def synthesize(self, protocol_id):
        from .evidence import synthesize

        return synthesize(self, protocol_id)
