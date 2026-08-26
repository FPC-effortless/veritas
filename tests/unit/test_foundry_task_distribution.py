from investigation_world.foundry import (
    DistributionSplit,
    GatedRewardContract,
    IntRange,
    RewardWeights,
    TaskDistributionSpec,
    gated_reward,
    sample_task_batch,
    sample_task_parameters,
)


def test_task_distribution_sampling_is_seed_deterministic():
    spec = TaskDistributionSpec(
        distribution_id="cw-train",
        split=DistributionSplit.TRAIN,
        capability_mix={"discover": 1.0, "recover": 1.0},
        task_families=["O2C_FULFILLMENT_TIMING", "PAYMENT_BLOCK_RECOVERY"],
        domain_mix={"operations": 1.0, "finance": 1.0},
    )
    first = sample_task_parameters(spec, seed=11)
    second = sample_task_parameters(spec, seed=11)
    assert first == second
    assert first.split == DistributionSplit.TRAIN
    assert first.capability_tags[0] in {"discover", "recover"}


def test_task_batch_uses_distinct_seeds():
    spec = TaskDistributionSpec(
        distribution_id="cw-ood",
        split=DistributionSplit.OOD,
        capability_mix={"reconcile": 1.0},
    )
    batch = sample_task_batch(spec, seed_start=100, count=4)
    assert [item.seed for item in batch] == [100, 101, 102, 103]
    assert len({item.sample_id for item in batch}) == 4


def test_invalid_ranges_and_mixes_fail():
    try:
        IntRange(minimum=3, maximum=1)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid range must fail")

    try:
        TaskDistributionSpec(distribution_id="x", split=DistributionSplit.TRAIN, capability_mix={})
    except ValueError:
        pass
    else:
        raise AssertionError("empty capability mix must fail")


def test_hard_invariant_failure_gates_reward_to_zero():
    contract = GatedRewardContract(hard_invariants=["authorized", "private_truth_hidden"])
    components = {"outcome":1.0,"evidence":1.0,"process":1.0,"efficiency":1.0}
    assert gated_reward(
        components,
        invariant_results={"authorized":True,"private_truth_hidden":False},
        contract=contract,
    ) == 0.0
    assert gated_reward(
        components,
        invariant_results={"authorized":True,"private_truth_hidden":True},
        contract=contract,
    ) == 1.0


def test_reward_contract_rejects_non_outcome_dominant_weights():
    try:
        GatedRewardContract(
            weights=RewardWeights(outcome=.1,evidence=.3,process=.3,efficiency=.3),
            terminal_outcome_min_share=.5,
        )
    except ValueError as exc:
        assert "terminal outcome" in str(exc)
    else:
        raise AssertionError("proxy-dominant reward contract must fail")
