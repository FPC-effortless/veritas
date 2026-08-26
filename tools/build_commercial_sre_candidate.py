from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from investigation_world.qualification import (
    QualificationSplit,
    QualificationThresholds,
    build_commercial_sre_candidate,
    cross_split_near_duplicates,
    execute_commercial_sre_policy_suite,
    private_release_manifest,
    qualify_candidate,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build and qualify a license-clean stratified Veritas commercial SRE candidate")
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--per-class", type=int, default=40)
    parser.add_argument("--version", default="sre-commercial-v1")
    parser.add_argument("--random-policy-seed", type=int, default=7)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-suite-output", type=Path)
    args = parser.parse_args()

    candidate, cases = build_commercial_sre_candidate(
        seed=args.seed,
        per_class=args.per_class,
        version=args.version,
    )
    duplicates = cross_split_near_duplicates(candidate.scenarios)
    evaluations = execute_commercial_sre_policy_suite(cases, random_seed=args.random_policy_seed)
    thresholds = QualificationThresholds(
        minimum_private_test_scenarios=30,
        random_chance_reward=0.25,
        maximum_random_excess_over_chance=0.10,
        private_stratum_metadata_key="causal_class",
        minimum_private_strata=4,
        minimum_private_scenarios_per_stratum=5,
        maximum_private_stratum_fraction=0.35,
    )
    report = qualify_candidate(candidate, evaluations, thresholds=thresholds)
    release = private_release_manifest(candidate, report) if report.releaseable else None
    private_cases = [case for case in cases if case.scenario.split == QualificationSplit.PRIVATE_TEST]
    class_counts = Counter(case.causal_class.value for case in private_cases)

    public_report = {
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "benchmark_candidate" if report.releaseable else "not_qualified",
        "candidate_id": candidate.candidate_id,
        "candidate_version": candidate.version,
        "evidence_manifest_id": candidate.evidence_manifest.manifest_id,
        "qualification_report_id": report.report_id,
        "panel_id": report.panel_id,
        "scenario_count": len(candidate.scenarios),
        "private_test_count": len(private_cases),
        "private_class_counts": dict(sorted(class_counts.items())),
        "cross_split_near_duplicates": len(duplicates),
        "policy_means": {key.value: value for key, value in report.policy_means.items()},
        "gates": [gate.model_dump(mode="json") for gate in report.gates],
        "thresholds": thresholds.model_dump(mode="json"),
        "private_release_manifest_id": release.manifest_id if release else None,
        "source_references": candidate.metadata.get("source_references", []),
        "source_text_copied": candidate.metadata.get("source_text_copied"),
        "synthetic": candidate.metadata.get("synthetic"),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(public_report, indent=2, sort_keys=True), encoding="utf-8")

    if args.private_suite_output:
        private_payload = {
            "schema_version": "1.0.0-private",
            "candidate": candidate.model_dump(mode="json"),
            "cases": [case.model_dump(mode="json") for case in cases],
            "policy_evaluations": [item.model_dump(mode="json") for item in evaluations],
            "qualification": report.model_dump(mode="json"),
            "private_release_manifest": release.model_dump(mode="json") if release else None,
        }
        args.private_suite_output.parent.mkdir(parents=True, exist_ok=True)
        args.private_suite_output.write_text(json.dumps(private_payload, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(public_report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
