from __future__ import annotations

from math import isclose
from typing import Any

from investigation_world.companyworld.interactive_models import (
    ActionExecution,
    InteractiveCompanyWorldEpisode,
    InteractiveCompanyWorldVerificationResult,
    StateValue,
)
from investigation_world.companyworld.verifier import verify_companyworld
from investigation_world.core.models import InvestigationResult


def _same(expected: Any, actual: Any) -> bool:
    if isinstance(expected, bool) or isinstance(actual, bool):
        return expected is actual
    if isinstance(expected, (int, float)) and isinstance(actual, (int, float)):
        return isclose(float(expected), float(actual), rel_tol=1e-6, abs_tol=1e-2)
    return str(expected).strip().casefold() == str(actual).strip().casefold()


def verify_interactive_companyworld(
    result: InvestigationResult,
    episode: InteractiveCompanyWorldEpisode,
    *,
    state: list[StateValue],
    journal: list[ActionExecution],
    budget_spent: int = 0,
    budget_total: int = 0,
) -> InteractiveCompanyWorldVerificationResult:
    investigation = verify_companyworld(
        result,
        episode.investigation,
        budget_spent=budget_spent,
        budget_total=budget_total,
    )
    state_index = {item.key(): item.value for item in state}
    conditions = episode.oracle.outcome_conditions
    matched = sum(
        1
        for condition in conditions
        if condition.key() in state_index
        and _same(condition.expected_value, state_index[condition.key()])
    )
    outcome_score = matched / len(conditions) if conditions else 0.0

    applied = [item for item in journal if item.applied]
    expected_applied = [
        item
        for item in applied
        if item.action.action_type == episode.oracle.expected_action_type
    ]
    if not applied:
        action_precision = 0.0
    elif expected_applied:
        action_precision = len(expected_applied) / len(applied)
    else:
        action_precision = 0.0

    unauthorized = sum(1 for item in journal if not item.authorized)
    authority_score = 1.0 if unauthorized == 0 else 0.0
    extra_applied = max(0, len(applied) - episode.oracle.max_applied_actions)

    if budget_total <= 0 or budget_spent <= budget_total * 0.5:
        efficiency = 1.0
    else:
        efficiency = max(
            0.0,
            1.0 - ((budget_spent - budget_total * 0.5) / (budget_total * 0.5)),
        )

    fact_score = investigation.fact_score
    evidence_support = investigation.evidence_support
    investigation_quality = (2.0 * fact_score + evidence_support) / 3.0
    joint_success = outcome_score * investigation_quality

    reward = (
        0.55 * joint_success
        + 0.15 * fact_score
        + 0.10 * evidence_support
        + 0.10 * action_precision
        + 0.05 * authority_score
        + 0.05 * efficiency
    )
    reward -= min(0.45, unauthorized * 0.15)
    reward -= min(0.30, extra_applied * 0.10)
    if outcome_score == 0.0:
        reward = min(reward, 0.35)
    reward = max(0.0, min(1.0, reward))

    return InteractiveCompanyWorldVerificationResult(
        outcome_score=round(outcome_score, 6),
        investigation_fact_score=round(fact_score, 6),
        evidence_support=round(evidence_support, 6),
        action_precision=round(action_precision, 6),
        authority_score=round(authority_score, 6),
        efficiency=round(efficiency, 6),
        unauthorized_attempts=unauthorized,
        extra_applied_actions=extra_applied,
        overall_reward=round(reward, 6),
    )
