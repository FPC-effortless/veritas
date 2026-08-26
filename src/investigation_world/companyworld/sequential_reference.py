from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass

from investigation_world.companyworld.interactive_models import OperationalAction, OperationalActionType
from investigation_world.companyworld.interactive_reference import solve_interactive_public
from investigation_world.core.models import InvestigationResult


@dataclass(frozen=True)
class SequentialPlanStep:
    kind: str
    action: OperationalAction | None = None
    ticks: int = 0


def _action(task: dict, action_type: OperationalActionType, parameters: dict | None = None) -> OperationalAction:
    return OperationalAction(
        action_type=action_type,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
        parameters=parameters or {},
    )


def _manager_view(interactive_payload: dict) -> dict:
    """Infer the most privileged public role from published action policies only."""
    payload = deepcopy(interactive_payload)
    task = payload["task"]
    counts: Counter[str] = Counter()
    for policy in task.get("action_policies", []):
        for role in policy.get("allowed_roles", []):
            counts[role] += 1
    if not counts:
        return payload
    current = task.get("actor_role")
    maximum = max(counts.values())
    candidates = sorted(role for role, count in counts.items() if count == maximum)
    task["actor_role"] = current if current in candidates else candidates[0]
    return payload


def _directly_authorized(task: dict, action_type: OperationalActionType) -> bool:
    role = task.get("actor_role")
    for policy in task.get("action_policies", []):
        if policy.get("action_type") == action_type.value:
            return role in policy.get("allowed_roles", [])
    return False


def solve_sequential_public(
    payload: dict,
) -> tuple[InvestigationResult, list[SequentialPlanStep]]:
    """Construct a complete control trajectory using only the public sequential episode payload."""
    interactive_payload = payload["interactive"]
    manager_view = _manager_view(interactive_payload)
    result, remediation = solve_interactive_public(manager_view)
    task = payload["task"]

    steps = [
        SequentialPlanStep(
            kind="action",
            action=_action(task, OperationalActionType.OPEN_CONTROL_CASE),
        )
    ]

    if not _directly_authorized(task, remediation.action_type):
        steps.extend(
            [
                SequentialPlanStep(
                    kind="action",
                    action=_action(
                        task,
                        OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
                        {"requested_action": remediation.action_type.value},
                    ),
                ),
                SequentialPlanStep(kind="advance", ticks=1),
            ]
        )

    remediation = remediation.model_copy(
        update={
            "target_object_type": task["target_object_type"],
            "target_object_id": task["target_object_id"],
        }
    )
    steps.extend(
        [
            SequentialPlanStep(kind="action", action=remediation),
            SequentialPlanStep(
                kind="action",
                action=_action(task, OperationalActionType.RECONCILE_SYSTEM_STATE),
            ),
            SequentialPlanStep(kind="advance", ticks=1),
            SequentialPlanStep(
                kind="action",
                action=_action(task, OperationalActionType.VERIFY_CONTROL_INVARIANTS),
            ),
            SequentialPlanStep(
                kind="action",
                action=_action(task, OperationalActionType.CLOSE_CONTROL_CASE),
            ),
        ]
    )
    return result, steps
