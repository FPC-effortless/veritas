from __future__ import annotations

from investigation_world.companyworld.dynamic_models import (
    DynamicCaseVerification,
    DynamicCompanyWorldScenario,
    DynamicCompanyWorldVerificationResult,
    DynamicHandoff,
    DynamicToolObservation,
)
from investigation_world.companyworld.sequential_models import SequentialCompanyWorldVerificationResult


def verify_dynamic_companyworld(
    scenario: DynamicCompanyWorldScenario,
    *,
    sequential_results: dict[str, SequentialCompanyWorldVerificationResult],
    deadline_missed: set[str],
    resource_conflicts: int,
    tool_observations: list[DynamicToolObservation],
    handoffs: list[DynamicHandoff],
    irreversible_compensation_attempts: int,
    coupled_consequence_applied: bool,
    budget_spent: int,
    budget_total: int,
) -> DynamicCompanyWorldVerificationResult:
    oracle_by_case = {item.case_id: item for item in scenario.oracle.case_oracles}
    total_weight = sum(case.priority_weight for case in scenario.cases) or 1.0
    weighted_reward = sum(
        case.priority_weight * sequential_results[case.case_id].overall_reward
        for case in scenario.cases
    ) / total_weight
    success_count = sum(
        1
        for case in scenario.cases
        if sequential_results[case.case_id].overall_reward >= 0.999999
    )
    case_success_rate = success_count / len(scenario.cases) if scenario.cases else 0.0

    late_penalty = sum(
        case.late_penalty for case in scenario.cases if case.case_id in deadline_missed
    )
    deadline_score = max(0.0, 1.0 - late_penalty)
    resource_discipline = max(0.0, 1.0 - 0.25 * resource_conflicts)

    denied_cases = [
        case
        for case in scenario.cases
        if oracle_by_case[case.case_id].approval_outcome == "DENIED"
        and case.sequential.oracle.approval_required
    ]
    recovered_denials = sum(
        1
        for case in denied_cases
        if sequential_results[case.case_id].overall_reward >= 0.999999
    )
    uncertainty_recovery = (
        recovered_denials / len(denied_cases) if denied_cases else 1.0
    )

    if budget_total <= 0 or budget_spent <= budget_total * 0.65:
        budget_efficiency = 1.0
    else:
        budget_efficiency = max(
            0.0,
            1.0 - ((budget_spent - budget_total * 0.65) / (budget_total * 0.35)),
        )

    tool_failures = sum(1 for item in tool_observations if not item.ok or item.degraded)
    applied_handoffs = sum(1 for item in handoffs if item.applied)
    case_results = [
        DynamicCaseVerification(
            case_id=case.case_id,
            sequential=sequential_results[case.case_id],
            deadline_met=case.case_id not in deadline_missed,
            approval_recovered=(
                oracle_by_case[case.case_id].approval_outcome != "DENIED"
                or sequential_results[case.case_id].overall_reward >= 0.999999
            ),
        )
        for case in scenario.cases
    ]

    reward = (
        0.60 * weighted_reward
        + 0.12 * deadline_score
        + 0.08 * resource_discipline
        + 0.10 * uncertainty_recovery
        + 0.10 * budget_efficiency
    )
    if coupled_consequence_applied:
        reward -= scenario.oracle.coupled_deadline_penalty
    reward -= min(0.30, irreversible_compensation_attempts * 0.10)

    if success_count == 0:
        reward = min(reward, 0.25)
    elif case_success_rate < 0.5:
        reward = min(reward, 0.45)
    if coupled_consequence_applied:
        reward = min(reward, 0.75)
    reward = max(0.0, min(1.0, reward))

    return DynamicCompanyWorldVerificationResult(
        weighted_case_reward=round(weighted_reward, 6),
        case_success_rate=round(case_success_rate, 6),
        deadline_score=round(deadline_score, 6),
        resource_discipline=round(resource_discipline, 6),
        uncertainty_recovery=round(uncertainty_recovery, 6),
        budget_efficiency=round(budget_efficiency, 6),
        deadline_misses=len(deadline_missed),
        resource_conflicts=resource_conflicts,
        tool_failures_observed=tool_failures,
        handoffs=applied_handoffs,
        irreversible_compensation_attempts=irreversible_compensation_attempts,
        coupled_consequence_applied=coupled_consequence_applied,
        case_results=case_results,
        overall_reward=round(reward, 6),
    )
