from __future__ import annotations

from investigation_world.projectworld.models import (
    OperationalProjectWorldSpec,
    ProjectVerificationReport,
    ProjectWorldState,
    WorkPackageStatus,
)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def verify_project_world(
    spec: OperationalProjectWorldSpec,
    state: ProjectWorldState,
    *,
    rejected_actions: int = 0,
) -> ProjectVerificationReport:
    completed = {
        work_id
        for work_id, status in state.work_package_status.items()
        if status == WorkPackageStatus.COMPLETE
    }
    total = max(1, len(spec.work_packages))
    completion = len(completed) / total

    satisfied: list[str] = []
    failed: list[str] = []
    weighted_met = 0.0
    weighted_total = 0.0
    hard_failed = False
    for requirement in spec.requirements:
        weighted_total += requirement.weight
        met = all(work_id in completed for work_id in requirement.satisfied_by_work_packages)
        if met:
            satisfied.append(requirement.requirement_id)
            weighted_met += requirement.weight
        else:
            failed.append(requirement.requirement_id)
            hard_failed = hard_failed or requirement.hard
    requirements = 1.0 if weighted_total == 0 else weighted_met / weighted_total

    if state.cost_spent <= spec.budget:
        cost_score = 1.0
    else:
        cost_score = _clamp(spec.budget / max(state.cost_spent, 1.0))
    budget_overrun = max(0.0, state.cost_spent - spec.budget)

    schedule_overrun_days = max(0, state.day - spec.deadline_days)
    if schedule_overrun_days == 0:
        schedule_score = 1.0
    else:
        schedule_score = _clamp(spec.deadline_days / max(state.day, 1))

    open_issues = sorted(issue.issue_id for issue in state.issues.values() if issue.open)
    quality_score = _clamp(1.0 - 0.2 * len(open_issues))
    authority_score = _clamp(1.0 - 0.1 * rejected_actions)

    overall = (
        0.30 * completion
        + 0.25 * requirements
        + 0.15 * cost_score
        + 0.15 * schedule_score
        + 0.10 * quality_score
        + 0.05 * authority_score
    )
    passed = (
        completion == 1.0
        and not hard_failed
        and not open_issues
        and state.cost_spent <= spec.budget
        and state.day <= spec.deadline_days
    )
    return ProjectVerificationReport(
        completion=completion,
        requirements=requirements,
        cost=cost_score,
        schedule=schedule_score,
        quality=quality_score,
        authority=authority_score,
        overall_reward=_clamp(overall),
        passed=passed,
        completed_work_packages=len(completed),
        total_work_packages=len(spec.work_packages),
        satisfied_requirements=satisfied,
        failed_requirements=failed,
        open_issue_ids=open_issues,
        rejected_actions=rejected_actions,
        budget_overrun=budget_overrun,
        schedule_overrun_days=schedule_overrun_days,
    )
