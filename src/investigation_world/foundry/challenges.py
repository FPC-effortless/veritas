from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from investigation_world.foundry.models import MutationKind, RolloutTrace, stable_hash


class FailureClass(StrEnum):
    EVIDENCE = "evidence"
    AUTHORITY = "authority"
    BUDGET = "budget"
    RECOVERY = "recovery"
    TEMPORAL = "temporal"
    TOOL_FAILURE = "tool_failure"
    REWARD_EXPLOIT = "reward_exploit"
    STRUCTURED_OUTPUT = "structured_output"
    UNKNOWN = "unknown"


class ChallengeSpec(BaseModel):
    challenge_id: str
    source_trace_id: str
    failure_class: FailureClass
    capability_tags: list[str] = Field(default_factory=list)
    mutations: list[MutationKind] = Field(default_factory=list)
    difficulty_delta: dict[str, float | int] = Field(default_factory=dict)
    rationale: str
    metadata: dict[str, Any] = Field(default_factory=dict)


def classify_failure(trace: RolloutTrace) -> FailureClass:
    components = {key.casefold(): value for key, value in trace.verifier_components.items()}
    reason = trace.termination_reason.casefold()
    if "exploit" in reason or components.get("exploit_resistance", 1.0) < 0.5:
        return FailureClass.REWARD_EXPLOIT
    if "parse" in reason or "structured" in reason:
        return FailureClass.STRUCTURED_OUTPUT
    if components.get("authority", 1.0) < 0.5 or "unauthorized" in reason:
        return FailureClass.AUTHORITY
    if components.get("evidence", components.get("evidence_support", 1.0)) < 0.5:
        return FailureClass.EVIDENCE
    if components.get("recovery", 1.0) < 0.5:
        return FailureClass.RECOVERY
    if components.get("temporal", 1.0) < 0.5:
        return FailureClass.TEMPORAL
    if "budget" in reason or components.get("budget", 1.0) < 0.5:
        return FailureClass.BUDGET
    if "tool" in reason or components.get("tool_reliability", 1.0) < 0.5:
        return FailureClass.TOOL_FAILURE
    return FailureClass.UNKNOWN


def challenge_from_trace(trace: RolloutTrace) -> ChallengeSpec:
    failure = classify_failure(trace)
    rules: dict[FailureClass, tuple[list[MutationKind], dict[str, float | int], str]] = {
        FailureClass.EVIDENCE: ([MutationKind.INJECT_DISTRACTOR, MutationKind.REORDER_RECORDS], {"distractors": 2}, "Increase evidence-selection pressure while preserving the answer."),
        FailureClass.AUTHORITY: ([MutationKind.PERMISSION_CHANGE], {"dependency_depth": 1}, "Require a different authority path or handoff."),
        FailureClass.BUDGET: ([MutationKind.TIGHTEN_BUDGET], {"budget_ratio": -0.15}, "Move the task toward the efficiency frontier."),
        FailureClass.RECOVERY: ([MutationKind.TOOL_FAILURE], {"stochasticity": 0.15}, "Add a recoverable tool interruption."),
        FailureClass.TEMPORAL: ([MutationKind.REORDER_RECORDS], {"dependency_depth": 1}, "Increase temporal reconstruction pressure without changing truth."),
        FailureClass.TOOL_FAILURE: ([MutationKind.TOOL_FAILURE], {"stochasticity": 0.10}, "Generate a controlled failure/retry challenge."),
        FailureClass.REWARD_EXPLOIT: ([MutationKind.INJECT_DISTRACTOR, MutationKind.REDACT_OPTIONAL_FIELD], {"adversarial_pressure": 0.20}, "Turn the observed exploit into a verifier regression challenge."),
        FailureClass.STRUCTURED_OUTPUT: ([MutationKind.REORDER_RECORDS], {"distractors": 1}, "Retest capability with varied surface form while tracking format compliance separately."),
        FailureClass.UNKNOWN: ([MutationKind.REORDER_RECORDS], {"adversarial_pressure": 0.05}, "Create a conservative surface variant for diagnosis."),
    }
    mutations, delta, rationale = rules[failure]
    challenge_id = f"CH-{stable_hash([trace.trace_id, failure.value, [item.value for item in mutations], delta])[:16].upper()}"
    return ChallengeSpec(
        challenge_id=challenge_id,
        source_trace_id=trace.trace_id,
        failure_class=failure,
        capability_tags=trace.capability_tags,
        mutations=mutations,
        difficulty_delta=delta,
        rationale=rationale,
    )
