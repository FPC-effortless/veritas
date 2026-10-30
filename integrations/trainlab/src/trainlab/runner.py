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
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


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
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


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
    if (
        not isinstance(config, dict)
        or set(config) != fields
        or config["schema"] != "trainlab.experiment.v1"
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
    return config


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


def run_experiment(config_path: Path, runs_root: Path) -> dict:
    """Run explicitly selected trusted code, using a unique output directory."""
    config_path = config_path.resolve()
    config = load_config(config_path)
    cwd = config_path.parent
    inputs = {name: digest(contained_file(cwd, name)) for name in config["inputs"]}
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:12]
    directory = runs_root.resolve() / run_id
    directory.mkdir(parents=True, mode=0o700)
    output = directory / "output"
    output.mkdir()
    write_json(directory / "experiment.json", config)
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
        "source_rights": "NOT_INDEPENDENTLY_VERIFIED",
    }
    write_json(directory / "run.json", record)
    env = {
        **os.environ,
        "TRAINLAB_OUTPUT_DIR": str(output),
        "TRAINLAB_SEED": str(config["seed"]),
        "PYTHONHASHSEED": str(config["seed"]),
    }
    started = time.perf_counter()
    process = None
    try:
        with (
            (directory / "stdout.log").open("wb") as stdout,
            (directory / "stderr.log").open("wb") as stderr,
        ):
            process = subprocess.Popen(
                config["command"],
                cwd=cwd,
                env=env,
                stdout=stdout,
                stderr=stderr,
                stdin=subprocess.DEVNULL,
                start_new_session=os.name == "posix",
            )
            try:
                record["exit_code"] = process.wait(timeout=config["timeout_seconds"])
            except subprocess.TimeoutExpired:
                _stop(process)
                record["exit_code"] = process.returncode
                record["status"] = "timed_out"
                record["error"] = "Experiment exceeded its declared timeout."
            else:
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
    except KeyboardInterrupt:
        if process is not None:
            _stop(process)
        record.update(status="interrupted", error="Interrupted by operator.")
    except (OSError, ValueError) as exc:
        record.update(status="failed", error=str(exc))
    finally:
        # Reap any descendants before freezing output; experiment commands must
        # wait for their workers and may not leave background jobs running.
        if process is not None and os.name == "posix":
            _stop(process)
        record["elapsed_seconds"] = round(time.perf_counter() - started, 6)
        record["finished_at"] = _now()
        for name in ("experiment.json", "stdout.log", "stderr.log", "output/metrics.json"):
            try:
                record["files"][name] = digest(contained_file(directory, name))
            except (LabError, OSError):
                pass
        write_json(directory / "run.json", record)
    return record


def list_runs(root: Path) -> list[dict]:
    runs = []
    for path in sorted(root.glob("*/run.json"), reverse=True):
        try:
            run = read_json(contained_file(root, path.relative_to(root).as_posix()))
            validate_record(run)
            if run["id"] == path.parent.name:
                runs.append(run)
        except (LabError, OSError):
            continue
    return runs


def validate_record(run: object) -> None:
    """Treat stored metadata as untrusted before sending it to a browser."""
    try:
        if not isinstance(run, dict) or run["schema"] != "trainlab.run.v1":
            raise LabError("unsupported run record")
        if not isinstance(run["id"], str) or not re.fullmatch(
            r"\d{8}T\d{6}-[a-f0-9]{12}", run["id"]
        ):
            raise LabError("invalid run identity")
        if run["status"] not in ("running", "succeeded", "failed", "timed_out", "interrupted"):
            raise LabError("invalid run status")
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
    if record.get("status") == "succeeded" and "output/metrics.json" not in hashes:
        mismatches.append("output/metrics.json")
    if record["status"] == "succeeded":
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
    if any(run["status"] != "succeeded" for run in runs):
        mismatches.append("status")
    return {
        "runs": runs,
        "matched_declared_conditions": not mismatches,
        "mismatches": mismatches,
        "qualification": "NOT_QUALIFIED",
        "note": (
            "Declared matching conditions do not establish equal actual compute, "
            "source rights, independent evaluation or a scientific winner."
        ),
    }
