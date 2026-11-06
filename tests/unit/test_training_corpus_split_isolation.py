from __future__ import annotations

from investigation_world.foundry.capability_families import (
    external_investigation_capability_contract,
)
from investigation_world.foundry.external_distribution import (
    ExternalInvestigationBuildPlan,
    ExternalInvestigationWorldSpec,
    materialize_external_investigation_build_plan,
)
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.training_corpus import (
    generate_training_demonstration_set,
)
from investigation_world.world.generator import WorldGenerationConfig


def _world(split: DistributionSplit, seed: int) -> ExternalInvestigationWorldSpec:
    return ExternalInvestigationWorldSpec(
        split=split,
        world_seed=seed,
        evidence_seed=seed + 100,
        task_seed=seed + 200,
        task_count=2,
        config=WorldGenerationConfig(
            num_people=18,
            num_organizations=8,
            num_addresses=8,
            relationship_density=0.10,
            alias_rate=0.25,
            rename_rate=0.10,
            ownership_chain_depth=2,
        ),
    )


def test_training_demonstrations_never_include_heldout_splits() -> None:
    distribution = materialize_external_investigation_build_plan(
        ExternalInvestigationBuildPlan(
            distribution_id="training-corpus-split-test",
            worlds=[
                _world(DistributionSplit.TRAIN, 61_001),
                _world(DistributionSplit.IID_TEST, 62_001),
                _world(DistributionSplit.OOD, 63_001),
                _world(DistributionSplit.ADVERSARIAL, 64_001),
            ],
        )
    )
    demonstrations = generate_training_demonstration_set(
        distribution.episodes,
        capability_contract_id=external_investigation_capability_contract().capability_id,
        expert_threshold=0.70,
        include_counterfactuals=False,
    )

    assert demonstrations.trajectories
    assert all(
        trajectory.split == DistributionSplit.TRAIN
        for trajectory in demonstrations.trajectories
    )
    assert demonstrations.metadata["allowed_splits"] == ["train"]
    assert demonstrations.metadata["heldout_source_episodes_excluded"] == 6
