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
    versions = {str(item["benchmark_version"]) for item in reports}
    if len(candidate_ids) != 1:
        raise ValueError("model reports were evaluated against different SRE candidates")
    if len(panel_ids) != 1:
        raise ValueError("model reports were evaluated against different private panels")
    if len(evidence_ids) != 1:
        raise ValueError("model reports were evaluated against different evidence manifests")
    if len(versions) != 1:
        raise ValueError("model reports use different benchmark versions")

    case_id_sets = [{str(row["scenario_id"]) for row in item["cases"]} for item in reports]
    if any(case_ids != case_id_sets[0] for case_ids in case_id_sets[1:]):
        raise ValueError("per-model private scenario identities differ")

    models = []
    for item in sorted(reports, key=lambda row: str(row["model"])):
        models.append(
            {
                "model": item["model"],
                "accuracy": item["accuracy"],
                "ci95_low": item["ci95_low"],
                "ci95_high": item["ci95_high"],
                "private_cases": item["private_cases"],
                "parse_failures": item["parse_failures"],
                "parse_failure_rate": item["parse_failure_rate"],
                "per_class": item["per_class"],
            }
        )

    result: dict[str, Any] = {
        "schema_version": "1.0.0",
        "evidence_type": "veritas-sre-commercial-model-comparison",
        "benchmark_version": next(iter(versions)),
        "candidate_id": next(iter(candidate_ids)),
        "panel_id": next(iter(panel_ids)),
        "evidence_manifest_id": next(iter(evidence_ids)),
        "private_cases": len(case_id_sets[0]),
        "models": models,
    }
    if qualification is not None:
        q = qualification.get("qualification", qualification)
        if str(q.get("candidate_id")) != result["candidate_id"]:
            raise ValueError("qualification report candidate does not match model-evidence candidate")
        result["qualification"] = {
            "report_id": q.get("report_id"),
            "status": "benchmark_candidate" if not [g for g in q.get("gates", []) if not g.get("passed")] else "not_qualified",
            "policy_means": q.get("policy_means", {}),
            "failed_gates": [g.get("name") for g in q.get("gates", []) if not g.get("passed")],
        }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate fixed-panel Veritas SRE model-evaluation reports")
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
