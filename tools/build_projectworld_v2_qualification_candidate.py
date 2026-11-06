from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.qualification.models import QualificationReport, QualificationThresholds
from investigation_world.qualification.projectworld_calibration import (
    build_calibrated_projectworld_v2_candidate,
    execute_calibrated_projectworld_v2_policy_suite,
)
from investigation_world.qualification.protocol import private_release_manifest, qualify_candidate

PROJECTWORLD_V2_GATE_NAMES = frozenset(
    {
        "source_groups",
        "train_source_groups",
        "dev_source_groups",
        "private_test_source_groups",
        "private_test_scenarios",
        "source_disjoint",
        "cross_split_contamination",
        "private_leakage",
        "provenance",
        "deterministic_replay",
        "programmatic_criteria",
        "feasibility",
        "policy_ordering",
        "competent_ceiling",
        "oracle_competent_gap",
        "random_ceiling",
        "exploit_resistance",
        "private_stratum_coverage",
    }
)


def _report_is_releaseable(report: QualificationReport) -> bool:
    names = [gate.name for gate in report.gates]
    if len(names) != 18 or set(names) != PROJECTWORLD_V2_GATE_NAMES:
        raise RuntimeError("ProjectWorld v2 requires the exact 18 named qualification gates")
    return report.releaseable and all(gate.passed for gate in report.gates)


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
        description=(
            "Compile, calibrate, and qualify a structurally generated ProjectWorld v2 distribution"
        )
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--public-output", type=Path, help="Optional aggregate-only summary")
    parser.add_argument("--seeds-per-type", type=int, default=40)
    parser.add_argument("--random-seed", type=int, default=7)
    args = parser.parse_args()
    if args.public_output is not None and args.public_output.resolve() == args.output.resolve():
        raise ValueError("private output and public summary must use different paths")

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

    releaseable = _report_is_releaseable(report)
    release = private_release_manifest(candidate, report) if releaseable else None

    payload = {
        "schema_version": "0.10.0",
        "status": "benchmark_candidate" if releaseable else "not_qualified",
        "candidate": candidate.model_dump(mode="json"),
        "qualification": report.model_dump(mode="json"),
        "policy_evaluations": [item.model_dump(mode="json") for item in evaluations],
        "private_release_manifest": release.model_dump(mode="json") if release else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    # Do not copy evaluator-private rows, identifiers, metadata or observed gate
    # payloads into the public summary. This is an aggregate implementation report.
    summary = {
        "status": payload["status"],
        "scenarios": len(candidate.scenarios),
        "private_test": sum(item.split.value == "private_test" for item in candidate.scenarios),
        "gate_count": len(report.gates),
        "passed_gates": sum(gate.passed for gate in report.gates),
        "failed_gates": [gate.name for gate in report.gates if not gate.passed],
        "gates": [{"name": gate.name, "passed": gate.passed} for gate in report.gates],
        "policy_means": {key.value: value for key, value in report.policy_means.items()},
    }
    summary_json = json.dumps(summary, indent=2, sort_keys=True)
    if args.public_output is not None:
        args.public_output.parent.mkdir(parents=True, exist_ok=True)
        args.public_output.write_text(summary_json, encoding="utf-8")
    print(summary_json)
    if not releaseable:
        raise SystemExit("ProjectWorld v2 qualification failed; no private release manifest issued")


if __name__ == "__main__":
    main()
