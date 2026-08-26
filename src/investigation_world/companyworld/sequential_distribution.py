from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investigation_world.companyworld.interactive_distribution import (
    InteractiveCompanyWorldConfig,
    _outcome_conditions,
    _plan,
    _role_pair,
    compile_interactive_distribution,
)
from investigation_world.companyworld.interactive_models import (
    ActionEffectTemplate,
    InteractiveCompanyWorldEpisode,
    InteractiveOutcomeCondition,
    OperationalActionType,
    StateValue,
)
from investigation_world.companyworld.sequential_models import (
    DelayedEffectTemplate,
    SequentialActionPolicy,
    SequentialCompanyWorldEpisode,
    SequentialCompanyWorldOracle,
    SequentialCompanyWorldTask,
    StateCondition,
)


SEQUENTIAL_DISTRIBUTION_VERSION = "0.1.0"


@dataclass(frozen=True)
class SequentialCompanyWorldConfig:
    per_family: int = 200
    include_legacy: bool = True
    legacy_limit: int | None = None


def _condition(episode: InteractiveCompanyWorldEpisode, field_name: str, value: Any) -> StateCondition:
    return StateCondition(
        object_type=episode.task.target_object_type,
        object_id=episode.task.target_object_id,
        field_name=field_name,
        expected_value=value,
    )


def _effect(field_name: str, value: Any) -> ActionEffectTemplate:
    return ActionEffectTemplate(field_name=field_name, constant_value=value)


def _control_condition(
    episode: InteractiveCompanyWorldEpisode,
    field_name: str,
    value: Any,
) -> InteractiveOutcomeCondition:
    return InteractiveOutcomeCondition(
        object_type=episode.task.target_object_type,
        object_id=episode.task.target_object_id,
        field_name=field_name,
        expected_value=value,
    )


def compile_sequential_episode(
    episode: InteractiveCompanyWorldEpisode,
) -> SequentialCompanyWorldEpisode:
    base = episode.investigation
    manager_role, analyst_role = _role_pair(base)
    manager_policies, remediation_action, remediation_parameters = _plan(
        base,
        manager_role,
        manager_role,
        analyst_role,
    )
    remediation_policy = next(
        item for item in manager_policies if item.action_type == remediation_action
    )
    approval_required = episode.task.actor_role not in remediation_policy.allowed_roles

    target_type = episode.task.target_object_type
    target_id = episode.task.target_object_id
    actor_role = episode.task.actor_role
    both_roles = sorted({manager_role, analyst_role, actor_role})

    policies: list[SequentialActionPolicy] = [
        SequentialActionPolicy(
            action_type=OperationalActionType.OPEN_CONTROL_CASE,
            allowed_roles=both_roles,
            cost=1,
            stage="contain",
            description="Open an operational control case before making state-changing decisions.",
            prerequisites=[_condition(episode, "control_case_status", "NEW")],
            effects=[_effect("control_case_status", "OPEN")],
        ),
        SequentialActionPolicy(
            action_type=OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
            allowed_roles=both_roles,
            cost=1,
            stage="approval",
            description=(
                "Request scoped delegated authority for one available operational action. "
                "Approval is delivered as a simulated external-system event."
            ),
            prerequisites=[_condition(episode, "control_case_status", "OPEN")],
            effects=[
                _effect("approval_status", "PENDING"),
                ActionEffectTemplate(field_name="approval_scope", parameter_name="requested_action"),
            ],
            delayed_effects=[
                DelayedEffectTemplate(
                    field_name="approval_status",
                    constant_value="APPROVED",
                    delay_ticks=1,
                )
            ],
        ),
    ]

    for item in episode.task.action_policies:
        policies.append(
            SequentialActionPolicy(
                action_type=item.action_type,
                allowed_roles=item.allowed_roles,
                cost=item.cost,
                stage="remediation",
                description=item.description,
                prerequisites=[
                    _condition(episode, "control_case_status", "OPEN"),
                    _condition(episode, "remediation_status", "NOT_STARTED"),
                ],
                effects=[
                    *item.effects,
                    _effect("remediation_status", "APPLIED"),
                    _effect("last_remediation_action", item.action_type.value),
                ],
                delegatable_with_approval=True,
            )
        )

    policies.extend(
        [
            SequentialActionPolicy(
                action_type=OperationalActionType.RECONCILE_SYSTEM_STATE,
                allowed_roles=both_roles,
                cost=2,
                stage="reconcile",
                description=(
                    "Initiate downstream reconciliation after remediation. The downstream sync "
                    "completes on the next simulated tick."
                ),
                prerequisites=[_condition(episode, "remediation_status", "APPLIED")],
                effects=[_effect("reconciliation_status", "PENDING")],
                delayed_effects=[
                    DelayedEffectTemplate(
                        field_name="reconciliation_status",
                        constant_value="COMPLETE",
                        delay_ticks=1,
                    )
                ],
            ),
            SequentialActionPolicy(
                action_type=OperationalActionType.VERIFY_CONTROL_INVARIANTS,
                allowed_roles=both_roles,
                cost=1,
                stage="verify",
                description=(
                    "Record that end-state invariants have been checked after downstream "
                    "reconciliation. Private correctness remains verifier-only."
                ),
                prerequisites=[_condition(episode, "reconciliation_status", "COMPLETE")],
                effects=[_effect("verification_status", "REQUESTED")],
            ),
            SequentialActionPolicy(
                action_type=OperationalActionType.CLOSE_CONTROL_CASE,
                allowed_roles=both_roles,
                cost=1,
                stage="close",
                description="Close the operational control case after verification.",
                prerequisites=[_condition(episode, "verification_status", "REQUESTED")],
                effects=[_effect("control_case_status", "CLOSED")],
            ),
            SequentialActionPolicy(
                action_type=OperationalActionType.COMPENSATE_LAST_ACTION,
                allowed_roles=both_roles,
                cost=2,
                stage="recover",
                description=(
                    "Compensate the most recent applied remediation, restoring its previous "
                    "state values so a corrected remediation can be attempted."
                ),
                prerequisites=[_condition(episode, "remediation_status", "APPLIED")],
                compensation_action=True,
            ),
            SequentialActionPolicy(
                action_type=OperationalActionType.ESCALATE_CONTROL_FAILURE,
                allowed_roles=both_roles,
                cost=1,
                stage="recover",
                description="Escalate the control case when safe recovery cannot be completed.",
                prerequisites=[_condition(episode, "control_case_status", "OPEN")],
                effects=[
                    _effect("control_case_status", "ESCALATED"),
                    _effect("control_failure_status", "ESCALATED"),
                ],
            ),
        ]
    )

    domain_conditions = _outcome_conditions(base, remediation_policy, remediation_parameters)
    control_conditions = [
        _control_condition(episode, "remediation_status", "APPLIED"),
        _control_condition(episode, "reconciliation_status", "COMPLETE"),
        _control_condition(episode, "verification_status", "REQUESTED"),
        _control_condition(episode, "control_case_status", "CLOSED"),
    ]
    if approval_required:
        control_conditions.extend(
            [
                _control_condition(episode, "approval_status", "APPROVED"),
                _control_condition(episode, "approval_scope", remediation_action.value),
            ]
        )

    task_id = f"SEQ-{episode.task.task_id}"
    return SequentialCompanyWorldEpisode(
        episode_id=f"SEQ-{episode.episode_id}",
        world_id=episode.world_id,
        interactive=episode,
        task=SequentialCompanyWorldTask(
            task_id=task_id,
            world_id=episode.world_id,
            task_type=f"SEQUENTIAL_{base.task.task_type}",
            objective=(
                base.task.objective
                + " Then operate the control workflow to a verified, reconciled end state. "
                "Respect prerequisites and obtain scoped approval when your role lacks direct authority."
            ),
            target_object_type=target_type,
            target_object_id=target_id,
            actor_role=actor_role,
            permitted_systems=episode.task.permitted_systems,
            available_actions=[item.action_type for item in policies],
            action_policies=policies,
            max_actions=9,
            max_ticks=6,
            constraints={
                "must_cite_records": True,
                "private_ground_truth_unavailable": True,
                "evidence_is_immutable": True,
                "prerequisites_are_enforced": True,
                "approval_is_scoped_to_requested_action": True,
                "system_effects_may_be_delayed": True,
                "recovery_actions_are_available": True,
            },
            metadata={
                "base_task_type": base.task.task_type,
                "sequential_distribution_version": SEQUENTIAL_DISTRIBUTION_VERSION,
            },
        ),
        initial_state=[
            StateValue(object_type=target_type, object_id=target_id, field_name="control_case_status", value="NEW"),
            StateValue(object_type=target_type, object_id=target_id, field_name="approval_status", value="NOT_REQUESTED"),
            StateValue(object_type=target_type, object_id=target_id, field_name="approval_scope", value=None),
            StateValue(object_type=target_type, object_id=target_id, field_name="remediation_status", value="NOT_STARTED"),
            StateValue(object_type=target_type, object_id=target_id, field_name="reconciliation_status", value="NOT_STARTED"),
            StateValue(object_type=target_type, object_id=target_id, field_name="verification_status", value="NOT_STARTED"),
        ],
        oracle=SequentialCompanyWorldOracle(
            task_id=task_id,
            remediation_action_type=remediation_action,
            remediation_action_parameters=remediation_parameters,
            domain_outcome_conditions=domain_conditions,
            control_outcome_conditions=control_conditions,
            approval_required=approval_required,
            max_applied_actions=7 if approval_required else 6,
            max_ticks=6,
        ),
        metadata={
            "base_episode_id": episode.episode_id,
            "base_task_type": base.task.task_type,
            "sequential_distribution_version": SEQUENTIAL_DISTRIBUTION_VERSION,
        },
    )


def compile_sequential_distribution(
    root: str | Path,
    *,
    config: SequentialCompanyWorldConfig | None = None,
) -> list[SequentialCompanyWorldEpisode]:
    cfg = config or SequentialCompanyWorldConfig()
    interactive = compile_interactive_distribution(
        root,
        config=InteractiveCompanyWorldConfig(
            per_family=cfg.per_family,
            include_legacy=cfg.include_legacy,
            legacy_limit=cfg.legacy_limit,
        ),
    )
    return [compile_sequential_episode(episode) for episode in interactive]
