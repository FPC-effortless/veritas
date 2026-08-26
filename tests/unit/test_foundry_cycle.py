from investigation_world.foundry import (
    ChallengeValidation,
    DifficultyVector,
    DistributionSplit,
    FoundryCycleConfig,
    FoundryTaskMetadata,
    RolloutTrace,
    run_foundry_cycle,
)


def _task(task_id: str) -> FoundryTaskMetadata:
    return FoundryTaskMetadata(
        task_id=task_id,
        split=DistributionSplit.TRAIN,
        capability_tags=["evidence"],
        difficulty=DifficultyVector(),
        seed=1,
        taskset_version="t1",
        harness_version="h1",
        runtime_version="r1",
    )


def _trace(trace_id: str, task_id: str, reward: float, evidence: float) -> RolloutTrace:
    return RolloutTrace(
        trace_id=trace_id,
        environment_version="e1",
        task_id=task_id,
        task_seed=1,
        split=DistributionSplit.TRAIN,
        capability_tags=["evidence"],
        taskset_version="t1",
        harness_version="h1",
        runtime_version="r1",
        initial_state_hash="state",
        verifier_components={"evidence_support": evidence},
        total_reward=reward,
        termination_reason="submitted",
    )


def test_cycle_proposes_but_does_not_promote_unvalidated_challenge():
    tasks = [_task("T1"), _task("T2")]
    traces = [_trace("TR-FAIL", "T1", .2, 0.0), _trace("TR-PASS", "T2", 1.0, 1.0)]
    result = run_foundry_cycle(tasks, traces, config=FoundryCycleConfig(frontier_limit=2))
    assert result.trace_count == 2
    assert len(result.challenge_proposals) == 1
    assert result.promoted_challenge_ids == []
    assert result.rejected_challenge_ids == []


def test_cycle_promotes_only_challenges_that_pass_integrity_gate():
    tasks = [_task("T1")]
    traces = [_trace("TR-FAIL", "T1", .2, 0.0)]
    first = run_foundry_cycle(tasks, traces)
    challenge_id = first.challenge_proposals[0].challenge_id

    good = ChallengeValidation(
        challenge_id=challenge_id,
        leakage_count=0,
        oracle_reward=1.0,
        exploit_max_reward=.1,
        deterministic=True,
    )
    promoted = run_foundry_cycle(tasks, traces, validations=[good])
    assert promoted.promoted_challenge_ids == [challenge_id]

    bad = good.model_copy(update={"leakage_count": 1})
    rejected = run_foundry_cycle(tasks, traces, validations=[bad])
    assert rejected.rejected_challenge_ids == [challenge_id]
