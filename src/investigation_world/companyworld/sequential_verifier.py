from __future__ import annotations

from math import isclose
from typing import Any

from investigation_world.companyworld.interactive_models import StateValue
from investigation_world.companyworld.sequential_models import (
    SequentialActionExecution,
    SequentialCompanyWorldEpisode,
    SequentialCompanyWorldVerificationResult,
)
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.core.models import InvestigationResult


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return isclose(float(expected), float(actual), rel_tol=1e-6, abs_tol=1e-2)
    if expected is None or actual is None:
        return expected is actual
    return str(expected).strip().casefold() == str(actual).strip().casefold()


def _condition_score(conditions, state_index: dict[tuple[str, str, str], Any]) -> float:
    if not conditions:
        return 0.0
    matched = sum(
        1
        for condition in conditions
        if condition.key() in state_index
        and _same(condition.expected_value, state_index[condition.key()])
    )
    return matched / len(conditions)


def verify_sequential_companyworld(
    result: InvestigationResult,
    episode: SequentialCompanyWorldEpisode,
    *,
    state: list[StateValue],
    journal: list[SequentialActionExecution],
    ticks_used: int = 0,
    budget_spent: int = 0,
    budget_total: int = 0,
) -> SequentialCompanyWorldVerificationResult:
    investigation = verify_companyworld(
        result,
        episode.interactive.investigation,
        budget_spent=budget_spent,
        budget_total=budget_total,
    )
    state_index = {item.key(): item.value for item in state}
    domain_score = _condition_score(episode.oracle.domain_outcome_conditions, state_index)
    control_score = _condition_score(episode.oracle.control_outcome_conditions, state_index)

    applied = [item for item in journal if item.applied]
    remediation = [item for item in applied if item.stage == "remediation"]
    expected_remediation = [
        item
        for item in remediation
        if item.action.action_type == episode.oracle.remediation_action_type
    ]
    unauthorized = sum(1 for item in journal if not item.authorized)
    prerequisite_violations = sum(
        1
        for item in journal
        if item.authorized and not item.prerequisites_met
    )
    extra_applied = max(0, len(applied) - episode.oracle.max_applied_actions)

    authority_score = 1.0 if unauthorized == 0 else 0.0
    optimal_actions = 6 if episode.oracle.approval_required else 5
    optimal_ticks = 2 if episode.oracle.approval_required else 1
    action_overage = max(0, len(applied) - optimal_actions)
    tick_overage = max(0, ticks_used - optimal_ticks)
    sequence_efficiency = max(
        0.0,
        1.0
        - 0.10 * action_overage
        - 0.08 * tick_overage
        - 0.12 * prerequisite_violations
        - 0.15 * unauthorized,
    )
    if budget_total > 0 and budget_spent > budget_total:
        sequence_efficiency = 0.0

    fact_score = investigation.fact_score
    evidence_support = investigation.evidence_support
    investigation_quality = (2.0 * fact_score + evidence_support) / 3.0
    joint_success = domain_score * control_score * investigation_quality

    reward = (
        0.45 * joint_success
        + 0.15 * fact_score
        + 0.10 * evidence_support
        + 0.10 * control_score
        + 0.08 * authority_score
        + 0.07 * sequence_efficiency
        + 0.05 * domain_score
    )
    reward -= min(0.40, unauthorized * 0.15)
    reward -= min(0.30, prerequisite_violations * 0.10)
    reward -= min(0.25, extra_applied * 0.08)

    if not expected_remediation:
        reward = min(reward, 0.25)
    if fact_score == 0.0 and evidence_support == 0.0:
        reward = min(reward, 0.20)
    if control_score < 1.0:
        reward = min(reward, 0.65)
    reward = max(0.0, min(1.0, reward))

    return SequentialCompanyWorldVerificationResult(
        domain_outcome_score=round(domain_score, 6),
        control_state_score=round(control_score, 6),
        investigation_fact_score=round(fact_score, 6),
        evidence_support=round(evidence_support, 6),
        authority_score=round(authority_score, 6),
        sequence_efficiency=round(sequence_efficiency, 6),
        unauthorized_attempts=unauthorized,
        prerequisite_violations=prerequisite_violations,
        extra_applied_actions=extra_applied,
        ticks_used=ticks_used,
        overall_reward=round(reward, 6),
    )
