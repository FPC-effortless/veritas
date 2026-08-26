from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from investigation_world.foundry.expert_trajectories import ExpertTrajectory, TrainingUse
from investigation_world.foundry.models import CapabilityContract, DistributionSplit, stable_hash


class TrainerKind(StrEnum):
    SFT = "sft"
    PREFERENCE = "preference"
    RL = "rl"
    VOPSD = "vopsd"


class TrainingRecipe(BaseModel):
    recipe_id: str
    version: str = "1"
    trainer: TrainerKind
    capability_contract_id: str
    train_splits: list[DistributionSplit] = Field(default_factory=lambda: [DistributionSplit.TRAIN])
    heldout_splits: list[DistributionSplit] = Field(
        default_factory=lambda: [DistributionSplit.IID_TEST, DistributionSplit.OOD, DistributionSplit.ADVERSARIAL]
    )
    minimum_verifier_score: float = Field(default=0.8, ge=0.0)
    require_invariant_pass: bool = True
    require_verified_terminal_success: bool = True
    parameters: dict[str, Any] = Field(default_factory=dict)


class TrainingExample(BaseModel):
    example_id: str
    trajectory_id: str
    task_id: str
    split: DistributionSplit
    capability_tags: list[str] = Field(default_factory=list)
    trainer: TrainerKind
    trace_ref: str
    verifier_score: float
    payload: dict[str, Any] = Field(default_factory=dict)


class TrainingBundle(BaseModel):
    bundle_id: str
    recipe: TrainingRecipe
    capability_contract: CapabilityContract
    train_examples: list[TrainingExample] = Field(default_factory=list)
    heldout_trajectory_ids: list[str] = Field(default_factory=list)
    rejected_trajectory_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def _required_use(trainer: TrainerKind) -> TrainingUse:
    return {
        TrainerKind.SFT: TrainingUse.SFT,
        TrainerKind.PREFERENCE: TrainingUse.PREFERENCE,
        TrainerKind.RL: TrainingUse.RL,
        TrainerKind.VOPSD: TrainingUse.VOPSD,
    }[trainer]


def _eligible(trajectory: ExpertTrajectory, recipe: TrainingRecipe) -> tuple[bool, str | None]:
    assessment = trajectory.assessment
    if assessment.verifier_score < recipe.minimum_verifier_score:
        return False, "verifier_score"
    if recipe.require_invariant_pass and not assessment.invariant_pass:
        return False, "invariant"
    if recipe.require_verified_terminal_success and not assessment.terminal_success:
        return False, "terminal_success"
    if _required_use(recipe.trainer) not in trajectory.training_uses:
        return False, "training_use"
    return True, None


def compile_training_bundle(
    capability_contract: CapabilityContract,
    recipe: TrainingRecipe,
    trajectories: list[ExpertTrajectory],
) -> TrainingBundle:
    if recipe.capability_contract_id != capability_contract.capability_id:
        raise ValueError("recipe capability_contract_id does not match capability contract")

    train_examples: list[TrainingExample] = []
    heldout: list[str] = []
    rejected: list[str] = []

    for trajectory in trajectories:
        if trajectory.split in recipe.heldout_splits:
            heldout.append(trajectory.trajectory_id)
            continue
        if trajectory.split not in recipe.train_splits:
            rejected.append(trajectory.trajectory_id)
            continue
        eligible, _ = _eligible(trajectory, recipe)
        if not eligible:
            rejected.append(trajectory.trajectory_id)
            continue
        example_payload = {
            "trace_id": trajectory.source_trace_id,
            "role": trajectory.role.value,
            "annotations": trajectory.annotations,
        }
        example_id = f"train-{stable_hash({'trajectory': trajectory.trajectory_id, 'recipe': recipe.recipe_id})[:16]}"
        train_examples.append(
            TrainingExample(
                example_id=example_id,
                trajectory_id=trajectory.trajectory_id,
                task_id=trajectory.task_id,
                split=trajectory.split,
                capability_tags=trajectory.capability_tags,
                trainer=recipe.trainer,
                trace_ref=trajectory.source_trace_id,
                verifier_score=trajectory.assessment.verifier_score,
                payload=example_payload,
            )
        )

    bundle_payload = {
        "recipe": recipe.model_dump(mode="json"),
        "train": [item.example_id for item in train_examples],
        "heldout": heldout,
        "rejected": rejected,
    }
    return TrainingBundle(
        bundle_id=f"bundle-{stable_hash(bundle_payload)[:20]}",
        recipe=recipe,
        capability_contract=capability_contract,
        train_examples=train_examples,
        heldout_trajectory_ids=heldout,
        rejected_trajectory_ids=rejected,
        metadata={
            "trace_is_source_of_truth": True,
            "trainer_adapter_required": True,
            "heldout_is_never_emitted_as_training_data": True,
        },
    )
