from __future__ import annotations

from investigation_world.operational_world import (
    DEFAULT_SOURCES,
    FusionAccumulator,
    FusionObservation,
    IndustryFamily,
    OperationalWorldCompiler,
    OperationalWorldSpec,
    RegionGroup,
    ScenarioKind,
    build_bootstrap_calibration,
    validate_operational_world,
)


def _spec(*scenarios: ScenarioKind) -> OperationalWorldSpec:
    return OperationalWorldSpec(
        seed=4242,
        region=RegionGroup.AFRICA,
        country_code="NG",
        industry=IndustryFamily.WHOLESALE_DISTRIBUTION,
        employee_count=80,
        simulation_days=30,
        scenario_types=list(scenarios),
        metadata={"currency_code": "NGN", "usd_to_local": 1500.0},
    )


def test_operational_world_is_deterministic() -> None:
    compiler = OperationalWorldCompiler()
    first = compiler.compile(_spec(ScenarioKind.DUPLICATE_INVOICE))
    second = compiler.compile(_spec(ScenarioKind.DUPLICATE_INVOICE))
    assert first.model_dump(mode="json") == second.model_dump(mode="json")


def test_procure_to_pay_references_and_integrity_hold() -> None:
    world = OperationalWorldCompiler().compile(_spec())
    report = validate_operational_world(world)
    assert report.valid, report.errors
    assert report.metrics["purchase_orders"] >= 12
    assert report.metrics["purchase_orders"] == report.metrics["invoices"]
    assert report.metrics["invoices"] == report.metrics["payments"]


def test_scenario_labels_and_private_truth_do_not_leak() -> None:
    world = OperationalWorldCompiler().compile(_spec(ScenarioKind.DUPLICATE_INVOICE))
    public = str(world.public_payload())
    assert "scenario_types" not in public
    assert ScenarioKind.DUPLICATE_INVOICE.value not in public
    assert world.ground_truth[0].finding_id not in public
    assert world.ground_truth[0].summary not in public


def test_all_scenario_families_compile_to_valid_worlds() -> None:
    compiler = OperationalWorldCompiler()
    for index, scenario in enumerate(ScenarioKind, start=1):
        spec = _spec(scenario).model_copy(update={"seed": 5000 + index})
        world = compiler.compile(spec)
        report = validate_operational_world(world)
        assert report.valid, (scenario, report.errors)
        assert len(world.ground_truth) == 1
        assert world.ground_truth[0].scenario_type == scenario
        assert world.ground_truth[0].facts
        assert world.ground_truth[0].facts[0].supporting_record_ids


def test_investigation_episode_separates_public_task_from_private_oracle() -> None:
    world, episode = OperationalWorldCompiler().compile_investigation_episode(
        _spec(ScenarioKind.PHANTOM_RECEIPT)
    )
    public = str(episode.public_payload())
    assert "oracle" not in episode.public_payload()
    assert world.ground_truth[0].finding_id not in public
    assert world.ground_truth[0].summary not in public
    assert ScenarioKind.PHANTOM_RECEIPT.value not in episode.task.objective
    assert episode.oracle.facts
    assert episode.oracle.hidden_error_id == world.ground_truth[0].finding_id


def test_fusion_registry_is_broad_and_multi_geography() -> None:
    assert len(DEFAULT_SOURCES) >= 9
    domains = {domain for source in DEFAULT_SOURCES for domain in source.domains}
    geographies = {geo for source in DEFAULT_SOURCES for geo in source.geography}
    assert {"legal_entities", "procurement", "financial_statements", "trade", "email"} <= domains
    assert {"global", "africa", "europe", "north_america"} <= geographies


def test_empirical_fusion_overrides_supported_metrics_and_preserves_fallback() -> None:
    accumulator = FusionAccumulator()
    accumulator.extend(
        FusionObservation(
            metric="procurement.purchase_orders_per_employee_year",
            value=float(value),
            source_id="test_empirical",
            region=RegionGroup.AFRICA,
        )
        for value in range(1, 31)
    )
    fallback = build_bootstrap_calibration(
        region=RegionGroup.AFRICA,
        industry=IndustryFamily.WHOLESALE_DISTRIBUTION,
    )
    profile = accumulator.build_profile(
        profile_id="test-fused",
        region=RegionGroup.AFRICA,
        industry=IndustryFamily.WHOLESALE_DISTRIBUTION,
        fallback=fallback,
        minimum_observations=20,
    )
    assert profile.state == "hybrid"
    assert profile.distributions[
        "procurement.purchase_orders_per_employee_year"
    ].observation_count == 30
    assert profile.distributions["finance.payment_lag_days"] == fallback.distributions[
        "finance.payment_lag_days"
    ]
    assert "test_empirical" in profile.source_ids
