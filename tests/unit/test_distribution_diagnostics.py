from __future__ import annotations

from investigation_world.operational_world import (
    CalibrationProfile,
    CompanySizeBand,
    IndustryFamily,
    OperationalWorldCompiler,
    OperationalWorldSpec,
    QuantileDistribution,
    RegionGroup,
    diagnose_generated_distribution,
    extract_world_metric_observations,
)


def fixed(value: float, *, observations: int = 100) -> QuantileDistribution:
    return QuantileDistribution(
        minimum=value,
        p10=value,
        p50=value,
        p90=value,
        maximum=value,
        observation_count=observations,
        source_ids=["test_source"] if observations else [],
    )


def test_extracts_procurement_metrics_with_source_semantics() -> None:
    calibration = CalibrationProfile(
        profile_id="test",
        region=RegionGroup.GLOBAL,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        state="empirical",
        source_ids=["test_source"],
        distributions={
            "procurement.items_per_tender": fixed(3),
            "procurement.parties_per_process": fixed(4),
        },
    )
    world = OperationalWorldCompiler(calibration=calibration).compile(
        OperationalWorldSpec(
            seed=71,
            employee_count=80,
            simulation_days=30,
        )
    )

    metrics = extract_world_metric_observations(world)

    assert metrics["procurement.items_per_tender"]
    assert set(metrics["procurement.items_per_tender"]) == {3.0}
    assert set(metrics["procurement.parties_per_process"]) == {4.0}
    assert metrics["firm.employee_count"] == [80.0]


def test_distribution_diagnostic_passes_exact_structural_projection() -> None:
    calibration = CalibrationProfile(
        profile_id="test",
        region=RegionGroup.GLOBAL,
        industry=IndustryFamily.GENERIC,
        size_band=CompanySizeBand.MEDIUM,
        state="empirical",
        source_ids=["test_source"],
        distributions={
            "procurement.items_per_tender": fixed(2),
            "procurement.parties_per_process": fixed(3),
        },
    )
    compiler = OperationalWorldCompiler(calibration=calibration)
    worlds = [
        compiler.compile(
            OperationalWorldSpec(
                seed=seed,
                employee_count=70,
                simulation_days=30,
            )
        )
        for seed in range(10, 15)
    ]

    report = diagnose_generated_distribution(
        worlds,
        calibration,
        metrics=["procurement.items_per_tender", "procurement.parties_per_process"],
        minimum_generated_observations=20,
        max_normalized_error=0.01,
    )

    assert report.valid, report.model_dump()
    assert report.metrics["procurement.items_per_tender"].max_normalized_error == 0
    assert report.metrics["procurement.parties_per_process"].max_normalized_error == 0


def test_diagnostic_refuses_insufficient_generated_evidence() -> None:
    calibration = CalibrationProfile(
        profile_id="test",
        state="empirical",
        distributions={"firm.employee_count": fixed(100)},
    )
    world = OperationalWorldCompiler(calibration=calibration).compile(
        OperationalWorldSpec(seed=123, employee_count=100, simulation_days=7)
    )

    report = diagnose_generated_distribution(
        [world],
        calibration,
        metrics=["firm.employee_count"],
        minimum_generated_observations=10,
    )

    assert not report.valid
    assert report.metrics["firm.employee_count"].passed is False
    assert report.errors
