from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.qualification.models import QualificationThresholds
from investigation_world.qualification.projectworld import (
    build_projectworld_v2_qualification_candidate,
    execute_projectworld_v2_policy_suite,
)
from investigation_world.qualification.protocol import private_release_manifest, qualify_candidate


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile, calibrate, and qualify a structurally generated ProjectWorld v2 distribution"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds-per-type", type=int, default=40)
    parser.add_argument("--random-seed", type=int, default=7)
    args = parser.parse_args()

    candidate, specs = build_projectworld_v2_qualification_candidate(
        seeds_per_type=args.seeds_per_type
    )
    evaluations = execute_projectworld_v2_policy_suite(
        candidate,
        specs,
        random_seed=args.random_seed,
    )
    report = qualify_candidate(candidate, evaluations, thresholds=QualificationThresholds())
    release = private_release_manifest(candidate, report) if report.releaseable else None
    payload = {
        "schema_version": "0.10.0",
        "status": "benchmark_candidate" if report.releaseable else "not_qualified",
        "candidate": candidate.model_dump(mode="json"),
        "qualification": report.model_dump(mode="json"),
        "policy_evaluations": [item.model_dump(mode="json") for item in evaluations],
        "private_release_manifest": release.model_dump(mode="json") if release else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": payload["status"],
        "candidate_id": candidate.candidate_id,
        "report_id": report.report_id,
        "scenarios": len(candidate.scenarios),
        "failed_gates": [gate.name for gate in report.gates if not gate.passed],
        "policy_means": {key.value: value for key, value in report.policy_means.items()},
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
