from investigation_world.foundry.models import DistributionSplit, RolloutTrace, TraceEvent
from investigation_world.observatory import (
    CallableHarnessAdapter,
    CallableModelProvider,
    CallableRuntimeFactory,
    ExecutionRegistry,
    ExperimentSpec,
    HarnessRunResult,
    HarnessSpec,
    JobStatus,
    LocalObservatoryScheduler,
    LongitudinalCell,
    ModelResponse,
    ModelSpec,
    ObservatoryExecutionEngine,
    ObservatoryStore,
    ProviderUsage,
    ScenarioPool,
    ScenarioRef,
    SchedulerPolicy,
    VerifierSpec,
    WorldRef,
)


def make_cell(seed: int = 1, *, pool: ScenarioPool = ScenarioPool.ANCHOR) -> LongitudinalCell:
    return LongitudinalCell(
        world=WorldRef(world_id="companyworld", version="cw-1"),
        scenario=ScenarioRef(
            scenario_id=f"case-{seed}",
            seed=seed,
            pool=pool,
            split=DistributionSplit.IID_TEST,
            task_id=f"task-{seed}",
        ),
        model=ModelSpec(provider="test-provider", model_id="agent-model", snapshot="aug"),
        harness=HarnessSpec(harness_id="test-harness", version="h-1"),
        verifier=VerifierSpec(verifier_id="company", version="v-1"),
        time_snapshot="2026-08-26",
    )


def make_trace(cell: LongitudinalCell) -> RolloutTrace:
    return RolloutTrace(
        trace_id=f"trace-{cell.scenario.seed}",
        environment_version=cell.world.version,
        task_id=cell.scenario.task_id or "unknown",
        task_seed=cell.scenario.seed,
        split=DistributionSplit.IID_TEST,
        capability_tags=["verification"],
        taskset_version="ts-1",
        harness_version=cell.harness.version,
        runtime_version="runtime-1",
        initial_state_hash="s0",
        final_state_hash="s1",
        total_reward=0.8,
        total_cost=0.25,
        termination_reason="submitted",
        verifier_components={"verification": 0.8},
        events=[
            TraceEvent(
                step=0,
                event_type="submit",
                state_hash_before="s0",
                state_hash_after="s1",
            )
        ],
    )


def make_registry(harness_function) -> ExecutionRegistry:
    registry = ExecutionRegistry()

    def provider(request):
        return ModelResponse(
            request_id=request.request_id,
            output={"decision": "continue"},
            usage=ProviderUsage(
                input_tokens=12,
                output_tokens=4,
                total_tokens=16,
                cost=0.01,
            ),
        )

    registry.providers.register(CallableModelProvider("test-provider", provider))
    registry.harnesses.register(
        CallableHarnessAdapter("test-harness", "h-1", harness_function)
    )
    registry.runtimes.register(
        CallableRuntimeFactory(
            "companyworld",
            "cw-1",
            lambda cell: {"seed": cell.scenario.seed},
        )
    )
    return registry


def test_execution_engine_instruments_provider_and_persists(tmp_path):
    def harness(cell, provider, runtime):
        response = provider.generate({"observation": runtime})
        assert response.output["decision"] == "continue"
        return HarnessRunResult(trace=make_trace(cell), metadata={"runtime_seed": runtime["seed"]})

    store = ObservatoryStore(tmp_path / "observatory")
    engine = ObservatoryExecutionEngine(make_registry(harness), store=store)
    cell = make_cell()

    run = engine.execute_cell(cell)

    assert run.metadata["runtime_seed"] == 1
    assert run.metadata["provider_session"]["calls"] == 1
    assert run.metadata["provider_session"]["total_tokens"] == 16
    assert run.metadata["provider_session"]["cost"] == 0.01
    assert store.has_run(run.run_id)
    assert store.latest_for_cell(cell.cell_id) == run


def test_scheduler_retries_filters_pools_and_skips_completed_cells(tmp_path):
    attempts: dict[str, int] = {}

    def harness(cell, provider, runtime):
        attempts[cell.cell_id] = attempts.get(cell.cell_id, 0) + 1
        provider.generate({"seed": runtime["seed"]})
        if cell.scenario.seed == 2 and attempts[cell.cell_id] == 1:
            raise RuntimeError("transient harness failure")
        return make_trace(cell)

    store = ObservatoryStore(tmp_path / "observatory")
    engine = ObservatoryExecutionEngine(make_registry(harness), store=store)
    scheduler = LocalObservatoryScheduler(engine)
    cells = [
        make_cell(1),
        make_cell(2),
        make_cell(3, pool=ScenarioPool.SEQUESTERED),
    ]
    experiment = ExperimentSpec(name="anchor regression", cell_ids=[cell.cell_id for cell in cells])
    policy = SchedulerPolicy(
        max_workers=2,
        max_attempts=2,
        pools={ScenarioPool.ANCHOR},
    )

    report = scheduler.run(experiment, cells, policy=policy)

    assert report.planned == 2
    assert report.succeeded == 2
    assert report.failed == 0
    assert report.skipped == 0
    assert attempts[cells[1].cell_id] == 2
    assert all(outcome.status == JobStatus.SUCCEEDED for outcome in report.outcomes)

    repeated = scheduler.run(experiment, cells, policy=policy)

    assert repeated.planned == 2
    assert repeated.succeeded == 0
    assert repeated.skipped == 2
    assert all(outcome.attempts == 0 for outcome in repeated.outcomes)


def test_scheduler_isolates_per_cell_failure(tmp_path):
    def harness(cell, provider, runtime):
        if cell.scenario.seed == 2:
            raise ValueError("permanent failure")
        return make_trace(cell)

    store = ObservatoryStore(tmp_path / "observatory")
    engine = ObservatoryExecutionEngine(make_registry(harness), store=store)
    scheduler = LocalObservatoryScheduler(engine)
    cells = [make_cell(1), make_cell(2)]
    experiment = ExperimentSpec(name="failure isolation", cell_ids=[cell.cell_id for cell in cells])

    report = scheduler.run(
        experiment,
        cells,
        policy=SchedulerPolicy(max_workers=2, max_attempts=2),
    )

    assert report.succeeded == 1
    assert report.failed == 1
    failure = next(outcome for outcome in report.outcomes if outcome.status == JobStatus.FAILED)
    assert failure.error_type == "ValueError"
    assert failure.attempts == 2
