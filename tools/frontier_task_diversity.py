from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from investigation_world.frontier.diversity import compute_task_diversity  # noqa: E402


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _artifact_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tasks(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("tasks", "scenarios", "items"):
            value = payload.get(key)
            if isinstance(value, list):
                return value
    raise ValueError("input must be a JSON list or an object containing tasks/scenarios/items")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute offline Frontier task-diversity evidence")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark-name")
    parser.add_argument("--benchmark-version")
    parser.add_argument("--candidate-id")
    parser.add_argument("--panel-id")
    parser.add_argument("--qualification-report-id")
    parser.add_argument("--evidence-manifest-id")
    parser.add_argument("--release-manifest-id")
    args = parser.parse_args()

    report = compute_task_diversity(
        _tasks(_read_json(args.input)),
        benchmark_name=args.benchmark_name,
        benchmark_version=args.benchmark_version,
        candidate_id=args.candidate_id,
        panel_id=args.panel_id,
        qualification_report_id=args.qualification_report_id,
        evidence_manifest_id=args.evidence_manifest_id,
        release_manifest_id=args.release_manifest_id,
        input_artifact_hashes={str(args.input): _artifact_hash(args.input)},
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
