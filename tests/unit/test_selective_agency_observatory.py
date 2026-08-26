from investigation_world.benchmark.selective_agency import (
    SelectiveAgencyAttempt,
    SelectiveAgencyDecision,
    SelectiveAgencyVerifierSignals,
    score_selective_agency,
)
from investigation_world.benchmark.selective_agency_runtime import (
    SelectiveAgencyRuntime,
    verify_selective_agency_runtime,
)
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.selective_agency_distribution import (
    SelectiveAgencyDistributionConfig,
    compile_selective_agency_distribution,
)
from investigation_world.observatory import (
    HarnessSpec,
    LongitudinalCell,
    ModelSpec,
    ScenarioPool,
    compare_runs,
    materialize_cells,
    selective_agency_capability_dimensions,
    selective_agency_capability_run,
    selective_agency_cell_matrix,
    selective_agency_scenario_ref,
    selective_agency_trace,
    selective_agency_world_ref,
)


def _bundle():
    return compile_selective_agency_distribution(
        SelectiveAgencyDistributionConfig(
            seed=23,
            train_count=20,
            iid_test_count=20,
            ood_count=20,
            adversarial_count=20,
        )
    )


def test_selective_agency_splits_map_to_observatory_exposure_pools():
    bundle = _bundle()
    by_split = {
        split: next(item for item in bundle.items if item.split == split)
        for split in DistributionSplit
    }

    assert selective_agency_scenario_ref(by_split[DistributionSplit.TRAIN]).pool == ScenarioPool.ROTATION
    assert selective_agency_scenario_ref(by_split[DistributionSplit.IID_TEST]).pool == ScenarioPool.ANCHOR
    assert selective_agency_scenario_ref(by_split[DistributionSplit.OOD]).pool == ScenarioPool.SEQUESTERED
    assert selective_agency_scenario_ref(by_split[DistributionSplit.ADVERSARIAL]).pool == ScenarioPool.SEQUESTERED


def test_selective_agency_matrix_materializes_longitudinal_cells():
    bundle = _bundle()
    spec = selective_agency_cell_matrix(
        bundle,
        models=[ModelSpec(provider="test", model_id="agent", snapshot="snapshot-a")],
        harnesses=[HarnessSpec(harness_id="test-harness", version="1")],
        time_snapshots=["2026-08-26T16:00:00+01:00"],
        splits=[DistributionSplit.IID_TEST.value],
    )
    cells = materialize_cells(spec)

    assert len(cells) == 20
    assert all(cell.world.world_id == "selective-agency" for cell in cells)
    assert all(cell.scenario.pool == ScenarioPool.ANCHOR for cell in cells)
    assert all(cell.scenario.split == DistributionSplit.IID_TEST for cell in cells)


def test_selective_agency_trace_preserves_verifier_dimensions_and_behavior():
    bundle = _bundle()
    item = next(
        item
        for item in bundle.items
        if item.split == DistributionSplit.TRAIN and item.variant == "execute"
    )
    runtime = SelectiveAgencyRuntime(item.case)
    runtime.execute(item.case.oracle.required_actions[0])
    attempt = runtime.to_attempt(SelectiveAgencyDecision.EXECUTE)
    signals = verify_selective_agency_runtime(item.case, runtime, attempt)
    score = score_selective_agency(item.case, attempt, signals)

    trace = selective_agency_trace(
        item,
        attempt,
        score,
        harness_version="1",
        taskset_version=bundle.taskset_version,
        runtime=runtime,
    )

    assert trace.total_reward == score.total_score
    assert trace.total_cost == attempt.cost
    assert trace.verifier_components["judgment"] == 1.0
    assert trace.verifier_components["action_safety"] == 1.0
    assert trace.verifier_components["harmful_action_avoidance"] == 1.0
    assert any(event.event_type.startswith("tool:") for event in trace.events)
    assert trace.events[-1].event_type == "verify_selective_agency"


def test_harm_metrics_are_oriented_higher_is_better_for_drift_analysis():
    bundle = _bundle()
    item = next(item for item in bundle.items if item.variant == "blocked")
    runtime = SelectiveAgencyRuntime(item.case)
    runtime.execute(item.case.public.available_actions[1])
    attempt = runtime.to_attempt(SelectiveAgencyDecision.EXECUTE)
    signals = verify_selective_agency_runtime(item.case, runtime, attempt)
    score = score_selective_agency(item.case, attempt, signals)
    dimensions = selective_agency_capability_dimensions(score)

    assert score.harmful_action
    assert dimensions["action_safety"] < 1.0
    assert dimensions["harmful_action_avoidance"] == 0.0
    assert dimensions["forbidden_action_avoidance"] == 0.0
    assert dimensions["unnecessary_action_avoidance"] == 0.0


def test_longitudinal_drift_detects_selective_agency_regression():
    bundle = _bundle()
    item = next(
        item
        for item in bundle.items
        if item.split == DistributionSplit.IID_TEST and item.variant == "execute"
    )
    world = selective_agency_world_ref(bundle)
    scenario = selective_agency_scenario_ref(item)
    harness = HarnessSpec(harness_id="test-harness", version="1")

    baseline_cell = LongitudinalCell(
        world=world,
        scenario=scenario,
        model=ModelSpec(provider="test", model_id="agent", snapshot="snapshot-a"),
        harness=harness,
        verifier=selective_agency_cell_matrix(
            bundle,
            models=[ModelSpec(provider="test", model_id="agent", snapshot="snapshot-a")],
            harnesses=[harness],
            time_snapshots=["2026-08-20"],
            splits=[DistributionSplit.IID_TEST.value],
        ).verifiers[0],
        time_snapshot="2026-08-20",
    )
    current_cell = LongitudinalCell(
        world=world,
        scenario=scenario,
        model=ModelSpec(provider="test", model_id="agent", snapshot="snapshot-b"),
        harness=harness,
        verifier=baseline_cell.verifier,
        time_snapshot="2026-08-26",
    )

    good_runtime = SelectiveAgencyRuntime(item.case)
    good_runtime.execute(item.case.oracle.required_actions[0])
    good_attempt = good_runtime.to_attempt(SelectiveAgencyDecision.EXECUTE)
    good_score = score_selective_agency(
        item.case,
        good_attempt,
        verify_selective_agency_runtime(item.case, good_runtime, good_attempt),
    )
    baseline = selective_agency_capability_run(
        baseline_cell,
        item,
        good_attempt,
        good_score,
        taskset_version=bundle.taskset_version,
        runtime=good_runtime,
    )

    bad_attempt = SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.NO_OP)
    bad_score = score_selective_agency(
        item.case,
        bad_attempt,
        SelectiveAgencyVerifierSignals(outcome_correct=False),
    )
    current = selective_agency_capability_run(
        current_cell,
        item,
        bad_attempt,
        bad_score,
        taskset_version=bundle.taskset_version,
    )

    report = compare_runs(baseline, current)

    assert baseline.cell.longitudinal_key == current.cell.longitudinal_key
    assert "selective_agency" in report.regressions
    assert "judgment" in report.regressions
    assert "outcome" in report.regressions
    assert report.reward_delta < 0.0
