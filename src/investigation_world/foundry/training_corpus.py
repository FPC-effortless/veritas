from __future__ import annotations

from investigation_world.foundry.expert_trajectories import DemonstrationSet
from investigation_world.foundry.external_runtime import ExternalInvestigationEpisode
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.observable_expert_policy import (
    ObservableOracleExpertPolicy,
)
from investigation_world.foundry.trajectory_generation import (
    ExternalInvestigationPolicy,
    generate_demonstration_set,
)


def generate_training_demonstration_set(
    episodes: list[ExternalInvestigationEpisode],
    *,
    capability_contract_id: str,
    version: str = "1",
    policy: ExternalInvestigationPolicy | None = None,
    expert_threshold: float = 0.8,
    include_counterfactuals: bool = True,
    maximum_episodes: int | None = None,
) -> DemonstrationSet:
    """Generate privileged, observation-complete demonstrations from TRAIN worlds only.

    Held-out IID/OOD/adversarial worlds must never be passed through the oracle-backed
    reference policy as part of the training-corpus pipeline. They remain available for
    independent evaluation and diagnostic verification through separate workflows.
    """
    all_train_episodes = [
        episode
        for episode in episodes
        if episode.metadata.split == DistributionSplit.TRAIN
    ]
    train_episodes = list(all_train_episodes)
    if maximum_episodes is not None:
        train_episodes = train_episodes[:maximum_episodes]
    if not train_episodes:
        raise ValueError("training demonstration generation requires TRAIN episodes")

    selected_policy = policy or ObservableOracleExpertPolicy()
    demonstrations = generate_demonstration_set(
        train_episodes,
        capability_contract_id=capability_contract_id,
        version=version,
        policy=selected_policy,
        expert_threshold=expert_threshold,
        include_counterfactuals=include_counterfactuals,
        maximum_episodes=None,
    )
    if any(
        trajectory.split != DistributionSplit.TRAIN
        for trajectory in demonstrations.trajectories
    ):
        raise RuntimeError("held-out trajectory entered training demonstration corpus")

    return demonstrations.model_copy(
        update={
            "metadata": {
                **demonstrations.metadata,
                "training_corpus": True,
                "allowed_splits": [DistributionSplit.TRAIN.value],
                "heldout_source_episodes_excluded": len(episodes)
                - len(all_train_episodes),
                "train_source_episodes_truncated": len(all_train_episodes)
                - len(train_episodes),
                "observation_complete_reference_policy": selected_policy.policy_id,
            }
        }
    )


__all__ = ["generate_training_demonstration_set"]
