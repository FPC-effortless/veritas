from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def aggregate(reports: list[dict[str, Any]], qualification: dict[str, Any] | None = None) -> dict[str, Any]:
    if len(reports) < 2:
        raise ValueError("SRE commercial model evidence requires at least two model reports")

    candidate_ids = {str(item["candidate_id"]) for item in reports}
    panel_ids = {str(item["panel_id"]) for item in reports}
    evidence_ids = {str(item["evidence_manifest_id"]) for item in reports}
    report_ids = {str(item["qualification_report_id"]) for item in reports}
    release_ids = {str(item["private_release_manifest_id"]) for item in reports}
    versions = {str(item["benchmark_version"]) for item in reports}
    private_counts = {int(item["private_cases"]) for item in reports}
    class_distributions = {
        json.dumps(item.get("class_distribution", {}), sort_keys=True)
        for item in reports
    }

    identity_sets = {
        "candidate": candidate_ids,
        "panel": panel_ids,
        "evidence manifest": evidence_ids,
        "qualification report": report_ids,
        "private release manifest": release_ids,
        "benchmark version": versions,
        "private-case count": private_counts,
        "private class distribution": class_distributions,
    }
    for name, values in identity_sets.items():
        if len(values) != 1:
            raise ValueError(f"model reports disagree on {name}")

    models = []
    for item in sorted(reports, key=lambda row: str(row["model"])):
        models.append(
            {
                "model": item["model"],
                "accuracy": item["accuracy"],
                "balanced_accuracy": item["balanced_accuracy"],
                "macro_f1": item["macro_f1"],
                "majority_baseline_accuracy": item["majority_baseline_accuracy"],
                "accuracy_lift_over_majority": item["accuracy_lift_over_majority"],
                "ci95_low": item["ci95_low"],
                "ci95_high": item["ci95_high"],
                "private_cases": item["private_cases"],
                "parse_failures": item["parse_failures"],
                "parse_failure_rate": item["parse_failure_rate"],
                "per_class": item["per_class"],
            }
        )

    result: dict[str, Any] = {
        "schema_version": "1.2.0",
        "evidence_type": "veritas-sre-commercial-model-comparison",
        "benchmark_version": next(iter(versions)),
        "candidate_id": next(iter(candidate_ids)),
        "panel_id": next(iter(panel_ids)),
        "evidence_manifest_id": next(iter(evidence_ids)),
        "qualification_report_id": next(iter(report_ids)),
        "private_release_manifest_id": next(iter(release_ids)),
        "private_cases": next(iter(private_counts)),
        "class_distribution": json.loads(next(iter(class_distributions))),
        "models": models,
        "artifact_contract": {
            "scenario_ids_included": False,
            "per_case_predictions_included": False,
            "per_case_expected_labels_included": False,
        },
    }

    if qualification is not None:
        q = qualification.get("qualification", qualification)
        release = qualification.get("private_release_manifest") or {}
        candidate = qualification.get("candidate") or {}
        qualification_candidate_id = str(q.get("candidate_id") or qualification.get("candidate_id"))
        checks = {
            "candidate": (qualification_candidate_id, result["candidate_id"]),
            "panel": (str(q.get("panel_id", "")), result["panel_id"]),
            "evidence manifest": (
                str(q.get("evidence_manifest_id") or candidate.get("evidence_manifest", {}).get("manifest_id", "")),
                result["evidence_manifest_id"],
            ),
            "qualification report": (str(q.get("report_id", "")), result["qualification_report_id"]),
            "private release manifest": (
                str(release.get("manifest_id", "")),
                result["private_release_manifest_id"],
            ),
        }
        for name, (actual, expected) in checks.items():
            if actual != expected:
                raise ValueError(f"qualification {name} does not match model evidence")

        gates = q.get("gates", qualification.get("gates", []))
        failed_gates = [g.get("name") for g in gates if not g.get("passed")]
        if failed_gates:
            raise ValueError(f"qualification has failed gates: {failed_gates}")
        if qualification.get("status") not in (None, "benchmark_candidate"):
            raise ValueError("qualification status is not benchmark_candidate")

        result["qualification"] = {
            "report_id": result["qualification_report_id"],
            "status": qualification.get("status") or "benchmark_candidate",
            "policy_means": q.get("policy_means", qualification.get("policy_means", {})),
            "failed_gates": failed_gates,
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate exact-panel Veritas SRE model-evaluation reports")
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.input]
    qualification = json.loads(args.qualification.read_text(encoding="utf-8")) if args.qualification else None
    result = aggregate(reports, qualification)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
