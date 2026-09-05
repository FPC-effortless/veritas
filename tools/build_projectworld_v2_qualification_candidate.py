from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.qualification.models import QualificationThresholds
from investigation_world.qualification.projectworld_calibration import (
    build_calibrated_projectworld_v2_candidate,
    execute_calibrated_projectworld_v2_policy_suite,
)
from investigation_world.qualification.protocol import private_release_manifest, qualify_candidate


def _projectworld_v2_thresholds() -> QualificationThresholds:
    """Frozen ProjectWorld v2 release thresholds with all 18 gates enabled."""
    return QualificationThresholds(
        private_stratum_metadata_key="project_type",
        minimum_private_strata=5,
        minimum_private_scenarios_per_stratum=1,
        maximum_private_stratum_fraction=0.30,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile, calibrate, and qualify a structurally generated ProjectWorld v2 distribution"
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seeds-per-type", type=int, default=40)
    parser.add_argument("--random-seed", type=int, default=7)
    args = parser.parse_args()

    candidate, specs = build_calibrated_projectworld_v2_candidate(
        seeds_per_type=args.seeds_per_type
    )
    evaluations = execute_calibrated_projectworld_v2_policy_suite(
        candidate,
        specs,
        random_seed=args.random_seed,
    )
    report = qualify_candidate(
        candidate,
        evaluations,
        thresholds=_projectworld_v2_thresholds(),
    )

    # Fail closed: ProjectWorld may claim release qualification only when the
    # exact report contains all 18 gates and every gate passes.
    if len(report.gates) != 18:
        raise RuntimeError(
            f"ProjectWorld v2 requires exactly 18 qualification gates; got {len(report.gates)}"
        )
    if not all(gate.passed for gate in report.gates):
        release = None
    else:
        release = private_release_manifest(candidate, report)

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
        "private_test": sum(item.split.value == "private_test" for item in candidate.scenarios),
        "gate_count": len(report.gates),
        "passed_gates": sum(gate.passed for gate in report.gates),
        "failed_gates": [gate.name for gate in report.gates if not gate.passed],
        "near_duplicate_components": candidate.metadata.get("near_duplicate_components"),
        "policy_means": {key.value: value for key, value in report.policy_means.items()},
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
