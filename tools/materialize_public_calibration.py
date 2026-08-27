from __future__ import annotations

import argparse
import gzip
import json
import shutil
import tempfile
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from investigation_world.operational_world import (
    CompanySizeBand,
    FusionAccumulator,
    FusionObservation,
    IndustryFamily,
    RegionGroup,
    build_bootstrap_calibration,
    ingest_ocds_jsonl,
)


@dataclass(frozen=True)
class PublicOCDSSlice:
    source_id: str
    region: RegionGroup
    publication_id: int
    year: int

    @property
    def url(self) -> str:
        return (
            "https://data.open-contracting.org/en/publication/"
            f"{self.publication_id}/download?name={self.year}.jsonl.gz"
        )


# Deliberately use modest year slices rather than multi-hundred-megabyte all-time dumps.
# The goal is a reproducible calibration seed that can be expanded, not a hidden warehouse.
PUBLIC_OCDS_SLICES: tuple[PublicOCDSSlice, ...] = (
    PublicOCDSSlice("nigeria_nocopo", RegionGroup.AFRICA, 64, 2026),
    PublicOCDSSlice("italy_anac_ocds", RegionGroup.EUROPE, 117, 2025),
    PublicOCDSSlice("uruguay_arce_ocds", RegionGroup.LATIN_AMERICA, 43, 2026),
    PublicOCDSSlice("thailand_bma_ocds", RegionGroup.EAST_ASIA_PACIFIC, 158, 2026),
)


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Veritas-Operational-World-Calibration/1.0 (+https://github.com/FPC-effortless/veritas)"
        },
    )
    with urllib.request.urlopen(request, timeout=180) as response, destination.open("wb") as target:
        shutil.copyfileobj(response, target)


def _decompress_gzip(source: Path, destination: Path) -> None:
    with gzip.open(source, "rb") as compressed, destination.open("wb") as target:
        shutil.copyfileobj(compressed, target)


def _copy_as_global(observation: FusionObservation) -> FusionObservation:
    return observation.model_copy(update={"region": RegionGroup.GLOBAL})


def _write_profile(
    accumulator: FusionAccumulator,
    *,
    output: Path,
    profile_id: str,
    region: RegionGroup,
    balance_sources: bool = False,
) -> dict[str, object]:
    fallback = build_bootstrap_calibration(
        region=region,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
    )
    profile = accumulator.build_profile(
        profile_id=profile_id,
        region=region,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        minimum_observations=25,
        fallback=fallback,
        balance_sources=balance_sources,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")

    observed_metric_sources = {
        metric: distribution.source_ids
        for metric, distribution in profile.distributions.items()
        if distribution.observation_count > 0
    }
    return {
        "profile_id": profile.profile_id,
        "state": profile.state,
        "balance_sources": balance_sources,
        "empirical_observation_count": profile.empirical_observation_count,
        "metrics": sorted(profile.distributions),
        "observed_metric_sources": observed_metric_sources,
        "source_ids": profile.source_ids,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize small, multi-region public calibration profiles for Veritas."
    )
    parser.add_argument("--output-dir", type=Path, default=Path("calibration/public"))
    args = parser.parse_args()

    global_accumulator = FusionAccumulator()
    regional: dict[RegionGroup, FusionAccumulator] = defaultdict(FusionAccumulator)
    acquisition: list[dict[str, object]] = []
    source_observation_counts: Counter[str] = Counter()

    with tempfile.TemporaryDirectory(prefix="veritas-calibration-") as temp_dir:
        temp_root = Path(temp_dir)
        for source in PUBLIC_OCDS_SLICES:
            compressed = temp_root / f"{source.source_id}-{source.year}.jsonl.gz"
            jsonl = temp_root / f"{source.source_id}-{source.year}.jsonl"
            _download(source.url, compressed)
            _decompress_gzip(compressed, jsonl)
            observations = ingest_ocds_jsonl(
                jsonl,
                source_id=source.source_id,
                region=source.region,
            )
            regional[source.region].extend(observations)
            global_accumulator.extend(_copy_as_global(item) for item in observations)
            source_observation_counts[source.source_id] += len(observations)
            acquisition.append(
                {
                    "source_id": source.source_id,
                    "region": source.region,
                    "publication_id": source.publication_id,
                    "year": source.year,
                    "url": source.url,
                    "compressed_bytes": compressed.stat().st_size,
                    "observations": len(observations),
                }
            )

    summaries: list[dict[str, object]] = []
    summaries.append(
        _write_profile(
            global_accumulator,
            output=args.output_dir / "global-procurement-ocds-v1.json",
            profile_id="global-procurement-ocds-v1",
            region=RegionGroup.GLOBAL,
            balance_sources=True,
        )
    )
    for region, accumulator in sorted(regional.items(), key=lambda item: item[0].value):
        summaries.append(
            _write_profile(
                accumulator,
                output=args.output_dir / f"{region.value}-procurement-ocds-v1.json",
                profile_id=f"{region.value}-procurement-ocds-v1",
                region=region,
            )
        )

    manifest = {
        "format": "veritas-public-calibration-materialization-v2",
        "method": (
            "OCDS structural observations only; missing fields remain missing; currency and "
            "date-derived fields are excluded until publisher-specific normalization/quality "
            "gates are available. Global quantiles are source-balanced so each admitted "
            "publisher contributes equal total mass per metric."
        ),
        "source_observation_counts": dict(sorted(source_observation_counts.items())),
        "acquisition": acquisition,
        "profiles": summaries,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
