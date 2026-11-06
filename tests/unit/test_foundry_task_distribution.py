from investigation_world.foundry import (
    CapabilityBundle,
    GatedRewardContract,
    RewardWeights,
    TaskDistributionSpec,
    gated_reward,
    sample_task_batch,
    sample_task_parameters,
)
from investigation_world.foundry.models import DistributionSplit


def test_task_distribution_is_deterministic_and_can_sample_capability_bundles():
    spec = TaskDistributionSpec(
        distribution_id="enterprise-control",
        split=DistributionSplit.TRAIN,
        capability_bundles=[
            CapabilityBundle(tags=["discover", "interpret"], weight=1.0),
            CapabilityBundle(tags=["plan", "act", "recover"], weight=2.0),
        ],
        task_family_mix={"invoice": 1.0, "shipment": 1.0},
        domain_mix={"finance": 1.0, "operations": 1.0},
    )
    first = sample_task_parameters(spec, seed=17)
    second = sample_task_parameters(spec, seed=17)
    assert first == second
    assert len(first.capability_tags) >= 2
    assert first.task_family in {"invoice", "shipment"}
    assert first.domain in {"finance", "operations"}


def test_task_distribution_batch_uses_disjoint_deterministic_seeds():
    spec = TaskDistributionSpec(
        distribution_id="single-capability",
        split=DistributionSplit.OOD,
        capability_mix={"verify": 1.0},
    )
    batch = sample_task_batch(spec, seed_start=100, count=4)
    assert [item.seed for item in batch] == [100, 101, 102, 103]
    assert len({item.sample_id for item in batch}) == 4
    assert all(item.capability_tags == ["verify"] for item in batch)


def test_gated_reward_zeroes_hard_invariant_violations():
    contract = GatedRewardContract(hard_invariants=["authorized", "no_hidden_state_access"])
    perfect = {"outcome": 1.0, "evidence": 1.0, "process": 1.0, "efficiency": 1.0}
    assert gated_reward(
        perfect,
        invariant_results={"authorized": True, "no_hidden_state_access": False},
        contract=contract,
    ) == 0.0
    assert gated_reward(
        perfect,
        invariant_results={"authorized": True, "no_hidden_state_access": True},
        contract=contract,
    ) == 1.0


def test_reward_contract_requires_outcome_dominance():
    try:
        GatedRewardContract(
            weights=RewardWeights(outcome=0.2, evidence=0.4, process=0.2, efficiency=0.2),
            terminal_outcome_min_share=0.5,
        )
    except ValueError as exc:
        assert "terminal outcome" in str(exc)
    else:
        raise AssertionError("non-outcome-dominant reward contracts must fail")
