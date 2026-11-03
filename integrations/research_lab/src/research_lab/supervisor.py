"""Local process supervision; systemd owns this supervisor on a persistent host."""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import uuid

from .autonomy import tick
from .core import ROLES, LabError, canonical, name, number


def _validate_workers(workers):
    if not isinstance(workers, list) or not workers:
        raise LabError("at least one explicit worker is required")
    ids = set()
    for worker in workers:
        if not isinstance(worker, dict) or set(worker) != {"id", "role", "principal", "resource"}:
            raise LabError("supervised worker requires id, role, principal and resource")
        for key in ("id", "principal", "resource"):
            name(worker[key])
        if (
            worker["id"] in ids
            or not isinstance(worker["role"], str)
            or worker["role"] not in ROLES - {"review"}
        ):
            raise LabError("duplicate worker or unsupported automatic worker role")
        ids.add(worker["id"])
    return sorted(workers, key=lambda worker: worker["id"])


def _locked(path):
    """Observe an existing local lock; never create one in a health probe."""
    import fcntl

    try:
        with path.open("r") as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(stream, fcntl.LOCK_UN)
    except OSError:
        pass
    return False


def _live(activity, lock, now):
    if (
        not activity
        or activity["state"] != "active"
        or activity["host"] != socket.gethostname()
        or not 0 <= now - activity["last_seen"] <= 15
        or activity["pid"] <= 0
        or not _locked(lock)
    ):
        return False
    try:
        os.kill(activity["pid"], 0)
    except OSError:
        return False
    return True


def health(lab, workers):
    """Point-in-time local process evidence, never scientific or hosting proof."""
    workers = _validate_workers(workers)
    with lab.connect() as db:
        db.execute("BEGIN")
        row = db.execute("SELECT * FROM supervisor_activity WHERE id=1").fetchone()
        supervisor = dict(row) if row else None
        registered = {r["id"]: dict(r) for r in db.execute("SELECT * FROM workers")}
        activity = {r["id"]: dict(r) for r in db.execute("SELECT * FROM worker_activity")}
        tasks = [dict(r) for r in db.execute("SELECT id,status,lease_until,owner FROM tasks")]
    now = time.time()
    reasons = []
    supervisor_live = _live(supervisor, lab.root / "supervisor.lock", now)
    if not supervisor_live:
        reasons.append("supervisor lacks a recent local heartbeat, held lock and live PID")
    children = json.loads(supervisor["children"]) if supervisor else {}
    if supervisor and json.loads(supervisor["workers"]) != workers:
        reasons.append("requested workers differ from the active supervisor configuration")
    live = set()
    for worker in workers:
        key = worker["id"]
        observed = activity.get(key)
        if (
            registered.get(key) == worker
            and _live(observed, lab.root / "worker_locks" / key, now)
            and children.get(key) == observed["pid"]
        ):
            live.add(key)
        else:
            reasons.append(f"worker {key} lacks matching supervised process evidence")
    lost = [
        t
        for t in tasks
        if t["status"] == "lost"
        or (t["status"] == "running" and (t["lease_until"] is None or t["lease_until"] < now))
    ]
    if lost:
        reasons.append("lost or expired execution requires confirmed-stop recovery")
    lost_ids = {t["id"] for t in lost}
    running = [
        t
        for t in tasks
        if t["status"] == "running"
        and t["id"] not in lost_ids
        and t["owner"] in live
        and activity[t["owner"]]["task"] == t["id"]
    ]
    if sum(t["status"] == "running" for t in tasks) != len(running):
        reasons.append("running task records lack matching supervised worker evidence")
    return {
        "healthy": not reasons,
        "scope": "POINT_IN_TIME_LOCAL_PROCESS_EVIDENCE",
        "supervisor_session": supervisor["session"] if supervisor else None,
        "supervisor_live": supervisor_live,
        "expected_workers": len(workers),
        "live_workers": len(live),
        "idle_workers": len(live - {t["owner"] for t in running}),
        "running_tasks": len(running),
        "queued_tasks": sum(t["status"] == "queued" for t in tasks),
        "lost_or_expired_tasks": len(lost),
        "reasons": reasons,
        "persistent_host": "UNVERIFIED",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def supervise(lab, workers, *, stop=None, interval=1):
    import fcntl

    workers = _validate_workers(workers)
    number(interval, minimum=0.01)
    stop = stop or threading.Event()
    logs = lab.root / "service_logs"
    logs.mkdir(exist_ok=True)
    with (lab.root / "supervisor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LabError("supervisor is already active") from exc
        for worker in workers:
            lab.worker(
                worker["id"], worker["role"], worker["resource"], principal=worker["principal"]
            )
        session = uuid.uuid4().hex
        children = {}

        def activity(state):
            with lab.transaction() as db:
                db.execute(
                    "INSERT INTO supervisor_activity VALUES (1,?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET session=excluded.session,host=excluded.host,"
                    "pid=excluded.pid,last_seen=excluded.last_seen,state=excluded.state,"
                    "workers=excluded.workers,children=excluded.children",
                    (
                        session,
                        socket.gethostname(),
                        os.getpid(),
                        time.time(),
                        state,
                        canonical(workers),
                        canonical({key: child.pid for key, child in children.items()}),
                    ),
                )

        activity("active")
        with lab.transaction() as db:
            lab._event(db, "supervisor_started", {"session": session, "pid": os.getpid()})

        restarts = {w["id"]: 0 for w in workers}
        retry_at = {w["id"]: 0 for w in workers}
        try:
            while not stop.is_set():
                tick(lab)
                for worker in workers:
                    key = worker["id"]
                    child = children.get(key)
                    if child is not None and child.poll() is not None:
                        with lab.transaction() as db:
                            lab._event(
                                db,
                                "supervised_worker_exit",
                                {"worker": key, "pid": child.pid, "returncode": child.returncode},
                            )
                        retry_at[key] = time.monotonic() + min(30, 2 ** min(restarts[key], 5))
                        restarts[key] += 1
                        del children[key]
                        child = None
                    if child is None and time.monotonic() >= retry_at[key]:
                        command = [
                            sys.executable,
                            "-m",
                            "research_lab",
                            "--root",
                            str(lab.root),
                            "worker",
                            key,
                            "--role",
                            worker["role"],
                            "--resource",
                            worker["resource"],
                            "--principal",
                            worker["principal"],
                            "--watch",
                        ]
                        with (logs / f"{key}.log").open("ab") as stream:
                            children[key] = subprocess.Popen(
                                command, stdout=stream, stderr=subprocess.STDOUT
                            )
                        with lab.transaction() as db:
                            lab._event(
                                db,
                                "supervised_worker_started",
                                {"worker": key, "pid": children[key].pid, "restart": restarts[key]},
                            )
                activity("active")
                stop.wait(interval)
        finally:
            try:
                activity("stopping")
            finally:
                # Losing storage must not skip process cleanup.
                for child in children.values():
                    if child.poll() is None:
                        child.terminate()
                for child in children.values():
                    try:
                        child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait()
            # Lost reservations remain quarantined; killing a parent alone is not
            # proof that an arbitrary external trainer stopped.
            activity("stopped")
            with lab.transaction() as db:
                lab._event(db, "supervisor_stopped", {"session": session, "pid": os.getpid()})
            fcntl.flock(lock, fcntl.LOCK_UN)


def signal_stop():
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    return stop
