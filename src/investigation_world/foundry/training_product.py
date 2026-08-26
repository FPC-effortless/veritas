from __future__ import annotations

from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, Field

from investigation_world.foundry.expert_trajectories import (
    ExpertTrajectory,
    PreferencePair,
    TrainingUse,
)
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
    train_splits: list[DistributionSplit] = Field(
        default_factory=lambda: [DistributionSplit.TRAIN]
    )
    heldout_splits: list[DistributionSplit] = Field(
        default_factory=lambda: [
            DistributionSplit.IID_TEST,
            DistributionSplit.OOD,
            DistributionSplit.ADVERSARIAL,
        ]
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


class PreferenceTrainingExample(BaseModel):
    example_id: str
    pair_id: str
    task_id: str
    chosen_trajectory_id: str
    rejected_trajectory_id: str
    chosen_trace_ref: str
    rejected_trace_ref: str
    score_margin: float
    capability_tags: list[str] = Field(default_factory=list)


class TrainingBundle(BaseModel):
    bundle_id: str
    recipe: TrainingRecipe
    capability_contract: CapabilityContract
    train_examples: list[TrainingExample] = Field(default_factory=list)
    preference_examples: list[PreferenceTrainingExample] = Field(default_factory=list)
    heldout_trajectory_ids: list[str] = Field(default_factory=list)
    rejected_trajectory_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainingRunManifest(BaseModel):
    run_id: str
    bundle_id: str
    trainer: TrainerKind
    base_model: str
    trainer_version: str = "unspecified"
    seed: int = 0
    parameters: dict[str, Any] = Field(default_factory=dict)


class TrainingRunResult(BaseModel):
    manifest: TrainingRunManifest
    artifact_ref: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    logs_ref: str | None = None
    post_training_evaluation_required: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class TrainerAdapter(Protocol):
    def run(self, bundle: TrainingBundle, manifest: TrainingRunManifest) -> TrainingRunResult: ...


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


def _preference_example(
    pair: PreferencePair,
    trajectories: dict[str, ExpertTrajectory],
    recipe: TrainingRecipe,
) -> PreferenceTrainingExample | None:
    chosen = trajectories.get(pair.chosen_trajectory_id)
    rejected = trajectories.get(pair.rejected_trajectory_id)
    if chosen is None or rejected is None:
        raise ValueError(f"preference pair {pair.pair_id} references an unknown trajectory")
    if chosen.split in recipe.heldout_splits or rejected.split in recipe.heldout_splits:
        return None
    if chosen.split not in recipe.train_splits or rejected.split not in recipe.train_splits:
        return None
    if TrainingUse.PREFERENCE not in chosen.training_uses:
        return None
    payload = {
        "pair_id": pair.pair_id,
        "recipe_id": recipe.recipe_id,
        "chosen_trace": chosen.source_trace_id,
        "rejected_trace": rejected.source_trace_id,
    }
    return PreferenceTrainingExample(
        example_id=f"pref-train-{stable_hash(payload)[:16]}",
        pair_id=pair.pair_id,
        task_id=pair.task_id,
        chosen_trajectory_id=chosen.trajectory_id,
        rejected_trajectory_id=rejected.trajectory_id,
        chosen_trace_ref=chosen.source_trace_id,
        rejected_trace_ref=rejected.source_trace_id,
        score_margin=pair.score_margin,
        capability_tags=pair.capability_tags,
    )


def compile_training_bundle(
    capability_contract: CapabilityContract,
    recipe: TrainingRecipe,
    trajectories: list[ExpertTrajectory],
    *,
    preference_pairs: list[PreferencePair] | None = None,
) -> TrainingBundle:
    if recipe.capability_contract_id != capability_contract.capability_id:
        raise ValueError("recipe capability_contract_id does not match capability contract")

    train_examples: list[TrainingExample] = []
    preference_examples: list[PreferenceTrainingExample] = []
    heldout: list[str] = []
    rejected: list[str] = []
    by_id = {trajectory.trajectory_id: trajectory for trajectory in trajectories}

    for trajectory in trajectories:
        if trajectory.split in recipe.heldout_splits:
            heldout.append(trajectory.trajectory_id)
            continue
        if trajectory.split not in recipe.train_splits:
            rejected.append(trajectory.trajectory_id)
            continue
        if recipe.trainer == TrainerKind.PREFERENCE:
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

    if recipe.trainer == TrainerKind.PREFERENCE:
        for pair in preference_pairs or []:
            example = _preference_example(pair, by_id, recipe)
            if example is not None:
                preference_examples.append(example)

    bundle_payload = {
        "recipe": recipe.model_dump(mode="json"),
        "train": [item.example_id for item in train_examples],
        "preference": [item.example_id for item in preference_examples],
        "heldout": heldout,
        "rejected": rejected,
    }
    return TrainingBundle(
        bundle_id=f"bundle-{stable_hash(bundle_payload)[:20]}",
        recipe=recipe,
        capability_contract=capability_contract,
        train_examples=train_examples,
        preference_examples=preference_examples,
        heldout_trajectory_ids=heldout,
        rejected_trajectory_ids=rejected,
        metadata={
            "trace_is_source_of_truth": True,
            "trainer_adapter_required": True,
            "post_training_evaluation_required": True,
            "heldout_is_never_emitted_as_training_data": True,
        },
    )
