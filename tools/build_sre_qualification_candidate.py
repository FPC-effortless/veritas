from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from investigation_world.qualification import (
    STATUSPAGE_INCIDENT_ENDPOINTS,
    QualificationThresholds,
    compile_sre_candidate,
    execute_sre_policy_suite,
    parse_statuspage_incidents,
    private_release_manifest,
    qualify_candidate,
)
from investigation_world.qualification.cluster_split import repartition_candidate_by_near_duplicates


def _fetch_json(url: str, timeout_s: float) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": "Veritas-SRE-Qualification/0.10"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # nosec B310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"SRE source {url} returned non-object JSON")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser(description="Acquire structured incident feeds and build a source-disjoint SRE benchmark candidate")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--early-updates", type=int, default=2)
    parser.add_argument("--random-seed", type=int, default=7)
    parser.add_argument("--version", default="sre-v1")
    parser.add_argument("--providers", nargs="*", default=None)
    args = parser.parse_args()

    providers = args.providers or list(STATUSPAGE_INCIDENT_ENDPOINTS)
    unknown = sorted(set(providers) - set(STATUSPAGE_INCIDENT_ENDPOINTS))
    if unknown:
        raise ValueError(f"unknown SRE providers: {unknown}")

    args.snapshot_dir.mkdir(parents=True, exist_ok=True)
    incidents = []
    source_summary: dict[str, Any] = {}
    for provider in providers:
        endpoint = STATUSPAGE_INCIDENT_ENDPOINTS[provider]
        payload = _fetch_json(endpoint, args.timeout)
        snapshot = args.snapshot_dir / f"{provider}-incidents.json"
        snapshot.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        parsed = parse_statuspage_incidents(provider, payload, endpoint=endpoint, early_update_count=args.early_updates)
        incidents.extend(parsed)
        source_summary[provider] = {
            "endpoint": endpoint,
            "raw_incidents": len(payload.get("incidents", [])),
            "eligible_incidents": len(parsed),
            "snapshot": str(snapshot),
        }

    candidate, cases = compile_sre_candidate(incidents, version=args.version)
    candidate, split_map = repartition_candidate_by_near_duplicates(candidate)
    cases = [case.model_copy(update={"scenario": case.scenario.model_copy(update={"split": split_map[case.scenario.scenario_id]})}) for case in cases]
    evaluations = execute_sre_policy_suite(cases, random_seed=args.random_seed)
    report = qualify_candidate(candidate, evaluations, thresholds=QualificationThresholds())
    release = private_release_manifest(candidate, report) if report.releaseable else None

    output = {
        "schema_version": "0.10.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "benchmark_candidate" if report.releaseable else "not_qualified",
        "source_summary": source_summary,
        "candidate": candidate.model_dump(mode="json"),
        "policy_evaluations": [item.model_dump(mode="json") for item in evaluations],
        "qualification": report.model_dump(mode="json"),
        "private_release_manifest": release.model_dump(mode="json") if release else None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps({
        "status": output["status"],
        "candidate_id": candidate.candidate_id,
        "report_id": report.report_id,
        "version": args.version,
        "providers": providers,
        "scenarios": len(candidate.scenarios),
        "private_test": sum(item.split.value == "private_test" for item in candidate.scenarios),
        "near_duplicate_components": candidate.metadata.get("near_duplicate_components"),
        "failed_gates": [item.name for item in report.gates if not item.passed],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
