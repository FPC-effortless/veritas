from investigation_world.foundry import (
    DifficultyVector, DistributionSplit, EfficiencyPoint, FoundryMetrics, FoundryTaskMetadata,
    MutationKind, RolloutTrace, TaskPerformance, TraceEvent, apply_mutation, branch_from_snapshot,
    challenge_from_trace, foundry_objective, make_snapshot, pareto_frontier, select_frontier_tasks,
)


def task(task_id: str) -> FoundryTaskMetadata:
    return FoundryTaskMetadata(
        task_id=task_id, split=DistributionSplit.TRAIN, capability_tags=["evidence"],
        difficulty=DifficultyVector(), seed=1, taskset_version="t1", harness_version="h1",
        runtime_version="r1",
    )


def test_frontier_prefers_learnable_and_unobserved_tasks():
    tasks = [task("easy"), task("frontier"), task("unseen")]
    perf = [
        TaskPerformance("easy", 10, 10, 1.0),
        TaskPerformance("frontier", 10, 4, 0.4),
    ]
    chosen = select_frontier_tasks(tasks, perf, limit=2, seed=7)
    assert "frontier" in chosen
    assert "unseen" in chosen
    assert "easy" not in chosen


def test_public_mutations_are_deterministic_and_do_not_add_private_truth():
    payload = {"task": {"task_id": "T1"}, "records": [{"record_id":"R1","fields":{"x":1}}]}
    first, lineage1 = apply_mutation(payload, task_id="T1", kind=MutationKind.INJECT_DISTRACTOR, seed=9)
    second, lineage2 = apply_mutation(payload, task_id="T1", kind=MutationKind.INJECT_DISTRACTOR, seed=9)
    assert first == second
    assert lineage1 == lineage2
    assert len(first["records"]) == 2
    text = str(first).casefold()
    assert "ground_truth" not in text and "expected_value" not in text


def test_private_fields_are_rejected_before_mutation():
    payload = {"task": {}, "oracle": {"expected_value": 1}}
    try:
        apply_mutation(payload, task_id="T", kind=MutationKind.REORDER_RECORDS, seed=1)
    except ValueError as exc:
        assert "private field" in str(exc)
    else:
        raise AssertionError("private payload must be rejected")


def test_counterfactual_branch_is_stable():
    snapshot = make_snapshot("trace-1", 3, {"balance": 4}, retain_payload=True)
    a = branch_from_snapshot(snapshot, {"action":"approve"})
    b = branch_from_snapshot(snapshot, {"action":"approve"})
    assert a.branch_id == b.branch_id
    assert a.snapshot_hash == snapshot.state_hash


def test_failure_trace_generates_targeted_challenge():
    trace = RolloutTrace(
        trace_id="TR-1", environment_version="e1", task_id="T1", task_seed=1,
        split=DistributionSplit.OOD, capability_tags=["evidence"], taskset_version="t1",
        harness_version="h1", runtime_version="r1", initial_state_hash="abc",
        events=[TraceEvent(step=0,event_type="submit")], verifier_components={"evidence_support":0.0},
        total_reward=0.2, termination_reason="submitted",
    )
    challenge = challenge_from_trace(trace)
    assert challenge.failure_class.value == "evidence"
    assert MutationKind.INJECT_DISTRACTOR in challenge.mutations


def test_foundry_objective_and_pareto_frontier():
    score = foundry_objective(FoundryMetrics(
        capability_gain=.2, transfer=.5, verifier_reliability=.99, task_coverage=.8,
        rollout_cost=2, reward_exploitability=.1, variance=.2, environment_brittleness=.1,
    ))
    assert score > 0
    p1 = EfficiencyPoint(quality=.8,cost=2,latency=2,risk=.1)
    p2 = EfficiencyPoint(quality=.7,cost=3,latency=3,risk=.2)
    assert pareto_frontier([p1,p2]) == [p1]


def test_distribution_manifest_rejects_cross_split_seed_reuse():
    from investigation_world.foundry.distributions import FoundryDistributionManifest, DistributionPartition
    try:
        FoundryDistributionManifest(
            manifest_id="M", version="1", partitions=[
                DistributionPartition(split=DistributionSplit.TRAIN, task_ids=["T1"], seeds=[1]),
                DistributionPartition(split=DistributionSplit.OOD, task_ids=["T2"], seeds=[1]),
            ]
        )
    except ValueError as exc:
        assert "seed 1 shared" in str(exc)
    else:
        raise AssertionError("cross-split seed reuse must fail")


def test_challenge_promotion_requires_integrity_gates():
    from investigation_world.foundry.promotion import ChallengeValidation, promotable
    good = ChallengeValidation(challenge_id="C1", leakage_count=0, oracle_reward=1.0, exploit_max_reward=.1, deterministic=True)
    bad = ChallengeValidation(challenge_id="C2", leakage_count=1, oracle_reward=1.0, exploit_max_reward=.1, deterministic=True)
    assert promotable(good)
    assert not promotable(bad)


def test_tracing_proxy_and_executable_prefix_replay():
    from pydantic import BaseModel
    from investigation_world.foundry.tracing import TracingRuntimeProxy, execute_counterfactual, replay_trace_prefix

    class Result(BaseModel):
        overall_reward: float = 1.0
        outcome: float = 1.0

    class FakeRuntime:
        def __init__(self):
            self.value = 0
            self.spent = 0
        def state_snapshot(self):
            return {"value": self.value}
        def budget_snapshot(self):
            return {"spent": self.spent}
        def advance(self, ticks=1):
            self.value += ticks
            self.spent += ticks
            return self.value
        def submit(self, result=None):
            return Result()

    meta = FoundryTaskMetadata(
        task_id="TRACING-TASK", split=DistributionSplit.IID_TEST,
        capability_tags=["planning"], difficulty=DifficultyVector(steps=2), seed=4,
        taskset_version="t1", harness_version="h1", runtime_version="r1",
    )
    proxy = TracingRuntimeProxy(FakeRuntime(), meta, environment_version="e1")
    proxy.advance(1)
    proxy.advance(2)
    proxy.submit(None)
    trace = proxy.trace()
    assert trace.total_reward == 1.0
    assert trace.total_cost == 3.0
    assert len(trace.events) == 3

    replayed = replay_trace_prefix(FakeRuntime(), trace, through_step=1)
    assert replayed.value == 3
    branched = execute_counterfactual(
        FakeRuntime, trace, branch_step=1, alternate_method="advance", alternate_args=[5]
    )
    assert branched.value == 6
