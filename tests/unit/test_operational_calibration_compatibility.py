from __future__ import annotations

import pytest

from investigation_world.operational_world import (
    CompanySizeBand,
    IndustryFamily,
    OperationalWorldCompiler,
    OperationalWorldSpec,
    RegionGroup,
    build_bootstrap_calibration,
)


def test_compiler_rejects_incompatible_regional_profile() -> None:
    calibration = build_bootstrap_calibration(
        region=RegionGroup.EUROPE,
        industry=IndustryFamily.WHOLESALE_DISTRIBUTION,
        size_band=CompanySizeBand.MEDIUM,
    )
    compiler = OperationalWorldCompiler(calibration=calibration)
    with pytest.raises(ValueError, match=r"region europe is incompatible with africa"):
        compiler.compile(
            OperationalWorldSpec(
                seed=901,
                region=RegionGroup.AFRICA,
                industry=IndustryFamily.WHOLESALE_DISTRIBUTION,
                size_band=CompanySizeBand.MEDIUM,
                employee_count=80,
            )
        )


def test_global_generic_profile_can_calibrate_matching_size_world() -> None:
    calibration = build_bootstrap_calibration(size_band=CompanySizeBand.MEDIUM)
    world = OperationalWorldCompiler(calibration=calibration).compile(
        OperationalWorldSpec(
            seed=902,
            region=RegionGroup.AFRICA,
            industry=IndustryFamily.LOGISTICS,
            size_band=CompanySizeBand.MEDIUM,
            employee_count=80,
        )
    )

    # The production facade scopes every supplied calibration to the generated world
    # before compilation. The source profile remains identifiable in the deterministic
    # generation profile ID; it is not used verbatim as the effective calibration.
    assert world.calibration.profile_id == (
        f"generation-{calibration.profile_id}-{CompanySizeBand.MEDIUM.value}"
    )
    assert world.calibration.region is RegionGroup.AFRICA
    assert world.calibration.industry is IndustryFamily.LOGISTICS
    assert world.calibration.size_band is CompanySizeBand.MEDIUM
    assert world.calibration.size_scope == "exact"
    assert world.calibration.state == "bootstrap_prior"
