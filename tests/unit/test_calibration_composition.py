from __future__ import annotations

import pytest

from investigation_world.operational_world import (
    CalibrationProfile,
    CompanySizeBand,
    IndustryFamily,
    QuantileDistribution,
    RegionGroup,
    WeightedCategory,
    compose_calibration_profiles,
)


def q(value: float, *, observations: int, source: str) -> QuantileDistribution:
    return QuantileDistribution(
        minimum=value,
        p10=value,
        p50=value,
        p90=value,
        maximum=value,
        observation_count=observations,
        source_ids=[source] if observations and source else [],
    )


def test_specific_regional_empirical_metric_overrides_global_bootstrap() -> None:
    global_profile = CalibrationProfile(
        profile_id="global",
        region=RegionGroup.GLOBAL,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        state="hybrid",
        source_ids=["global_source"],
        distributions={"procurement.items_per_tender": q(1, observations=0, source="")},
    )
    africa_profile = CalibrationProfile(
        profile_id="africa",
        region=RegionGroup.AFRICA,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        state="empirical",
        source_ids=["nigeria_nocopo"],
        distributions={
            "procurement.items_per_tender": q(
                4, observations=230, source="nigeria_nocopo"
            )
        },
    )

    composite = compose_calibration_profiles(
        [global_profile, africa_profile],
        profile_id="africa-composite",
        region=RegionGroup.AFRICA,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
    )

    assert composite.distributions["procurement.items_per_tender"].p50 == 4
    assert composite.distributions["procurement.items_per_tender"].source_ids == [
        "nigeria_nocopo"
    ]


def test_industry_specific_profile_overrides_generic_metric() -> None:
    generic = CalibrationProfile(
        profile_id="generic",
        region=RegionGroup.EUROPE,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        state="empirical",
        distributions={"sales.line_items_per_invoice": q(2, observations=1000, source="a")},
    )
    retail = CalibrationProfile(
        profile_id="retail",
        region=RegionGroup.EUROPE,
        industry=IndustryFamily.RETAIL,
        size_band=CompanySizeBand.MEDIUM,
        state="empirical",
        source_ids=["online_retail_ii"],
        distributions={
            "sales.line_items_per_invoice": q(
                11, observations=100, source="online_retail_ii"
            )
        },
        categories={
            "sales.invoice_status": WeightedCategory(
                weights={"completed": 0.92, "cancelled": 0.08},
                observation_count=100,
                source_ids=["online_retail_ii"],
            )
        },
    )

    composite = compose_calibration_profiles(
        [generic, retail],
        profile_id="eu-retail",
        region=RegionGroup.EUROPE,
        industry=IndustryFamily.RETAIL,
        size_band=CompanySizeBand.MEDIUM,
    )

    assert composite.distributions["sales.line_items_per_invoice"].p50 == 11
    assert "sales.invoice_status" in composite.categories


def test_size_agnostic_profile_can_compose_into_large_world() -> None:
    entity_shape = CalibrationProfile(
        profile_id="global-entity-shape",
        region=RegionGroup.GLOBAL,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        size_scope="agnostic",
        state="empirical",
        distributions={
            "organization.other_names_count": q(1, observations=500, source="gleif_lei")
        },
        source_ids=["gleif_lei"],
    )

    composite = compose_calibration_profiles(
        [entity_shape],
        profile_id="large-with-entity-shape",
        region=RegionGroup.NORTH_AMERICA,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.LARGE,
    )

    assert composite.size_band == CompanySizeBand.LARGE
    assert composite.size_scope == "exact"
    assert composite.distributions["organization.other_names_count"].p50 == 1


def test_incompatible_region_is_rejected() -> None:
    profile = CalibrationProfile(
        profile_id="eu",
        region=RegionGroup.EUROPE,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
    )
    with pytest.raises(ValueError, match="region"):
        compose_calibration_profiles(
            [profile],
            profile_id="bad",
            region=RegionGroup.AFRICA,
            industry=IndustryFamily.GENERIC,
            size_band=CompanySizeBand.MEDIUM,
        )


def test_incompatible_size_band_is_rejected() -> None:
    profile = CalibrationProfile(
        profile_id="medium",
        size_band=CompanySizeBand.MEDIUM,
    )
    with pytest.raises(ValueError, match="size band"):
        compose_calibration_profiles(
            [profile],
            profile_id="bad",
            region=RegionGroup.GLOBAL,
            industry=IndustryFamily.GENERIC,
            size_band=CompanySizeBand.LARGE,
        )
