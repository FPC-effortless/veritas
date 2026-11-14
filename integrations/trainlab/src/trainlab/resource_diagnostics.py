"""Linux trusted-command supervision; per-process limits are not a security sandbox."""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import os
import platform
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

from .prediction_artifacts import _bytes, _hash, _require, _text
from .runner import LabError, digest, read_json, write_json

BOUNDARY = {
    "clock": "monotonic_ns_host_wall",
    "start": "immediately_before_supervised_worker_launch",
    "end": "after_leader_reap_and_process_group_cleanup",
    "includes": [
        "worker_startup",
        "target_startup",
        "all_target_work",
        "exit",
        "reaping",
        "cleanup",
    ],
    "excludes": [
        "input_and_receipt_preparation",
        "final_receipt_serialization",
        "external_services",
    ],
    "device": "CPU_SYNCHRONOUS_ONLY",
}

EXECUTION = {"device": "cpu", "synchronous": True, "detaches": False, "remote_work": False}


def _sha(value):
    import hashlib

    return hashlib.sha256(_bytes(value)).hexdigest()


def _limits(limits):
    _require(
        type(limits) is dict
        and set(limits) == {"wall_seconds", "cpu_seconds", "address_space_bytes", "file_bytes"},
        "explicit limits required",
    )
    _require(
        type(limits["wall_seconds"]) in (int, float) and 0.05 <= limits["wall_seconds"] <= 3600,
        "wall limit must be 0.05..3600 seconds",
    )
    for key, low, high in [
        ("cpu_seconds", 1, 3600),
        ("address_space_bytes", 64 * 1024**2, 1024**4),
        ("file_bytes", 4096, 64 * 1024**2),
    ]:
        _require(type(limits[key]) is int and low <= limits[key] <= high, "invalid resource limit")


def _rate(rate):
    if rate is None:
        return
    _require(
        type(rate) is dict
        and set(rate) == {"per_hour", "currency", "as_of"}
        and type(rate["per_hour"]) in (int, float)
        and 0 <= rate["per_hour"] <= 1e6
        and type(rate["currency"]) is str
        and re.fullmatch("[A-Z]{3}", rate["currency"])
        and type(rate["as_of"]) is str,
        "declared hourly rate/currency/date required",
    )
    try:
        dt.date.fromisoformat(rate["as_of"])
    except ValueError as exc:
        raise LabError("invalid rate date") from exc


def _hardware():
    model = "UNKNOWN"
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                model = line.split(":", 1)[1].strip()
                break
    except OSError:
        pass
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "cpu_model": model,
        "logical_cpus": os.cpu_count(),
        "attestation": "OS_REPORTED_NOT_EXCLUSIVE_HOST",
    }


def _kill_group(pid):
    try:
        os.killpg(pid, signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False


def _artifact(path):
    try:
        return digest(path)
    except OSError:
        return None


def run_command(
    command, root, *, cwd, identities, workload_sha256, limits, execution, hourly_rate=None
):
    """Measure one fresh CPU process session, retaining failed attempts and exact scope.

    Trusted local commands only. No shell, credentials are not captured from the
    environment, but command/config/log contents must be authorized for retention.
    Limits are inherited per process; aggregate descendants/GPU/remote calls are not metered.
    """
    _require(
        sys.platform == "linux" and hasattr(os, "wait4"), "Linux wait4/resource support required"
    )
    _require(
        type(command) is list
        and 1 <= len(command) <= 64
        and all(_text(x) for x in command)
        and Path(command[0]).is_absolute(),
        "bounded argv with absolute executable required",
    )
    _require(
        type(identities) is dict
        and set(identities) == {"model", "dataset", "code", "configuration"}
        and all(_hash(v) for v in identities.values())
        and _hash(workload_sha256),
        "four SHA256 identities and workload identity required",
    )
    _limits(limits)
    _rate(hourly_rate)
    _require(
        _bytes(execution) == _bytes(EXECUTION),
        "declare synchronous CPU execution without detached or remote work",
    )
    command, identities, limits, hourly_rate = copy.deepcopy(
        [command, identities, limits, hourly_rate]
    )
    cwd = Path(cwd).resolve()
    _require(cwd.is_dir(), "existing working directory required")
    root = Path(root).resolve()
    request = {
        "command": command,
        "cwd": str(cwd),
        "limits": limits,
        "identities": identities,
        "workload_sha256": workload_sha256,
        "hourly_rate": hourly_rate,
        "execution": copy.deepcopy(execution),
    }
    _bytes(request)
    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    write_json(root / "request.json", request)
    pin = digest(root / "request.json")
    hardware = _hardware()
    receipt = {
        "schema": "trainlab.resource-session.v1",
        "state": "STARTED",
        "pid": None,
        "request_sha256": pin,
        "identities": identities,
        "workload_sha256": workload_sha256,
        "hardware": hardware,
        "hardware_sha256": _sha(hardware),
        "boundary": copy.deepcopy(BOUNDARY),
        "boundary_sha256": _sha([BOUNDARY, limits, execution]),
        "execution": copy.deepcopy(execution),
        "execution_trust": "CALLER_DECLARED_NOT_ATTESTED",
        "limits": limits,
        "cost_coverage": "INCOMPLETE",
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(root / "receipt.json", receipt)
    process, usage, returncode, timed_out, error, interrupt = None, None, None, False, None, None
    descendants_terminated = False
    with (root / "stdout.log").open("wb") as stdout, (root / "stderr.log").open("wb") as stderr:
        started = time.monotonic_ns()
        try:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import sys; sys.path.insert(0, sys.argv[1]); "
                    "from trainlab.resource_diagnostics import _worker; _worker(sys.argv[2])",
                    str(Path(__file__).resolve().parents[1]),
                    str(root / "request.json"),
                ],
                cwd=cwd,
                stdin=subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                start_new_session=True,
            )
            receipt["pid"] = process.pid
            write_json(root / "receipt.json", receipt)
            while True:
                pid, status, measured = os.wait4(process.pid, os.WNOHANG)
                if pid:
                    usage, returncode = measured, os.waitstatus_to_exitcode(status)
                    process.returncode = returncode
                    break
                remaining = limits["wall_seconds"] - (time.monotonic_ns() - started) / 1e9
                if remaining <= 0:
                    timed_out = True
                    _kill_group(process.pid)
                    _, status, usage = os.wait4(process.pid, 0)
                    returncode = os.waitstatus_to_exitcode(status)
                    process.returncode = returncode
                    break
                time.sleep(min(0.02, remaining))
        except BaseException as exc:
            error = type(exc).__name__
            if not isinstance(exc, Exception):
                interrupt = exc
        finally:
            if process is not None:
                if process.returncode is None:
                    _kill_group(process.pid)
                    try:
                        _, status, usage = os.wait4(process.pid, 0)
                        returncode = os.waitstatus_to_exitcode(status)
                        process.returncode = returncode
                    except ChildProcessError:
                        pass
                descendants_terminated = _kill_group(process.pid)
            elapsed = (time.monotonic_ns() - started) / 1e9
    applied, applied_hash = None, None
    try:
        applied = read_json(root / "limits-applied.json")
        applied_hash = digest(root / "limits-applied.json")
    except (LabError, OSError):
        pass
    expected = {
        "cpu_seconds": [limits["cpu_seconds"]] * 2,
        "address_space_bytes": [limits["address_space_bytes"]] * 2,
        "file_bytes": [limits["file_bytes"]] * 2,
        "core_bytes": [0, 0],
    }
    try:
        verified_limits = _bytes(applied) == _bytes(
            {"pid": receipt["pid"], "request_sha256": pin, "limits": expected}
        )
    except (LabError, OverflowError):
        verified_limits = False
    unchanged = _artifact(root / "request.json") == pin
    logs = {name: _artifact(root / name) for name in ("stdout.log", "stderr.log")}
    wall_overrun = elapsed >= limits["wall_seconds"]
    complete = (
        returncode == 0
        and not timed_out
        and not wall_overrun
        and not error
        and not descendants_terminated
        and verified_limits
        and unchanged
        and usage is not None
        and all(logs.values())
    )
    receipt.update(
        {
            "state": "INTERRUPTED"
            if interrupt
            else "TIMEOUT"
            if timed_out or wall_overrun
            else "SUCCEEDED"
            if complete
            else "FAILED",
            "returncode": returncode,
            "error_type": error,
            "wall_budget_exceeded": wall_overrun,
            "timeout_termination_requested": timed_out,
            "descendants_terminated": descendants_terminated,
            "limits_applied": verified_limits,
            "request_unchanged": unchanged,
            "cost_coverage": "MEASURED" if complete else "INCOMPLETE",
            "wall_seconds": elapsed,
            "user_cpu_seconds": usage.ru_utime if usage else None,
            "system_cpu_seconds": usage.ru_stime if usage else None,
            "peak_process_rss_bytes": usage.ru_maxrss * 1024 if usage else None,
            "resource_scope": "Linux wait4 leader/waited children; RSS is not aggregate tree peak.",
            "limit_scope": "Per-process CPU/address space and per-file size; no aggregate quotas.",
            "unmeasured": ["GPU", "aggregate_tree_RAM", "energy", "remote_cost", "actual_invoice"],
            "signal_cause": "NOT_INFERRED_FROM_EXIT_STATUS",
            "artifacts": {
                **logs,
                "limits-applied.json": applied_hash,
            },
        }
    )
    receipt["money_estimate"] = (
        None
        if hourly_rate is None
        else {
            **hourly_rate,
            "amount": elapsed / 3600 * hourly_rate["per_hour"],
            "scope": "DECLARED_SINGLE_ALLOCATION_WALL_RATE_NOT_A_BILL",
        }
    )
    write_json(root / "receipt.json", receipt)
    if interrupt:
        raise interrupt
    return receipt


def _worker(path):
    import resource

    path = Path(path).resolve()
    request = read_json(path)
    _limits(request["limits"])
    limits = request["limits"]
    mapping = {
        "cpu_seconds": (resource.RLIMIT_CPU, limits["cpu_seconds"]),
        "address_space_bytes": (resource.RLIMIT_AS, limits["address_space_bytes"]),
        "file_bytes": (resource.RLIMIT_FSIZE, limits["file_bytes"]),
        "core_bytes": (resource.RLIMIT_CORE, 0),
    }
    for kind, value in mapping.values():
        resource.setrlimit(kind, (value, value))
    write_json(
        path.parent / "limits-applied.json",
        {
            "pid": os.getpid(),
            "request_sha256": digest(path),
            "limits": {key: list(resource.getrlimit(kind)) for key, (kind, _) in mapping.items()},
        },
    )
    os.chdir(request["cwd"])
    command = request["command"]
    os.execv(command[0], command)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", required=True, type=Path)
    _worker(parser.parse_args().worker)
