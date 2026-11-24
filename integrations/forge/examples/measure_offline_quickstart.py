"""Measure the constructed Forge quickstart without forwarding secrets.

The script measures the child Python process. It does not itself disable OS
networking; use the accompanying Docker --network=none workflow for that gate.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCHEMA = "forge.offline-demo-measurement.v1"
LIMIT_MS = 10 * 60 * 1000
SAFE_PARENT_KEYS = ("PATH", "SYSTEMROOT", "WINDIR", "TMP", "TEMP", "TMPDIR", "LANG", "LC_ALL")


def child_environment(root: Path, parent: dict[str, str] | None = None) -> dict[str, str]:
    """Build an allowlisted child environment; never forward tokens or secrets."""
    source = os.environ if parent is None else parent
    env = {key: source[key] for key in SAFE_PARENT_KEYS if source.get(key)}
    env.update(
        {
            "PYTHONPATH": str(root / "src"),
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": tempfile.gettempdir(),
        }
    )
    return env


def _write_receipt(path: Path, receipt: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Evidence paths are immutable: never silently replace a prior run.
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--receipt", type=Path, help="create a new JSON receipt at this path"
    )
    parser.add_argument(
        "--commit",
        help="checked-out source commit SHA (recorded, not independently attested)",
    )
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    quickstart = root / "examples" / "offline_quickstart.py"
    env = child_environment(root)
    started = time.perf_counter_ns()
    quickstart_output = None
    child_exit_code = None
    failure_reason = None
    try:
        completed = subprocess.run(
            [sys.executable, str(quickstart)],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=LIMIT_MS / 1000,
            check=False,
        )
        child_exit_code = completed.returncode
        try:
            quickstart_output = json.loads(completed.stdout)
        except (json.JSONDecodeError, TypeError):
            failure_reason = "quickstart_stdout_not_valid_json"
        if child_exit_code != 0:
            failure_reason = "quickstart_exit_nonzero"
    except subprocess.TimeoutExpired:
        failure_reason = "quickstart_timeout"
    elapsed_ms = (time.perf_counter_ns() - started) // 1_000_000

    expected = {
        "demo": "CONSTRUCTED_ONLY",
        "authentic_dataset": "NOT_USED",
        "rights": "FIXTURE_DECLARATIONS_NOT_VERIFIED",
        "scientific_qualification": "NOT_PERFORMED",
        "model_training": "NOT_PERFORMED",
        "physical_offline_inference": "NOT_RUN",
        "outcomes": "UNKNOWN_UNVERIFIED_ONLY",
        "hidden_labels": "NOT_USED",
    }
    if quickstart_output is not None and any(
        quickstart_output.get(key) != value for key, value in expected.items()
    ):
        failure_reason = "quickstart_scope_contract_mismatch"

    within_limit = elapsed_ms <= LIMIT_MS
    if not within_limit and failure_reason is None:
        failure_reason = "ten_minute_limit_exceeded"
    passed = failure_reason is None and child_exit_code == 0 and within_limit
    result = "PASS" if passed else "FAIL"
    if failure_reason == "quickstart_timeout":
        result = "TIMED_OUT"
    receipt = {
        "schema": SCHEMA,
        "result": result,
        "commit": args.commit,
        "measurement": {
            "elapsed_ms": elapsed_ms,
            "limit_ms": LIMIT_MS,
            "within_ten_minutes": bool(passed),
            "timer": (
                "time.perf_counter_ns around child interpreter startup, imports "
                "and quickstart"
            ),
            "scope": "excludes checkout, runner provisioning and container-image acquisition",
        },
        "environment": {
            "child_environment_keys": sorted(env),
            "secret_environment_forwarding": "DISABLED_BY_ALLOWLIST",
        },
        "network": {
            "enforcement": "EXTERNAL_SANDBOX_REQUIRED",
            "note": (
                "This measurer does not disable OS networking; the CI workflow "
                "runs it in a Docker --network=none container."
            ),
        },
        "child_exit_code": child_exit_code,
        "failure_reason": failure_reason,
        "quickstart": quickstart_output,
        "qualification": {
            "scientific": "NOT_QUALIFIED",
            "source_rights": "NOT_VERIFIED",
            "physical_device": "NOT_RUN",
            "commercial_release": "NOT_AUTHORIZED",
        },
    }
    if args.receipt is not None:
        _write_receipt(args.receipt, receipt)
    print(json.dumps(receipt, sort_keys=True, indent=2, allow_nan=False))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
