"""Execute operator-selected local commands and retain explicit run evidence.

Commands are trusted code, not sandboxed jobs. Only the CLI executes commands;
the dashboard reads saved results and never accepts commands from a browser.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import re
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from itertools import islice
from pathlib import Path

MAX_ACTIVE_RUNS = 1000
MAX_ACTIVE_RECORD_BYTES = 8 * 1024 * 1024
_ACCEPTANCE_FAILURE = "Metric acceptance checks failed: "


class LabError(ValueError):
    """An invalid experiment or incomplete run record."""


def _finite(value) -> bool:
    try:
        return type(value) in (int, float) and math.isfinite(value)
    except OverflowError:
        return False


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise LabError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise LabError("nonfinite JSON number")


def read_json(path: Path, limit: int = 1024 * 1024):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise LabError("JSON file exceeds size limit")
    try:
        return json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid JSON document") from exc


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def write_json(path: Path, value: dict) -> None:
    data = (json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".metadata-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
        if os.name == "posix":
            descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _relative(name: object) -> str:
    if not isinstance(name, str) or not name or "\\" in name:
        raise LabError("expected relative file path")
    path = Path(name)
    if path.is_absolute() or any(part in ("..", ".") for part in name.split("/")):
        raise LabError("paths must stay inside their declared directory")
    return name


def contained_file(root: Path, name: str) -> Path:
    _relative(name)
    target = root / name
    if not target.resolve().is_relative_to(root.resolve()) or not target.is_file():
        raise LabError("missing file or path outside declared directory")
    # Artifacts and inputs may not hide their provenance through symlink aliases.
    if any(parent.is_symlink() for parent in [target, *target.parents] if parent != root.parent):
        raise LabError("symlink paths are unsupported")
    return target


def load_config(path: Path) -> dict:
    config = read_json(path)
    fields = {
        "schema",
        "name",
        "description",
        "command",
        "seed",
        "timeout_seconds",
        "source_kind",
        "split_identity",
        "inputs",
        "artifacts",
        "metrics",
        "budget",
    }
    if isinstance(config, dict) and "research_adequacy" in config:
        from .research_adequacy import validate_pointer

        validate_pointer(config["research_adequacy"])
        fields.add("research_adequacy")
    if isinstance(config, dict) and "execution_purpose" in config:
        if config["execution_purpose"] not in (
            "research",
            "engineering_diagnostic",
            "historical_replay",
        ):
            raise LabError("invalid execution purpose")
        fields.add("execution_purpose")
    version = config.get("schema") if isinstance(config, dict) else None
    if version == "trainlab.experiment.v2":
        fields |= {"workload", "checks"}
    if (
        not isinstance(config, dict)
        or set(config) != fields
        or version not in ("trainlab.experiment.v1", "trainlab.experiment.v2")
    ):
        raise LabError("unsupported experiment schema or fields")
    for key in ("name", "description", "split_identity"):
        if not isinstance(config[key], str) or not config[key].strip() or len(config[key]) > 500:
            raise LabError(f"{key} must be a bounded nonempty string")
    command = config["command"]
    if (
        not isinstance(command, list)
        or not command
        or len(command) > 128
        or any(
            not isinstance(arg, str) or not arg or "\0" in arg or len(arg) > 4096 for arg in command
        )
    ):
        raise LabError("command must be a nonempty argv array")
    if type(config["seed"]) is not int or not 0 <= config["seed"] <= 2**32 - 1:
        raise LabError("seed must be a 32-bit unsigned integer")
    timeout = config["timeout_seconds"]
    if not _finite(timeout) or not 0 < timeout <= 86400:
        raise LabError("timeout must be finite and between zero and one day")
    if config["source_kind"] not in ("CONSTRUCTED", "AUTHENTIC_CANDIDATE"):
        raise LabError("unknown source kind; source rights are never inferred")
    for key in ("inputs", "artifacts"):
        names = config[key]
        if not isinstance(names, list) or not names or len(names) > 128:
            raise LabError(f"{key} must declare 1–128 files")
        for name in names:
            _relative(name)
        if len(set(names)) != len(names):
            raise LabError(f"duplicate {key}")
    metrics = config["metrics"]
    if (
        not isinstance(metrics, dict)
        or not 1 <= len(metrics) <= 64
        or any(
            not isinstance(key, str) or not key or len(key) > 80 or value not in ("min", "max")
            for key, value in metrics.items()
        )
    ):
        raise LabError("metrics must map names to min or max")
    budget = config["budget"]
    if (
        not isinstance(budget, dict)
        or not 1 <= len(budget) <= 32
        or any(
            not isinstance(key, str)
            or not key
            or len(key) > 80
            or type(value) is not int
            or value < 0
            for key, value in budget.items()
        )
    ):
        raise LabError("budget must map names to nonnegative integer declarations")
    if version == "trainlab.experiment.v2":
        validate_workload(config["workload"])
        validate_checks(config["checks"], config["metrics"])
    return config


def validate_workload(workload: object) -> None:
    if not isinstance(workload, dict) or set(workload) != {"kind", "training_method", "execution"}:
        raise LabError("workload must declare kind, training_method and execution")
    if workload["kind"] not in (
        "train",
        "debug",
        "profile",
        "test",
        "export",
        "deployment_check",
    ) or workload["execution"] not in ("single_process", "distributed", "external"):
        raise LabError("unsupported workload kind or execution")
    method = workload["training_method"]
    if workload["kind"] == "train":
        if method not in (
            "supervised",
            "self_supervised",
            "fine_tuning",
            "distillation",
            "reinforcement",
            "continual",
            "custom",
        ):
            raise LabError("training workload requires a supported training_method")
    elif method is not None:
        raise LabError("training_method must be null for non-training workloads")


def validate_checks(checks: object, metrics: dict) -> None:
    if not isinstance(checks, dict) or set(checks) - set(metrics):
        raise LabError("checks must reference declared metrics")
    for bounds in checks.values():
        if (
            not isinstance(bounds, dict)
            or not bounds
            or set(bounds) - {"min", "max"}
            or any(not _finite(value) for value in bounds.values())
            or ("min" in bounds and "max" in bounds and bounds["min"] > bounds["max"])
        ):
            raise LabError("checks require finite inclusive min/max bounds in order")


def failed_checks(checks: dict, metrics: dict) -> list[str]:
    return [
        name
        for name, bounds in checks.items()
        if ("min" in bounds and metrics[name] < bounds["min"])
        or ("max" in bounds and metrics[name] > bounds["max"])
    ]


def _git_identity(root: Path) -> dict:
    try:
        sha = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        dirty = bool(
            subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                timeout=5,
                check=True,
            ).stdout
        )
        return {"commit": sha, "dirty": dirty}
    except (OSError, subprocess.SubprocessError):
        return {"commit": None, "dirty": None}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stop(process: subprocess.Popen) -> None:
    if os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    elif process.poll() is None:
        process.kill()
    process.wait()


def run_experiment(
    config_path: Path,
    runs_root: Path,
    *,
    log_limit: int = 16 * 1024 * 1024,
    cancel: threading.Event | None = None,
) -> dict:
    """Run explicitly selected trusted code, using a unique output directory."""
    if type(log_limit) is not int or not 1 <= log_limit <= 1024 * 1024 * 1024:
        raise LabError("log limit must be an integer between 1 byte and 1 GiB")
    if sum(1 for _ in islice(runs_root.glob("*/run.json"), MAX_ACTIVE_RUNS)) >= MAX_ACTIVE_RUNS:
        raise LabError("active run store is full; archive it and start a new store")
    config_path = config_path.resolve()
    config = load_config(config_path)
    cwd = config_path.parent
    inputs = {name: digest(contained_file(cwd, name)) for name in config["inputs"]}
    adequacy = None
    purpose = config.get("execution_purpose", "research")
    if purpose == "research" and "research_adequacy" not in config:
        refusal = runs_root.resolve() / "adequacy-refusals"
        refusal.mkdir(parents=True, exist_ok=True)
        write_json(
            refusal / (uuid.uuid4().hex + ".json"),
            {
                "schema": "trainlab.research-adequacy-refusal.v1",
                "status": "UNKNOWN",
                "reason": "Research execution requires a pinned adequacy contract",
                "recipe": config,
                "inputs": inputs,
                "qualification": "NOT_QUALIFIED",
            },
        )
        raise LabError("Research adequacy blocked: missing contract (UNKNOWN)")
    if "research_adequacy" in config:
        from .research_adequacy import assess

        adequacy = assess(config, cwd, inputs)
        if adequacy["status"] != "DECLARED_CRITERIA_MET":
            refusal = runs_root.resolve() / "adequacy-refusals"
            refusal.mkdir(parents=True, exist_ok=True)
            write_json(refusal / (uuid.uuid4().hex + ".json"), adequacy)
            raise LabError("Research adequacy blocked: " + adequacy["status"])
        if purpose == "research":
            from .execution_adequacy import validate_execution

            validate_execution(adequacy["contract"], config)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    directory = runs_root.resolve() / run_id
    directory.mkdir(parents=True, mode=0o700)
    output = directory / "output"
    output.mkdir()
    write_json(directory / "experiment.json", config)
    if adequacy is not None:
        write_json(directory / "research_adequacy.json", adequacy)
    record = {
        "schema": "trainlab.run.v1",
        "id": run_id,
        "name": config["name"],
        "description": config["description"],
        "status": "running",
        "started_at": _now(),
        "finished_at": None,
        "elapsed_seconds": None,
        "exit_code": None,
        "error": None,
        "command": config["command"],
        "seed": config["seed"],
        "inputs": inputs,
        "source_kind": config["source_kind"],
        "split_identity": config["split_identity"],
        "metric_directions": config["metrics"],
        "budget": config["budget"],
        "metrics": {},
        "artifacts": {},
        "files": {},
        "git": _git_identity(cwd),
        "runtime": {"python": sys.version.split()[0], "platform": platform.platform()},
        "qualification": "NOT_QUALIFIED",
        "execution_purpose": purpose,
        "research_adequacy": "UNASSESSED" if adequacy is None else "PLAN_ADMITTED",
        "claim_eligibility": "NOT_ESTABLISHED",
        "evidence_capture": "UNASSESSED",
        "source_rights": "NOT_INDEPENDENTLY_VERIFIED",
        "execution_limits": {"log_bytes_per_stream": log_limit},
    }
    if config["schema"] == "trainlab.experiment.v2":
        record.update(
            schema="trainlab.run.v2", workload=config["workload"], checks=config["checks"]
        )
    write_json(directory / "run.json", record)
    env = {
        **os.environ,
        "TRAINLAB_OUTPUT_DIR": str(output),
        "TRAINLAB_SEED": str(config["seed"]),
        "PYTHONHASHSEED": str(config["seed"]),
    }
    started = time.perf_counter()
    process = None
    readers = []
    exceeded = threading.Event()
    capture_errors = []
    drain_deadline = None
    abandoned = threading.Event()

    def capture(source, destination):
        try:
            with source, destination.open("wb") as stream:
                retained = 0
                while True:
                    if os.name == "posix":
                        if drain_deadline is not None and time.monotonic() >= drain_deadline:
                            abandoned.set()
                            break
                        if not select.select([source], [], [], 0.05)[0]:
                            continue
                    block = source.read(65536)
                    if not block:
                        break
                    remaining = log_limit - retained
                    stream.write(block[:remaining])
                    retained += min(len(block), remaining)
                    if len(block) > remaining:
                        exceeded.set()
        except OSError:
            capture_errors.append("Could not persist process logs.")
            exceeded.set()

    try:
        if cancel is not None and cancel.is_set():
            record.update(
                status="interrupted", error="Interrupted by operator or service shutdown."
            )
        else:
            process = subprocess.Popen(
                config["command"],
                cwd=cwd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL,
                start_new_session=os.name == "posix",
                bufsize=0,
            )
            for source, name in ((process.stdout, "stdout.log"), (process.stderr, "stderr.log")):
                reader = threading.Thread(
                    target=capture, args=(source, directory / name), daemon=True
                )
                reader.start()
                readers.append(reader)
            deadline = time.monotonic() + config["timeout_seconds"]
            while True:
                if cancel is not None and cancel.is_set():
                    record.update(
                        status="interrupted", error="Interrupted by operator or service shutdown."
                    )
                    break
                if exceeded.is_set():
                    record.update(
                        status="failed",
                        error="Experiment exceeded its log limit or log storage failed.",
                    )
                    break
                if time.monotonic() >= deadline:
                    record.update(
                        status="timed_out", error="Experiment exceeded its declared timeout."
                    )
                    break
                try:
                    process.wait(timeout=min(0.05, max(0.001, deadline - time.monotonic())))
                    break
                except subprocess.TimeoutExpired:
                    continue
            # Freeze the process group and fully drain bounded pipes BEFORE
            # reading metrics or hashing outputs; children cannot race snapshots.
            _stop(process)
            drain_deadline = time.monotonic() + 0.5
            record["exit_code"] = process.returncode
            for reader in readers:
                reader.join(timeout=2)
            if abandoned.is_set() or any(reader.is_alive() for reader in readers):
                raise LabError("Experiment left detached workers holding process logs open.")
            if exceeded.is_set():
                raise LabError("Experiment exceeded its log limit or log storage failed.")
            if capture_errors:
                raise LabError(capture_errors[0])
            if record["status"] == "running":
                if process.returncode != 0:
                    raise LabError("Experiment exited unsuccessfully; inspect local stderr.log.")
                metrics = read_json(contained_file(output, "metrics.json"))
                if (
                    not isinstance(metrics, dict)
                    or set(metrics) != set(config["metrics"])
                    or any(not _finite(value) for value in metrics.values())
                ):
                    raise LabError(
                        "metrics.json must contain exactly the declared finite scalar metrics"
                    )
                artifacts = {
                    name: digest(contained_file(output, name)) for name in config["artifacts"]
                }
                if any(digest(contained_file(cwd, name)) != sha for name, sha in inputs.items()):
                    raise LabError("Declared inputs changed during the experiment")
                record.update(status="succeeded", metrics=metrics, artifacts=artifacts)
                if purpose == "research":
                    from .execution_adequacy import assess_execution

                    document = read_json(
                        contained_file(output, adequacy["contract"]["execution"]["artifact"])
                    )
                    executed = assess_execution(adequacy["contract"], config, inputs, document)
                    write_json(directory / "execution_adequacy.json", executed)
                    record["research_adequacy"] = (
                        "EXECUTED_CRITERIA_MET"
                        if executed["status"] == "MET"
                        else executed["status"]
                    )
                    if executed["status"] != "MET":
                        raise LabError("Executed research adequacy blocked: " + executed["status"])
                    if "capture" in adequacy["contract"]:
                        from .adequacy_capture import verify_capture

                        capture = read_json(
                            contained_file(output, adequacy["contract"]["capture"]["artifact"]),
                            limit=16 * 1024 * 1024,
                        )
                        capture_check = verify_capture(capture, document, config, inputs)
                        write_json(directory / "capture_verification.json", capture_check)
                        if capture_check.get("admissible") != 1:
                            raise LabError("Measured capture is incomplete or failed")
                        measured_metric = adequacy["contract"]["capture"]["metric"]
                        if metrics[measured_metric] != capture_check["metrics"][measured_metric]:
                            raise LabError(
                                "Reported metric differs from independently rescored capture"
                            )
                        record["evidence_capture"] = "MEASURED_SUPPORTED_ADAPTER"
                    record["claim_eligibility"] = "DECLARED_CONDITIONS_ONLY"

                failures = failed_checks(config.get("checks", {}), metrics)
                if failures:
                    raise LabError(_ACCEPTANCE_FAILURE + ", ".join(failures))
    except KeyboardInterrupt:
        if process is not None:
            _stop(process)
        record.update(
            status="interrupted",
            error="Interrupted by operator.",
            claim_eligibility="NOT_ESTABLISHED",
        )
    except (OSError, ValueError) as exc:
        record.update(status="failed", error=str(exc), claim_eligibility="NOT_ESTABLISHED")
    finally:
        # Reap any descendants before freezing output; experiment commands must
        # wait for their workers and may not leave background jobs running.
        if process is not None and os.name == "posix":
            _stop(process)
        drain_deadline = time.monotonic() + 0.5
        for reader in readers:
            reader.join(timeout=2)
        record["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        record["finished_at"] = _now()
        for name in (
            "experiment.json",
            "stdout.log",
            "stderr.log",
            "output/metrics.json",
            "research_adequacy.json",
            "execution_adequacy.json",
            "capture_verification.json",
        ):
            try:
                record["files"][name] = digest(contained_file(directory, name))
            except (LabError, OSError):
                pass
        write_json(directory / "run.json", record)
    return record


def list_runs(root: Path) -> list[dict]:
    runs = []
    paths = list(islice(root.glob("*/run.json"), MAX_ACTIVE_RUNS + 1))
    if len(paths) > MAX_ACTIVE_RUNS:
        raise LabError("active run store exceeds supported capacity; archive it offline")
    retained_bytes = 0
    for path in sorted(paths, reverse=True):
        try:
            run = read_json(contained_file(root, path.relative_to(root).as_posix()))
            validate_record(run)
            if run["id"] == path.parent.name:
                runs.append(run)
                retained_bytes += len(json.dumps(run, allow_nan=False).encode())
        except (LabError, OSError):
            continue
        if retained_bytes > MAX_ACTIVE_RECORD_BYTES:
            raise LabError("active run metadata exceeds supported capacity; archive it offline")
    return runs


def validate_record(run: object) -> None:
    """Treat stored metadata as untrusted before sending it to a browser."""
    try:
        if not isinstance(run, dict) or run["schema"] not in ("trainlab.run.v1", "trainlab.run.v2"):
            raise LabError("unsupported run record")
        if run["schema"] == "trainlab.run.v2":
            validate_workload(run["workload"])
            validate_checks(run["checks"], run["metric_directions"])
        elif "workload" in run or "checks" in run:
            raise LabError("v1 records cannot declare v2 workload fields")
        if not isinstance(run["id"], str) or not re.fullmatch(
            r"\d{8}T\d{6}-[a-f0-9]{12}", run["id"]
        ):
            raise LabError("invalid run identity")
        if run["status"] not in ("running", "succeeded", "failed", "timed_out", "interrupted"):
            raise LabError("invalid run status")
        purpose = run.get("execution_purpose")
        phase = run.get("research_adequacy", "UNASSESSED")
        eligibility = run.get("claim_eligibility", "NOT_ESTABLISHED")
        if (
            purpose not in (None, "research", "engineering_diagnostic", "historical_replay")
            or phase
            not in ("UNASSESSED", "PLAN_ADMITTED", "UNKNOWN", "INADEQUATE", "EXECUTED_CRITERIA_MET")
            or eligibility not in ("NOT_ESTABLISHED", "DECLARED_CONDITIONS_ONLY")
        ):
            raise LabError("invalid research admission metadata")
        if phase in ("UNKNOWN", "INADEQUATE", "EXECUTED_CRITERIA_MET") and purpose != "research":
            raise LabError("non-research execution cannot claim reconciled adequacy")
        if eligibility == "DECLARED_CONDITIONS_ONLY" and (
            purpose != "research"
            or run["status"] != "succeeded"
            or phase != "EXECUTED_CRITERIA_MET"
            or not {"research_adequacy.json", "execution_adequacy.json"}
            <= set(run.get("files", {}))
        ):
            raise LabError("research eligibility lacks successful reconciled evidence")
        for key in ("name", "description", "started_at", "split_identity", "source_kind"):
            if not isinstance(run[key], str) or not run[key]:
                raise LabError("invalid run metadata")
        datetime.fromisoformat(run["started_at"])
        if run["source_kind"] not in ("CONSTRUCTED", "AUTHENTIC_CANDIDATE"):
            raise LabError("invalid source kind")
        if type(run["seed"]) is not int or not 0 <= run["seed"] <= 2**32 - 1:
            raise LabError("invalid run seed")
        if run["elapsed_seconds"] is not None and (
            not _finite(run["elapsed_seconds"]) or run["elapsed_seconds"] < 0
        ):
            raise LabError("invalid run duration")
        if not isinstance(run["metrics"], dict) or any(
            not _finite(v) for v in run["metrics"].values()
        ):
            raise LabError("invalid run metrics")
        if (
            not isinstance(run["metric_directions"], dict)
            or not run["metric_directions"]
            or any(v not in ("min", "max") for v in run["metric_directions"].values())
        ):
            raise LabError("invalid metric directions")
        if set(run["metrics"]) - set(run["metric_directions"]):
            raise LabError("unexpected run metrics")
        if run["status"] == "succeeded" and set(run["metrics"]) != set(run["metric_directions"]):
            raise LabError("missing successful run metrics")
        if run["status"] == "succeeded" and failed_checks(run.get("checks", {}), run["metrics"]):
            raise LabError("successful run has failing acceptance checks")
        for key in ("inputs", "files", "artifacts"):
            if not isinstance(run[key], dict):
                raise LabError("invalid file identities")
            for name, sha in run[key].items():
                _relative(name)
                if not isinstance(sha, str) or not re.fullmatch("[a-f0-9]{64}", sha):
                    raise LabError("invalid file hash")
        if not isinstance(run["budget"], dict) or any(
            type(v) is not int or v < 0 for v in run["budget"].values()
        ):
            raise LabError("invalid run budget")
        if not isinstance(run["command"], list) or any(
            not isinstance(v, str) for v in run["command"]
        ):
            raise LabError("invalid run command")
        if run["error"] is not None and not isinstance(run["error"], str):
            raise LabError("invalid run error")
        if (
            not isinstance(run["git"], dict)
            or run["git"]["commit"] is not None
            and not isinstance(run["git"]["commit"], str)
        ):
            raise LabError("invalid source commit")
        if run["git"]["dirty"] is not None and type(run["git"]["dirty"]) is not bool:
            raise LabError("invalid source dirty state")
        if not isinstance(run["runtime"], dict) or any(
            not isinstance(run["runtime"][key], str) for key in ("python", "platform")
        ):
            raise LabError("invalid runtime metadata")
        if (
            run["qualification"] != "NOT_QUALIFIED"
            or run["source_rights"] != "NOT_INDEPENDENTLY_VERIFIED"
        ):
            raise LabError("run metadata cannot confer qualification or source rights")
    except (KeyError, TypeError, ValueError) as exc:
        raise LabError("invalid run record") from exc


def verify_run(directory: Path) -> dict:
    record = read_json(directory / "run.json")
    validate_record(record)
    if record.get("status") == "running":
        raise LabError("run is not finalized; it may be active or interrupted by a host shutdown")
    mismatches = []
    hashes = {
        **record["files"],
        **{"output/" + name: sha for name, sha in record["artifacts"].items()},
    }
    for name, sha in hashes.items():
        try:
            if digest(contained_file(directory, name)) != sha:
                mismatches.append(name)
        except (LabError, OSError):
            mismatches.append(name)
    if "experiment.json" not in hashes:
        mismatches.append("experiment.json")
    try:
        config = load_config(contained_file(directory, "experiment.json"))
        expected_schema = config["schema"].replace("experiment", "run")
        if record["schema"] != expected_schema:
            mismatches.append("run.json schema")
        if "research_adequacy" in config:
            from .research_adequacy import verify_report

            if "research_adequacy.json" not in hashes:
                mismatches.append("missing research adequacy report")
            else:
                verify_report(
                    read_json(contained_file(directory, "research_adequacy.json")),
                    config,
                    record["inputs"],
                )
            purpose = config.get("execution_purpose", "research")
            if record.get("execution_purpose") != purpose:
                mismatches.append("execution purpose")
            expected_phase = "PLAN_ADMITTED"
            if purpose == "research" and "execution_adequacy.json" in hashes:
                from .execution_adequacy import assess_execution, validate_execution

                plan = read_json(contained_file(directory, "research_adequacy.json"))
                validate_execution(plan["contract"], config)
                artifact = plan["contract"]["execution"]["artifact"]
                execution = assess_execution(
                    plan["contract"],
                    config,
                    record["inputs"],
                    read_json(contained_file(directory, "output/" + artifact)),
                )
                expected_phase = (
                    "EXECUTED_CRITERIA_MET" if execution["status"] == "MET" else execution["status"]
                )
                if execution != read_json(contained_file(directory, "execution_adequacy.json")):
                    mismatches.append("executed research adequacy")
            if record.get("research_adequacy") != expected_phase:
                mismatches.append("research adequacy phase")
            expected_capture = "UNASSESSED"
            if purpose == "research" and "capture_verification.json" in hashes:
                from .adequacy_capture import verify_capture

                plan = read_json(contained_file(directory, "research_adequacy.json"))
                contract = plan["contract"]
                if "capture" not in contract:
                    raise LabError("unbound capture verification")
                captured = verify_capture(
                    read_json(
                        contained_file(directory, "output/" + contract["capture"]["artifact"]),
                        limit=16 * 1024 * 1024,
                    ),
                    read_json(
                        contained_file(directory, "output/" + contract["execution"]["artifact"])
                    ),
                    config,
                    record["inputs"],
                )
                if captured != read_json(contained_file(directory, "capture_verification.json")):
                    mismatches.append("capture verification changed")
                if captured.get("admissible") == 1:
                    metric = contract["capture"]["metric"]
                    if record["metrics"].get(metric) != captured["metrics"][metric]:
                        mismatches.append("reported metric differs from captured predictions")
                    else:
                        expected_capture = "MEASURED_SUPPORTED_ADAPTER"
            if record.get("evidence_capture", "UNASSESSED") != expected_capture:
                mismatches.append("evidence capture status")
            if (
                purpose == "research"
                and record["status"] == "succeeded"
                and "capture"
                in read_json(contained_file(directory, "research_adequacy.json"))["contract"]
                and expected_capture != "MEASURED_SUPPORTED_ADAPTER"
            ):
                mismatches.append("successful research lacks required measured capture")
            eligible = (
                purpose == "research"
                and record["status"] == "succeeded"
                and expected_phase == "EXECUTED_CRITERIA_MET"
            )
            if purpose == "research" and record["status"] == "succeeded" and not eligible:
                mismatches.append("successful research lacks executed adequacy")
            if record.get("claim_eligibility") != (
                "DECLARED_CONDITIONS_ONLY" if eligible else "NOT_ESTABLISHED"
            ):
                mismatches.append("research claim eligibility")

        else:
            if record.get("evidence_capture", "UNASSESSED") != "UNASSESSED":
                mismatches.append("ungated run claims measured capture")
            if record.get("research_adequacy", "UNASSESSED") != "UNASSESSED":
                mismatches.append("unassessed recipe claims adequacy")
            if record.get("claim_eligibility", "NOT_ESTABLISHED") != "NOT_ESTABLISHED":
                mismatches.append("unassessed recipe claims eligibility")
            if "execution_purpose" in record and record["execution_purpose"] != config.get(
                "execution_purpose", "research"
            ):
                mismatches.append("execution purpose")
        for key in ("workload", "checks"):
            if record.get(key) != config.get(key):
                mismatches.append("run.json " + key)
    except (LabError, OSError):
        mismatches.append("saved experiment")
    # This failure is emitted only after complete result collection. Its phase
    # must still require output checks when BOTH result maps have been erased.
    # Earlier process/output failures can legitimately have no collected results.
    acceptance_failed = (
        record["schema"] == "trainlab.run.v2"
        and record["status"] == "failed"
        and (record["error"] or "").startswith(_ACCEPTANCE_FAILURE)
    )
    collected = (
        record["status"] == "succeeded"
        or acceptance_failed
        or bool(record["metrics"] or record["artifacts"])
    )
    if collected and "output/metrics.json" not in hashes:
        mismatches.append("output/metrics.json")
    if collected:
        try:
            if read_json(contained_file(directory, "output/metrics.json")) != record["metrics"]:
                mismatches.append("run.json metrics")
            config = load_config(contained_file(directory, "experiment.json"))
            if set(config["artifacts"]) != set(record["artifacts"]):
                mismatches.append("run.json artifact list")
        except (LabError, OSError):
            mismatches.append("saved experiment/metrics")
    return {
        "id": record["id"],
        "valid": not mismatches,
        "mismatches": mismatches,
        "scope": "RECORDED_FILE_HASHES_ONLY",
        "qualification": "NOT_QUALIFIED",
    }


def compare_runs(runs: list[dict]) -> dict:
    if len(runs) < 2:
        raise LabError("select at least two runs")
    fields = ("inputs", "source_kind", "split_identity", "metric_directions", "budget", "seed")
    mismatches = [key for key in fields if any(run[key] != runs[0][key] for run in runs[1:])]
    mismatches.extend(
        key
        for key in ("workload", "checks")
        if any(run.get(key) != runs[0].get(key) for run in runs[1:])
    )
    if any(run["status"] != "succeeded" for run in runs):
        mismatches.append("status")
    return {
        "runs": runs,
        "matched_declared_conditions": not mismatches,
        "research_claim_eligibility": "NOT_ESTABLISHED",
        "adequacy_observations": {
            run["id"]: run.get("research_adequacy", "UNASSESSED") for run in runs
        },
        "mismatches": mismatches,
        "qualification": "NOT_QUALIFIED",
        "note": (
            "Declared matching conditions do not establish equal actual compute, "
            "source rights, independent evaluation or a scientific winner."
        ),
    }
