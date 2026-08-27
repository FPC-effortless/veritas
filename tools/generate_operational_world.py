from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.operational_world import (
    CalibrationProfile,
    OperationalWorldCompiler,
    OperationalWorldSpec,
    compose_calibration_profiles,
    validate_operational_world,
)


def _load_calibration_profiles(paths: list[Path]) -> list[CalibrationProfile]:
    return [
        CalibrationProfile.model_validate_json(path.read_text(encoding="utf-8"))
        for path in paths
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Veritas operational world from a spec and one or more calibration profiles."
    )
    parser.add_argument("spec", type=Path, help="OperationalWorldSpec JSON")
    parser.add_argument(
        "--calibration",
        type=Path,
        action="append",
        default=[],
        help=(
            "Empirical/hybrid calibration JSON. Repeat the flag to compose compatible "
            "global, regional, and industry-specific calibration profiles."
        ),
    )
    parser.add_argument("--allow-bootstrap", action="store_true")
    parser.add_argument("--public-output", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    args = parser.parse_args()

    spec_payload = json.loads(args.spec.read_text(encoding="utf-8"))
    spec = OperationalWorldSpec.model_validate(spec_payload)

    calibration = None
    profiles = _load_calibration_profiles(args.calibration)
    if len(profiles) == 1:
        calibration = profiles[0]
    elif len(profiles) > 1:
        calibration = compose_calibration_profiles(
            profiles,
            profile_id=(
                f"composite-{spec.region.value}-{spec.industry.value}-{spec.size_band.value}"
            ),
            region=spec.region,
            industry=spec.industry,
            size_band=spec.size_band,
        )
    elif not args.allow_bootstrap:
        raise SystemExit(
            "Production generation requires --calibration. Repeat --calibration to fuse multiple "
            "compatible profiles. Use --allow-bootstrap only for development."
        )

    compiler = OperationalWorldCompiler(calibration=calibration)
    world = compiler.compile(spec)
    report = validate_operational_world(world)
    if not report.valid:
        raise SystemExit("world integrity validation failed: " + "; ".join(report.errors))

    args.public_output.parent.mkdir(parents=True, exist_ok=True)
    args.private_output.parent.mkdir(parents=True, exist_ok=True)
    args.public_output.write_text(
        json.dumps(world.public_payload(), indent=2, default=str), encoding="utf-8"
    )
    args.private_output.write_text(world.model_dump_json(indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "world_id": world.world_id,
                "calibration_profile": world.calibration.profile_id,
                "calibration_state": world.calibration.state,
                "calibration_sources": world.calibration.source_ids,
                "entities": report.metrics["entities"],
                "events": report.metrics["events"],
                "records": report.metrics["records"],
                "findings": report.metrics["findings"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
