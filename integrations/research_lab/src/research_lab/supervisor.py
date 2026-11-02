"""Local process supervision; systemd owns this supervisor on a persistent host."""

from __future__ import annotations

import signal
import subprocess
import sys
import threading
import time

from .autonomy import tick
from .core import LabError, name


def supervise(lab, workers, *, stop=None, interval=1):
    import fcntl

    if not isinstance(workers, list) or not workers:
        raise LabError("at least one explicit worker is required")
    ids = set()
    for worker in workers:
        if not isinstance(worker, dict) or set(worker) != {"id", "role", "principal", "resource"}:
            raise LabError("supervised worker requires id, role, principal and resource")
        name(worker["id"])
        if worker["id"] in ids or worker["role"] == "review":
            raise LabError("duplicate worker or reviewer requires its own receipt session")
        ids.add(worker["id"])
        lab.worker(worker["id"], worker["role"], worker["resource"], principal=worker["principal"])
    stop = stop or threading.Event()
    logs = lab.root / "service_logs"
    logs.mkdir(exist_ok=True)
    with (lab.root / "supervisor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LabError("supervisor is already active") from exc
        children = {}
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
                stop.wait(interval)
        finally:
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
            fcntl.flock(lock, fcntl.LOCK_UN)


def signal_stop():
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    return stop
