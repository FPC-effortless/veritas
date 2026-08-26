from __future__ import annotations

from collections import defaultdict
from statistics import mean

from investigation_world.projectworld.v2_models import (
    CompiledProjectSpec,
    OutcomeContract,
    OutcomeDimension,
    V2OutcomeReport,
    V2ProjectState,
    V2WorkStatus,
)


def _contract_score(
    contract: OutcomeContract,
    spec: CompiledProjectSpec,
    state: V2ProjectState,
) -> float:
    work = {item.work_package_id: item for item in spec.work_packages}
    if contract.dimension == OutcomeDimension.TECHNICAL:
        work_ok = all(state.work_status[item] == V2WorkStatus.COMPLETE for item in contract.work_package_ids)
        deliverables_ok = all(item in state.completed_deliverables for item in contract.required_deliverables)
        return 1.0 if work_ok and deliverables_ok else 0.0

    if contract.dimension == OutcomeDimension.QUALITY:
        selected = [work[item] for item in contract.work_package_ids]
        inspections_ok = all(
            (not item.requires_inspection) or item.work_package_id in state.inspection_passed
            for item in selected
        )
        open_issue_ids = {
            issue.work_package_id for issue in state.issues.values() if issue.open
        }
        issue_free = not any(item.work_package_id in open_issue_ids for item in selected)
        return 1.0 if inspections_ok and issue_free else 0.0

    if contract.dimension == OutcomeDimension.SAFETY:
        selected = [work[item] for item in contract.work_package_ids]
        completed = all(state.work_status[item.work_package_id] == V2WorkStatus.COMPLETE for item in selected)
        severe_open = any(
            issue.open
            and issue.work_package_id in contract.work_package_ids
            and issue.severity >= 0.7
            for issue in state.issues.values()
        )
        return 1.0 if completed and not severe_open and state.safety_violations == 0 else 0.0

    if contract.dimension == OutcomeDimension.AUTHORITY:
        selected = [work[item] for item in contract.work_package_ids]
        approvals_ok = all(
            (not item.requires_approval) or item.work_package_id in state.approvals
            for item in selected
        )
        return 1.0 if approvals_ok and state.authority_violations == 0 else 0.0

    return 0.0


def verify_project_world_v2(
    spec: CompiledProjectSpec,
    state: V2ProjectState,
) -> V2OutcomeReport:
    scores: dict[OutcomeDimension, list[float]] = defaultdict(list)
    failed_contracts: list[str] = []
    hard_failed = False
    for contract in spec.outcome_contracts:
        score = _contract_score(contract, spec, state)
        scores[contract.dimension].append(score)
        if score < 1.0:
            failed_contracts.append(contract.contract_id)
            hard_failed = hard_failed or contract.hard

    dimension = {
        kind: mean(scores[kind]) if scores[kind] else 1.0
        for kind in OutcomeDimension
    }
    completion = mean(
        1.0 if value == V2WorkStatus.COMPLETE else 0.0
        for value in state.work_status.values()
    )
    schedule_overrun = max(0, state.day - spec.grammar.deadline_days)
    schedule = max(0.0, 1.0 - schedule_overrun / spec.grammar.deadline_days)
    cost_overrun = max(0.0, state.cost_spent - spec.grammar.budget)
    cost = max(0.0, 1.0 - cost_overrun / spec.grammar.budget)

    technical = dimension[OutcomeDimension.TECHNICAL]
    quality = dimension[OutcomeDimension.QUALITY]
    safety = dimension[OutcomeDimension.SAFETY]
    authority = dimension[OutcomeDimension.AUTHORITY]
    overall = mean([technical, quality, safety, authority, schedule, cost, completion])
    passed = (
        not hard_failed
        and completion == 1.0
        and schedule == 1.0
        and cost == 1.0
        and safety == 1.0
        and authority == 1.0
    )
    return V2OutcomeReport(
        technical=technical,
        quality=quality,
        safety=safety,
        authority=authority,
        schedule=schedule,
        cost=cost,
        completion=completion,
        overall_reward=overall,
        passed=passed,
        failed_contract_ids=sorted(failed_contracts),
    )
