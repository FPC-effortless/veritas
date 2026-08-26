from investigation_world.foundry.models import DistributionSplit, RolloutTrace, TraceEvent
from investigation_world.observatory import (
    CellMatrixSpec,
    ExecutionSpec,
    HarnessSpec,
    LongitudinalCell,
    ModelSpec,
    ObservatoryStore,
    ScenarioPool,
    ScenarioRef,
    VerifierSpec,
    WorldRef,
    capability_run_from_trace,
    compare_runs,
    experiment_from_matrix,
    materialize_cells,
)


def make_cell(
    snapshot: str = "2026-08-26",
    model_snapshot: str = "aug",
    seed: int = 7,
) -> LongitudinalCell:
    return LongitudinalCell(
        world=WorldRef(world_id="companyworld", version="cw-1"),
        scenario=ScenarioRef(
            scenario_id="case-7",
            seed=seed,
            pool=ScenarioPool.ANCHOR,
            task_id="task-7",
        ),
        model=ModelSpec(
            provider="lab",
            model_id="agent-model",
            snapshot=model_snapshot,
            config={"effort": "high"},
        ),
        harness=HarnessSpec(harness_id="veritas", version="h-1"),
        verifier=VerifierSpec(verifier_id="company", version="v-1"),
        execution=ExecutionSpec(tool_call_budget=100),
        time_snapshot=snapshot,
    )


def make_trace(
    reward: float = 0.8,
    precision: float = 0.9,
    cost: float = 2.0,
) -> RolloutTrace:
    return RolloutTrace(
        trace_id=f"trace-{reward}-{precision}",
        environment_version="cw-1",
        task_id="task-7",
        task_seed=7,
        split=DistributionSplit.IID_TEST,
        capability_tags=["verification"],
        taskset_version="ts-1",
        harness_version="h-1",
        runtime_version="r-1",
        initial_state_hash="s0",
        final_state_hash="s2",
        total_reward=reward,
        total_cost=cost,
        termination_reason="submitted",
        verifier_components={"evidence_precision": precision, "verification": reward},
        events=[
            TraceEvent(
                step=0,
                event_type="search",
                state_hash_before="s0",
                state_hash_after="s0",
            ),
            TraceEvent(
                step=1,
                event_type="act",
                state_hash_before="s0",
                state_hash_after="s1",
                cost=1.0,
            ),
            TraceEvent(
                step=2,
                event_type="submit",
                payload={"result": {"passed": reward > 0.5}},
                state_hash_before="s1",
                state_hash_after="s2",
                cost=1.0,
            ),
        ],
    )


def test_cell_identity_separates_snapshot_but_preserves_lineage():
    before = make_cell("2026-08-19", "jul")
    after = make_cell("2026-08-26", "aug")

    assert before.cell_id != after.cell_id
    assert before.longitudinal_key == after.longitudinal_key


def test_run_derives_capability_and_behavior():
    run = capability_run_from_trace(make_cell(), make_trace())

    assert run.capability.dimensions["evidence_precision"] == 0.9
    assert run.behavior.total_steps == 3
    assert run.behavior.state_change_rate == 2 / 3
    assert run.behavior.verification_events == 1
    assert run.behavior.tool_mix["search"] == 1 / 3


def test_compare_runs_reports_regression_and_efficiency_change():
    baseline = capability_run_from_trace(
        make_cell("2026-08-19", "jul"),
        make_trace(0.8, 0.9, 2.0),
    )
    current = capability_run_from_trace(
        make_cell("2026-08-26", "aug"),
        make_trace(0.7, 0.95, 1.5),
    )

    report = compare_runs(baseline, current)

    assert "verification" in report.regressions
    assert "evidence_precision" in report.improvements
    assert report.cost_delta == -0.5


def test_store_round_trip(tmp_path):
    run = capability_run_from_trace(make_cell(), make_trace())
    store = ObservatoryStore(tmp_path / "observatory")

    store.append(run)

    loaded = store.load()
    assert loaded == [run]
    assert store.latest_for_lineage(run.cell.longitudinal_key) == run


def test_alignment_rejects_wrong_seed():
    import pytest

    with pytest.raises(ValueError, match="scenario seed"):
        capability_run_from_trace(make_cell(seed=99), make_trace())


def test_matrix_materialization_is_cartesian_and_deterministic():
    spec = CellMatrixSpec(
        worlds=[WorldRef(world_id="companyworld", version="cw-1")],
        scenarios=[
            ScenarioRef(scenario_id="case-7", seed=7, task_id="task-7"),
            ScenarioRef(scenario_id="case-8", seed=8, task_id="task-8"),
        ],
        models=[
            ModelSpec(provider="lab", model_id="a"),
            ModelSpec(provider="lab", model_id="b"),
        ],
        harnesses=[HarnessSpec(harness_id="veritas", version="h-1")],
        verifiers=[VerifierSpec(verifier_id="company", version="v-1")],
        time_snapshots=["2026-08-26", "2026-09-02"],
    )

    first = materialize_cells(spec)
    second = materialize_cells(spec)

    assert len(first) == 8
    assert [cell.cell_id for cell in first] == [cell.cell_id for cell in second]

    experiment, cells = experiment_from_matrix("weekly drift", spec)
    assert len(experiment.cell_ids) == len(cells) == 8
