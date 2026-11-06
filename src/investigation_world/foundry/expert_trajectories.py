from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from investigation_world.foundry.models import DistributionSplit, RolloutTrace, stable_hash


class TrajectoryRole(StrEnum):
    EXPERT = "expert"
    RECOVERY = "recovery"
    COUNTERFACTUAL = "counterfactual"
    FAILURE = "failure"
    PREFERENCE_CHOSEN = "preference_chosen"
    PREFERENCE_REJECTED = "preference_rejected"


class TrainingUse(StrEnum):
    SFT = "sft"
    PREFERENCE = "preference"
    RL = "rl"
    VOPSD = "vopsd"
    EVAL_ONLY = "eval_only"


class ExpertiseAssessment(BaseModel):
    verifier_score: float
    invariant_pass: bool = True
    terminal_success: bool = False
    efficiency_score: float | None = None
    recovery_success: bool | None = None
    evidence_quality: float | None = None
    rationale: list[str] = Field(default_factory=list)


class VerifiedTrajectory(BaseModel):
    trajectory_id: str
    source_trace_id: str
    task_id: str
    split: DistributionSplit
    capability_tags: list[str] = Field(default_factory=list)
    role: TrajectoryRole
    assessment: ExpertiseAssessment
    training_uses: list[TrainingUse] = Field(default_factory=list)
    trace: RolloutTrace
    annotations: dict[str, Any] = Field(default_factory=dict)


class ExpertTrajectory(VerifiedTrajectory):
    pass


class PreferencePair(BaseModel):
    pair_id: str
    task_id: str
    chosen_trajectory_id: str
    rejected_trajectory_id: str
    reason: str
    score_margin: float
    capability_tags: list[str] = Field(default_factory=list)


class DemonstrationSet(BaseModel):
    dataset_id: str
    version: str
    capability_contract_id: str
    trajectories: list[VerifiedTrajectory] = Field(default_factory=list)
    preference_pairs: list[PreferencePair] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


def assess_trace(
    trace: RolloutTrace,
    *,
    min_verifier_score: float = 0.8,
    require_success: bool = True,
    success_score_threshold: float | None = None,
) -> ExpertiseAssessment:
    verifier_score = float(trace.verifier_components.get("outcome", trace.total_reward))
    explicit_terminal = trace.metadata.get("terminal_success")
    if explicit_terminal is None:
        terminal_success = trace.termination_reason in {"success", "verified", "completed"}
        if success_score_threshold is not None:
            terminal_success = terminal_success or verifier_score >= success_score_threshold
    else:
        terminal_success = bool(explicit_terminal)
    invariant_pass = bool(trace.metadata.get("invariant_pass", True))
    rationale: list[str] = []
    if verifier_score < min_verifier_score:
        rationale.append("verifier score below expert threshold")
    if require_success and not terminal_success:
        rationale.append("trajectory did not reach a verified terminal success")
    if not invariant_pass:
        rationale.append("hard invariant failed")
    return ExpertiseAssessment(
        verifier_score=verifier_score,
        invariant_pass=invariant_pass,
        terminal_success=terminal_success,
        efficiency_score=trace.metadata.get("efficiency_score"),
        recovery_success=trace.metadata.get("recovery_success"),
        evidence_quality=trace.metadata.get("evidence_quality"),
        rationale=rationale,
    )


def curate_verified_trace(
    trace: RolloutTrace,
    *,
    role: TrajectoryRole,
    training_uses: list[TrainingUse] | None = None,
    annotations: dict[str, Any] | None = None,
) -> VerifiedTrajectory:
    assessment = assess_trace(
        trace,
        min_verifier_score=0.8,
        require_success=False,
        success_score_threshold=None,
    )
    uses = training_uses or [TrainingUse.EVAL_ONLY]
    payload = {
        "trace_id": trace.trace_id,
        "role": role.value,
        "uses": [item.value for item in uses],
        "verifier_score": assessment.verifier_score,
    }
    return VerifiedTrajectory(
        trajectory_id=f"verified-{stable_hash(payload)[:16]}",
        source_trace_id=trace.trace_id,
        task_id=trace.task_id,
        split=trace.split,
        capability_tags=trace.capability_tags,
        role=role,
        assessment=assessment,
        training_uses=uses,
        trace=trace,
        annotations=annotations or {},
    )


def qualify_expert_trace(
    trace: RolloutTrace,
    *,
    role: TrajectoryRole = TrajectoryRole.EXPERT,
    min_verifier_score: float = 0.8,
    require_success: bool = True,
    training_uses: list[TrainingUse] | None = None,
    annotations: dict[str, Any] | None = None,
) -> ExpertTrajectory:
    assessment = assess_trace(
        trace,
        min_verifier_score=min_verifier_score,
        require_success=require_success,
        success_score_threshold=min_verifier_score,
    )
    if assessment.rationale:
        raise ValueError("trace is not expert-qualified: " + "; ".join(assessment.rationale))
    uses = training_uses or [TrainingUse.SFT, TrainingUse.RL, TrainingUse.VOPSD]
    payload = {
        "trace_id": trace.trace_id,
        "role": role.value,
        "uses": [item.value for item in uses],
        "verifier_score": assessment.verifier_score,
    }
    return ExpertTrajectory(
        trajectory_id=f"expert-{stable_hash(payload)[:16]}",
        source_trace_id=trace.trace_id,
        task_id=trace.task_id,
        split=trace.split,
        capability_tags=trace.capability_tags,
        role=role,
        assessment=assessment,
        training_uses=uses,
        trace=trace,
        annotations=annotations or {},
    )


def make_preference_pair(
    chosen: VerifiedTrajectory,
    rejected: VerifiedTrajectory,
    *,
    reason: str,
) -> PreferencePair:
    if chosen.task_id != rejected.task_id:
        raise ValueError("preference trajectories must come from the same task")
    margin = chosen.assessment.verifier_score - rejected.assessment.verifier_score
    if margin <= 0:
        raise ValueError("chosen trajectory must have a strictly higher verifier score")
    pair_payload = {
        "task_id": chosen.task_id,
        "chosen": chosen.trajectory_id,
        "rejected": rejected.trajectory_id,
        "reason": reason,
    }
    return PreferencePair(
        pair_id=f"pref-{stable_hash(pair_payload)[:16]}",
        task_id=chosen.task_id,
        chosen_trajectory_id=chosen.trajectory_id,
        rejected_trajectory_id=rejected.trajectory_id,
        reason=reason,
        score_margin=margin,
        capability_tags=sorted(set(chosen.capability_tags) | set(rejected.capability_tags)),
    )
