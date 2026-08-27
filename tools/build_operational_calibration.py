from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.operational_world import (
    CompanySizeBand,
    FusionAccumulator,
    IndustryFamily,
    RegionGroup,
    build_bootstrap_calibration,
    ingest_numeric_csv,
    ingest_ocds_jsonl,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build a provenance-bearing Veritas operational-world calibration profile."
    )
    parser.add_argument("manifest", type=Path, help="Fusion input manifest JSON")
    parser.add_argument("--output", type=Path, required=True, help="Output profile JSON")
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    region = RegionGroup(manifest.get("region", "global"))
    industry = IndustryFamily(manifest.get("industry", "generic"))
    size_band = CompanySizeBand(manifest.get("size_band", "medium"))
    accumulator = FusionAccumulator()

    for item in manifest.get("inputs", []):
        kind = item["kind"]
        item_region = RegionGroup(item.get("region", region))
        if kind == "ocds_jsonl":
            accumulator.extend(
                ingest_ocds_jsonl(
                    item["path"],
                    source_id=item["source_id"],
                    region=item_region,
                )
            )
        elif kind == "numeric_csv":
            accumulator.extend(
                ingest_numeric_csv(
                    item["path"],
                    source_id=item["source_id"],
                    metric_columns=item["metric_columns"],
                    region=item_region,
                    industry=IndustryFamily(item.get("industry", industry)),
                )
            )
        else:
            raise ValueError(f"unsupported fusion input kind: {kind}")

    fallback = build_bootstrap_calibration(
        region=region,
        industry=industry,
        size_band=size_band,
    )
    profile = accumulator.build_profile(
        profile_id=manifest["profile_id"],
        region=region,
        industry=industry,
        size_band=size_band,
        minimum_observations=int(manifest.get("minimum_observations", 20)),
        fallback=fallback,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "profile_id": profile.profile_id,
                "state": profile.state,
                "empirical_observation_count": profile.empirical_observation_count,
                "metrics": len(profile.distributions),
                "source_ids": profile.source_ids,
                "output": str(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
