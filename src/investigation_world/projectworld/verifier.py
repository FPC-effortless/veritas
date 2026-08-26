from __future__ import annotations

from collections import defaultdict
from typing import Any

from investigation_world.projectworld.models import (
    ConditionOperator,
    OperationalProjectEpisode,
    OperationalProjectVerificationResult,
    ProjectActionExecution,
    ProjectActionType,
    ProjectOutcomeCondition,
    ProjectStateValue,
    ProjectSystemEvent,
    VerificationDimension,
)


def _condition_met(
    condition: ProjectOutcomeCondition,
    state: dict[tuple[str, str, str], ProjectStateValue],
) -> bool:
    item = state.get(condition.key())
    value = None if item is None else item.value
    expected = condition.expected_value
    op = condition.operator
    if op == ConditionOperator.EXISTS:
        return item is not None
    if op == ConditionOperator.EQ:
        return value == expected
    if op == ConditionOperator.NE:
        return value != expected
    if op == ConditionOperator.IN:
        return value in expected if expected is not None else False
    if op == ConditionOperator.NOT_IN:
        return value not in expected if expected is not None else True
    if value is None:
        return False
    try:
        if op == ConditionOperator.LTE:
            return value <= expected
        if op == ConditionOperator.GTE:
            return value >= expected
        if op == ConditionOperator.LT:
            return value < expected
        if op == ConditionOperator.GT:
            return value > expected
    except TypeError:
        return False
    return False


def _clamp(value: float) -> float:
    return min(1.0, max(0.0, value))


def verify_operational_project(
    episode: OperationalProjectEpisode,
    *,
    state: list[ProjectStateValue],
    journal: list[ProjectActionExecution],
    events: list[ProjectSystemEvent],
    ticks_used: int,
    committed_cost: float,
) -> OperationalProjectVerificationResult:
    """Score project outcome from private ground truth plus execution invariants."""
    state_index = {item.key(): item for item in state}
    dimension_hits: dict[VerificationDimension, float] = defaultdict(float)
    dimension_totals: dict[VerificationDimension, float] = defaultdict(float)
    critical_failures = 0
    for condition in episode.oracle.outcome_conditions:
        dimension_totals[condition.dimension] += condition.weight
        if _condition_met(condition, state_index):
            dimension_hits[condition.dimension] += condition.weight
        elif condition.critical:
            critical_failures += 1

    dimensions = set(VerificationDimension) | set(dimension_totals)
    dimension_scores: dict[VerificationDimension, float] = {}
    for dimension in dimensions:
        total = dimension_totals.get(dimension, 0.0)
        dimension_scores[dimension] = 1.0 if total == 0 else dimension_hits[dimension] / total

    weighted_total = 0.0
    weighted_hit = 0.0
    for dimension, score in dimension_scores.items():
        weight = episode.oracle.dimension_weights.get(dimension, 1.0)
        weighted_total += weight
        weighted_hit += weight * score
    outcome_score = weighted_hit / weighted_total if weighted_total else 0.0

    unauthorized_attempts = sum(1 for item in journal if not item.authorized)
    prerequisite_violations = sum(
        1 for item in journal if item.authorized and not item.prerequisites_met
    )
    resource_conflicts = sum(
        1
        for item in journal
        if item.authorized
        and item.prerequisites_met
        and item.evidence_sufficient
        and not item.resource_feasible
    )
    evidence_failures = sum(
        1
        for item in journal
        if item.authorized and item.prerequisites_met and not item.evidence_sufficient
    )
    rework_events = sum(
        1
        for item in journal
        if item.applied
        and item.action.action_type
        in {
            ProjectActionType.REJECT_DESIGN,
            ProjectActionType.REJECT_WORK,
            ProjectActionType.REJECT_CHANGE_ORDER,
            ProjectActionType.COMPENSATE_ACTION,
        }
    )
    irreversible_errors = sum(
        1
        for item in journal
        if item.irreversible
        and item.applied
        and item.action.action_type != ProjectActionType.ACCEPT_PROJECT
    )

    allowed_unauthorized = episode.oracle.maximum_unauthorized_attempts
    authority_score = _clamp(1.0 - max(0, unauthorized_attempts - allowed_unauthorized) * 0.2)
    process_errors = prerequisite_violations + resource_conflicts
    process_score = _clamp(1.0 - process_errors * 0.12)
    evidence_score = _clamp(1.0 - evidence_failures * 0.15)

    budget_limit = episode.task.budget_limit
    if budget_limit <= 0:
        budget_score = 1.0
    elif committed_cost <= budget_limit:
        budget_score = _clamp(1.0 - 0.15 * (committed_cost / budget_limit))
    else:
        budget_score = _clamp(1.0 - (committed_cost - budget_limit) / budget_limit)

    max_ticks = episode.task.max_ticks
    schedule_score = _clamp(1.0 - max(0, ticks_used - max_ticks) / max(1, max_ticks))
    critical_penalty = min(0.75, critical_failures * 0.25)
    rework_penalty = min(
        0.25,
        max(0, rework_events - episode.oracle.maximum_rework_events) * 0.05,
    )
    irreversible_penalty = min(0.5, irreversible_errors * 0.15)

    overall_reward = (
        0.58 * outcome_score
        + 0.10 * authority_score
        + 0.10 * process_score
        + 0.07 * evidence_score
        + 0.08 * budget_score
        + 0.07 * schedule_score
        - critical_penalty
        - rework_penalty
        - irreversible_penalty
    )
    overall_reward = _clamp(overall_reward)

    return OperationalProjectVerificationResult(
        dimension_scores=dimension_scores,
        outcome_score=outcome_score,
        authority_score=authority_score,
        process_score=process_score,
        evidence_score=evidence_score,
        budget_score=budget_score,
        schedule_score=schedule_score,
        unauthorized_attempts=unauthorized_attempts,
        prerequisite_violations=prerequisite_violations,
        resource_conflicts=resource_conflicts,
        evidence_failures=evidence_failures,
        rework_events=rework_events,
        irreversible_errors=irreversible_errors,
        ticks_used=ticks_used,
        committed_cost=committed_cost,
        overall_reward=overall_reward,
    )
