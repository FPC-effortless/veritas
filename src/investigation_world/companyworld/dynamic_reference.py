from __future__ import annotations

from investigation_world.companyworld.dynamic_runtime import DynamicCompanyWorldRuntime
from investigation_world.companyworld.interactive_models import OperationalAction, OperationalActionType
from investigation_world.companyworld.sequential_reference import solve_sequential_public
from investigation_world.core.models import InvestigationResult


_GENERIC_ACTIONS = {
    OperationalActionType.OPEN_CONTROL_CASE,
    OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
    OperationalActionType.RECONCILE_SYSTEM_STATE,
    OperationalActionType.VERIFY_CONTROL_INVARIANTS,
    OperationalActionType.CLOSE_CONTROL_CASE,
    OperationalActionType.COMPENSATE_LAST_ACTION,
    OperationalActionType.ESCALATE_CONTROL_FAILURE,
}


def _action(task: dict, action_type: OperationalActionType, parameters: dict | None = None):
    return OperationalAction(
        action_type=action_type,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
        parameters=parameters or {},
    )


def _remediation(plan):
    return next(
        step.action
        for step in plan
        if step.kind == "action"
        and step.action is not None
        and step.action.action_type not in _GENERIC_ACTIONS
    )


def _policy(task: dict, action_type: OperationalActionType) -> dict:
    return next(
        policy
        for policy in task.get("action_policies", [])
        if policy.get("action_type") == action_type.value
    )


def run_dynamic_public_reference(
    runtime: DynamicCompanyWorldRuntime,
    payload: dict,
) -> tuple[dict[str, InvestigationResult], object]:
    """Adaptively solve a dynamic portfolio using only public scenario data and observed state."""
    cases = sorted(
        payload["cases"],
        key=lambda item: (item["deadline_tick"], -float(item["priority_weight"]), item["case_id"]),
    )
    results: dict[str, InvestigationResult] = {}
    remediation_by_case: dict[str, OperationalAction] = {}
    policy_by_case: dict[str, dict] = {}

    for case in cases:
        result, plan = solve_sequential_public(case["sequential"])
        remediation = _remediation(plan)
        task = case["sequential"]["task"]
        remediation = remediation.model_copy(
            update={
                "target_object_type": task["target_object_type"],
                "target_object_id": task["target_object_id"],
            }
        )
        results[case["case_id"]] = result
        remediation_by_case[case["case_id"]] = remediation
        policy_by_case[case["case_id"]] = _policy(task, remediation.action_type)
        runtime.act(case["case_id"], _action(task, OperationalActionType.OPEN_CONTROL_CASE))

    approval_cases: list[str] = []
    for case in cases:
        case_id = case["case_id"]
        task = case["sequential"]["task"]
        remediation = remediation_by_case[case_id]
        policy = policy_by_case[case_id]
        if task["actor_role"] not in policy.get("allowed_roles", []):
            runtime.act(
                case_id,
                _action(
                    task,
                    OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
                    {"requested_action": remediation.action_type.value},
                ),
            )
            approval_cases.append(case_id)

    if approval_cases:
        runtime.advance(1)
        for case in cases:
            case_id = case["case_id"]
            if case_id not in approval_cases:
                continue
            status = runtime.case_status(case_id)["state"].get("approval_status")
            if status == "APPROVED":
                continue
            allowed_roles = policy_by_case[case_id].get("allowed_roles", [])
            if not allowed_roles:
                continue
            runtime.handoff(case_id, sorted(allowed_roles)[0])

    remaining = {case["case_id"] for case in cases}
    case_by_id = {case["case_id"]: case for case in cases}
    while remaining:
        busy_resources: set[str] = set()
        pending: list[str] = []
        progress = False
        for case in cases:
            case_id = case["case_id"]
            if case_id not in remaining:
                continue
            resource = case["shared_resource"]
            if resource in busy_resources:
                continue
            execution = runtime.act(case_id, remediation_by_case[case_id])
            if not execution.applied:
                continue
            busy_resources.add(resource)
            task = case["sequential"]["task"]
            reconciliation = runtime.act(
                case_id,
                _action(task, OperationalActionType.RECONCILE_SYSTEM_STATE),
            )
            if reconciliation.applied:
                pending.append(case_id)
                remaining.remove(case_id)
                progress = True

        if pending:
            runtime.advance(1)
            for case_id in pending:
                case = case_by_id[case_id]
                task = case["sequential"]["task"]
                runtime.act(
                    case_id,
                    _action(task, OperationalActionType.VERIFY_CONTROL_INVARIANTS),
                )
                runtime.act(
                    case_id,
                    _action(task, OperationalActionType.CLOSE_CONTROL_CASE),
                )
            continue

        if not progress and remaining:
            if runtime.tick >= payload["task"]["max_ticks"]:
                break
            runtime.advance(1)

    return results, runtime.submit(results)
