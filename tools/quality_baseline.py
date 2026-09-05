from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = ROOT / "quality" / "python-quality-baseline.json"
SCHEMA_VERSION = "veritas-python-quality-baseline-v1"
EXPECTED_VERSIONS = {"ruff": "0.16.5", "mypy": "2.3.1"}
RUFF_COMMAND = (
    sys.executable,
    "-m",
    "ruff",
    "check",
    ".",
    "--output-format=json",
)
MYPY_COMMAND = (
    sys.executable,
    "-m",
    "mypy",
    "src",
    "--no-incremental",
    "--no-error-summary",
    "--show-error-codes",
    "--show-column-numbers",
    "--no-pretty",
)
MYPY_PATTERN = re.compile(
    r"^(?P<path>.+?):(?P<line>\d+):(?P<column>\d+): "
    r"error: (?P<message>.*?)(?:  \[(?P<code>[^]]+)\])?$"
)


class QualityBaselineError(RuntimeError):
    pass


def _tool_versions() -> dict[str, str]:
    found: dict[str, str] = {}
    for tool, expected in EXPECTED_VERSIONS.items():
        try:
            installed = version(tool)
        except PackageNotFoundError as exc:
            raise QualityBaselineError(
                f"{tool} is not installed; install requirements-quality.txt"
            ) from exc
        if installed != expected:
            raise QualityBaselineError(
                f"{tool} version mismatch: expected {expected}, found {installed}"
            )
        found[tool] = installed
    return found


def _run(command: tuple[str, ...], tool: str) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode not in {0, 1}:
        diagnostic = completed.stderr.strip().splitlines()
        detail = diagnostic[-1] if diagnostic else f"exit {completed.returncode}"
        raise QualityBaselineError(f"{tool} execution failed: {detail}")
    return completed


def _relative_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(ROOT)
        except ValueError as exc:
            raise QualityBaselineError(f"diagnostic escaped repository: {path}") from exc
    normalized = candidate.as_posix()
    if normalized.startswith("../"):
        raise QualityBaselineError(f"diagnostic escaped repository: {path}")
    return normalized


def _lane(path: str) -> str:
    parts = Path(path).parts
    if len(parts) >= 3 and parts[:2] == ("src", "investigation_world"):
        return parts[2].removesuffix(".py") or "package-root"
    return parts[0] if parts else "repository-root"


def _fingerprint(tool: str, path: str, code: str, message: str) -> str:
    payload = json.dumps(
        [tool, path, code, message],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ruff_diagnostics() -> list[dict[str, str]]:
    completed = _run(RUFF_COMMAND, "ruff")
    try:
        rows = json.loads(completed.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise QualityBaselineError("ruff returned invalid JSON") from exc
    diagnostics: list[dict[str, str]] = []
    for row in rows:
        path = _relative_path(row["filename"])
        diagnostics.append(
            {
                "tool": "ruff",
                "path": path,
                "lane": _lane(path),
                "code": str(row["code"]),
                "message": str(row["message"]),
            }
        )
    return diagnostics


def _mypy_diagnostics() -> list[dict[str, str]]:
    completed = _run(MYPY_COMMAND, "mypy")
    diagnostics: list[dict[str, str]] = []
    for line in completed.stdout.splitlines():
        match = MYPY_PATTERN.match(line)
        if match is None:
            if ": error:" in line:
                raise QualityBaselineError(f"unparsed mypy diagnostic: {line}")
            continue
        path = _relative_path(match.group("path"))
        diagnostics.append(
            {
                "tool": "mypy",
                "path": path,
                "lane": _lane(path),
                "code": match.group("code") or "untyped",
                "message": match.group("message"),
            }
        )
    return diagnostics


def _snapshot() -> dict[str, Any]:
    versions = _tool_versions()
    diagnostics = [*_ruff_diagnostics(), *_mypy_diagnostics()]
    fingerprints = Counter(
        _fingerprint(item["tool"], item["path"], item["code"], item["message"])
        for item in diagnostics
    )
    by_tool = Counter(item["tool"] for item in diagnostics)
    by_code = Counter(f"{item['tool']}:{item['code']}" for item in diagnostics)
    by_lane = Counter(f"{item['tool']}:{item['lane']}" for item in diagnostics)
    files: dict[str, set[str]] = {item["tool"]: set() for item in diagnostics}
    for item in diagnostics:
        files[item["tool"]].add(item["path"])
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_versions": versions,
        "commands": {
            "ruff": list(RUFF_COMMAND[2:]),
            "mypy": list(MYPY_COMMAND[2:]),
        },
        "fingerprints": dict(sorted(fingerprints.items())),
        "diagnostics": diagnostics,
        "summary": {
            "diagnostics_by_tool": dict(sorted(by_tool.items())),
            "files_by_tool": {
                tool: len(paths) for tool, paths in sorted(files.items())
            },
            "diagnostics_by_code": dict(sorted(by_code.items())),
            "diagnostics_by_owner_lane": dict(sorted(by_lane.items())),
        },
    }


def _load_baseline() -> dict[str, Any]:
    try:
        baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise QualityBaselineError(f"baseline is missing: {BASELINE_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise QualityBaselineError("baseline is not valid JSON") from exc
    if baseline.get("schema_version") != SCHEMA_VERSION:
        raise QualityBaselineError("baseline schema is unsupported")
    if baseline.get("tool_versions") != EXPECTED_VERSIONS:
        raise QualityBaselineError("baseline tool versions do not match pinned policy")
    return baseline


def _write_snapshot(snapshot: dict[str, Any]) -> None:
    BASELINE_PATH.parent.mkdir(parents=True, exist_ok=True)
    BASELINE_PATH.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _check(snapshot: dict[str, Any], baseline: dict[str, Any]) -> None:
    current = Counter(snapshot["fingerprints"])
    allowed = Counter(baseline["fingerprints"])
    introduced = current - allowed
    removed = allowed - current
    print(json.dumps(snapshot["summary"], indent=2, sort_keys=True))
    print(f"ratchet_removed={sum(removed.values())}")
    if introduced:
        print(f"ratchet_introduced={sum(introduced.values())}", file=sys.stderr)
        for fingerprint, count in sorted(introduced.items()):
            print(f"new {fingerprint} x{count}", file=sys.stderr)
        for item in snapshot["diagnostics"]:
            fingerprint = _fingerprint(
                item["tool"],
                item["path"],
                item["code"],
                item["message"],
            )
            if fingerprint in introduced:
                detail = json.dumps(item, sort_keys=True, ensure_ascii=False)
                print(f"introduced_detail={detail}", file=sys.stderr)
        raise QualityBaselineError("new Ruff/Mypy diagnostics exceed the committed baseline")
    print("ratchet_introduced=0")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Update or enforce the pinned repository-wide Python quality ratchet."
    )
    parser.add_argument("command", choices=("check", "update"))
    args = parser.parse_args(argv)
    try:
        snapshot = _snapshot()
        if args.command == "update":
            _write_snapshot(snapshot)
            print(json.dumps(snapshot["summary"], indent=2, sort_keys=True))
            print(f"updated={BASELINE_PATH.relative_to(ROOT)}")
        else:
            _check(snapshot, _load_baseline())
    except QualityBaselineError as exc:
        print(f"QUALITY_BASELINE_FAILED: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
