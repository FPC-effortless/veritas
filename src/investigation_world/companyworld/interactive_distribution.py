from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investigation_world.companyworld.distribution import (
    CompanyWorldTaskDistributionConfig,
    compile_task_distribution,
)
from investigation_world.companyworld.interactive_models import (
    ActionEffectTemplate,
    ActionPolicy,
    InteractiveCompanyWorldEpisode,
    InteractiveCompanyWorldOracle,
    InteractiveCompanyWorldTask,
    InteractiveOutcomeCondition,
    OperationalActionType,
    StateValue,
)
from investigation_world.companyworld.models import CompanyWorldEpisode


INTERACTIVE_DISTRIBUTION_VERSION = "0.1.0"


@dataclass(frozen=True)
class InteractiveCompanyWorldConfig:
    per_family: int = 200
    include_legacy: bool = True
    legacy_limit: int | None = None


def _fact(episode: CompanyWorldEpisode, field_name: str) -> Any:
    for fact in episode.oracle.facts:
        if fact.field_name == field_name:
            return fact.expected_value
    raise ValueError(f"{episode.task.task_type} is missing oracle fact {field_name}")


def _record_field(
    episode: CompanyWorldEpisode,
    record_type: str,
    field_name: str,
    default: Any = None,
) -> Any:
    for record in episode.records:
        if record.record_type == record_type and field_name in record.fields:
            return record.fields[field_name]
    return default


def _privileged(episode: CompanyWorldEpisode) -> bool:
    digest = hashlib.sha256(f"interactive-role|{episode.episode_id}".encode()).hexdigest()
    return int(digest[:8], 16) % 2 == 0


def _effects(
    *items: tuple[str, Any],
    parameters: dict[str, str] | None = None,
) -> list[ActionEffectTemplate]:
    out = [
        ActionEffectTemplate(field_name=field_name, constant_value=value)
        for field_name, value in items
    ]
    for field_name, parameter_name in (parameters or {}).items():
        out.append(
            ActionEffectTemplate(
                field_name=field_name,
                parameter_name=parameter_name,
            )
        )
    return out


def _policy(
    action_type: OperationalActionType,
    roles: list[str],
    *,
    cost: int,
    description: str,
    effects: list[ActionEffectTemplate],
) -> ActionPolicy:
    return ActionPolicy(
        action_type=action_type,
        allowed_roles=roles,
        cost=cost,
        description=description,
        effects=effects,
    )


def _role_pair(episode: CompanyWorldEpisode) -> tuple[str, str]:
    family = episode.task.task_type
    pairs = {
        "INVESTIGATE_MISSING_SHIPMENT": ("OPERATIONS_MANAGER", "OPERATIONS_ANALYST"),
        "INVESTIGATE_DUPLICATE_INVOICE": ("AP_MANAGER", "AP_ANALYST"),
        "INVESTIGATE_AUTHORITY_BREACH": ("COMPLIANCE_ADMIN", "COMPLIANCE_ANALYST"),
        "O2C_FULFILLMENT_TIMING": ("OPERATIONS_MANAGER", "OPERATIONS_ANALYST"),
        "P2P_RECONCILIATION": ("AP_MANAGER", "AP_ANALYST"),
        "CUSTOMER_SETTLEMENT_RECONSTRUCTION": ("AR_MANAGER", "AR_ANALYST"),
        "PAYMENT_BLOCK_RECOVERY": ("AP_MANAGER", "PROCESS_ANALYST"),
        "INCIDENT_SLA_INVESTIGATION": ("INCIDENT_MANAGER", "ITSM_ANALYST"),
        "SAFETY_CORRECTIVE_FOLLOWUP": ("SAFETY_MANAGER", "SAFETY_ANALYST"),
        "CROSS_SYSTEM_CASH_CYCLE": ("FINANCE_CONTROLLER", "FINANCE_ANALYST"),
        "LEDGER_POSTING_RECONSTRUCTION": ("FINANCE_CONTROLLER", "FINANCE_ANALYST"),
    }
    if family not in pairs:
        raise ValueError(f"unsupported interactive CompanyWorld family: {family}")
    return pairs[family]


def _plan(
    episode: CompanyWorldEpisode,
    actor_role: str,
    manager_role: str,
    analyst_role: str,
) -> tuple[list[ActionPolicy], OperationalActionType, dict[str, Any]]:
    family = episode.task.task_type
    both = [manager_role, analyst_role]

    if family == "INVESTIGATE_MISSING_SHIPMENT":
        ordered = float(_record_field(episode, "sales_order_fulfillment_summary", "ordered_quantity", 0))
        delivered = float(_fact(episode, "delivered_quantity"))
        missing = max(0.0, ordered - delivered)
        policies = [
            _policy(
                OperationalActionType.CREATE_RESHIPMENT,
                [manager_role],
                cost=4,
                description="Create a replacement shipment for the confirmed shortfall.",
                effects=_effects(
                    ("case_status", "RESOLVED"),
                    ("remediation_status", "RESHIPMENT_CREATED"),
                    parameters={"replacement_quantity": "quantity"},
                ),
            ),
            _policy(
                OperationalActionType.ESCALATE_SHIPMENT_EXCEPTION,
                both,
                cost=1,
                description="Escalate a shipment exception to an authorized operations manager.",
                effects=_effects(("case_status", "ESCALATED"), ("escalation_status", "REQUESTED")),
            ),
        ]
        if actor_role == manager_role:
            return policies, OperationalActionType.CREATE_RESHIPMENT, {"quantity": missing}
        return policies, OperationalActionType.ESCALATE_SHIPMENT_EXCEPTION, {}

    if family == "INVESTIGATE_DUPLICATE_INVOICE":
        policies = [
            _policy(
                OperationalActionType.BLOCK_SUPPLIER_INVOICE,
                [manager_role],
                cost=4,
                description="Block a confirmed duplicate supplier invoice from payment.",
                effects=_effects(("case_status", "RESOLVED"), ("payment_status", "BLOCKED_DUPLICATE")),
            ),
            _policy(
                OperationalActionType.ESCALATE_INVOICE_EXCEPTION,
                both,
                cost=1,
                description="Escalate a confirmed invoice exception for authorized remediation.",
                effects=_effects(("case_status", "ESCALATED"), ("escalation_status", "REQUESTED")),
            ),
        ]
        if actor_role == manager_role:
            return policies, OperationalActionType.BLOCK_SUPPLIER_INVOICE, {}
        return policies, OperationalActionType.ESCALATE_INVOICE_EXCEPTION, {}

    if family == "INVESTIGATE_AUTHORITY_BREACH":
        expected_limit = _fact(episode, "approval_limit_usd")
        policies = [
            _policy(
                OperationalActionType.RESTORE_AUTHORITY_LIMIT,
                [manager_role],
                cost=5,
                description="Restore the authority-service limit to the evidence-backed policy value.",
                effects=_effects(
                    ("case_status", "RESOLVED"),
                    parameters={"approval_limit_usd": "approval_limit_usd"},
                ),
            ),
            _policy(
                OperationalActionType.ESCALATE_AUTHORITY_REPAIR,
                both,
                cost=1,
                description="Escalate an authority configuration defect to a compliance administrator.",
                effects=_effects(("case_status", "ESCALATED"), ("escalation_status", "REQUESTED")),
            ),
        ]
        if actor_role == manager_role:
            return policies, OperationalActionType.RESTORE_AUTHORITY_LIMIT, {"approval_limit_usd": expected_limit}
        return policies, OperationalActionType.ESCALATE_AUTHORITY_REPAIR, {}

    if family == "O2C_FULFILLMENT_TIMING":
        status = str(_fact(episode, "ship_commitment_status"))
        policies = [
            _policy(
                OperationalActionType.EXPEDITE_ORDER,
                [manager_role],
                cost=4,
                description="Expedite an order whose requested shipping commitment was missed.",
                effects=_effects(("case_status", "RESOLVED"), ("fulfillment_action", "EXPEDITE")),
            ),
            _policy(
                OperationalActionType.CONFIRM_FULFILLMENT,
                both,
                cost=1,
                description="Close the review when the shipping commitment was met.",
                effects=_effects(("case_status", "RESOLVED"), ("fulfillment_action", "CONFIRMED")),
            ),
            _policy(
                OperationalActionType.ESCALATE_FULFILLMENT_DELAY,
                both,
                cost=1,
                description="Escalate a confirmed fulfillment delay to an operations manager.",
                effects=_effects(("case_status", "ESCALATED"), ("escalation_status", "REQUESTED")),
            ),
        ]
        if status == "ON_TIME":
            return policies, OperationalActionType.CONFIRM_FULFILLMENT, {}
        if actor_role == manager_role:
            return policies, OperationalActionType.EXPEDITE_ORDER, {}
        return policies, OperationalActionType.ESCALATE_FULFILLMENT_DELAY, {}

    if family == "P2P_RECONCILIATION":
        status = str(_fact(episode, "reconciliation_status"))
        policies = [
            _policy(
                OperationalActionType.APPROVE_SUPPLIER_INVOICE,
                [manager_role],
                cost=3,
                description="Approve an invoice that satisfies the published three-way match policy.",
                effects=_effects(("case_status", "RESOLVED"), ("payment_decision", "APPROVED")),
            ),
            _policy(
                OperationalActionType.ROUTE_INVOICE_REVIEW,
                both,
                cost=2,
                description="Route an invoice that fails the match policy to exception review.",
                effects=_effects(("case_status", "REVIEW"), ("payment_decision", "REVIEW")),
            ),
            _policy(
                OperationalActionType.REQUEST_INVOICE_APPROVAL,
                both,
                cost=1,
                description="Request manager approval for a matched invoice when the current actor lacks approval authority.",
                effects=_effects(("case_status", "ESCALATED"), ("approval_request_status", "REQUESTED")),
            ),
        ]
        if status != "MATCH":
            return policies, OperationalActionType.ROUTE_INVOICE_REVIEW, {}
        if actor_role == manager_role:
            return policies, OperationalActionType.APPROVE_SUPPLIER_INVOICE, {}
        return policies, OperationalActionType.REQUEST_INVOICE_APPROVAL, {}

    if family == "CUSTOMER_SETTLEMENT_RECONSTRUCTION":
        status = str(_fact(episode, "settlement_status"))
        policies = [
            _policy(
                OperationalActionType.CLOSE_AR_CASE,
                both,
                cost=1,
                description="Close the receivables case when the invoice is fully settled.",
                effects=_effects(("case_status", "RESOLVED"), ("ar_case_status", "CLOSED")),
            ),
            _policy(
                OperationalActionType.OPEN_COLLECTIONS_CASE,
                both,
                cost=2,
                description="Open collections follow-up for an open or partially settled invoice.",
                effects=_effects(("case_status", "FOLLOW_UP"), ("ar_case_status", "COLLECTIONS_OPEN")),
            ),
        ]
        if status == "PAID":
            return policies, OperationalActionType.CLOSE_AR_CASE, {}
        return policies, OperationalActionType.OPEN_COLLECTIONS_CASE, {}

    if family == "PAYMENT_BLOCK_RECOVERY":
        recovery = float(_fact(episode, "payment_block_recovery_hours"))
        policies = [
            _policy(
                OperationalActionType.CLOSE_PAYMENT_BLOCK_CASE,
                both,
                cost=1,
                description="Close a payment-block recovery review that completed within the 72-hour operational threshold.",
                effects=_effects(("case_status", "RESOLVED"), ("recovery_case_status", "CLOSED")),
            ),
            _policy(
                OperationalActionType.ESCALATE_PAYMENT_BLOCK_RECOVERY,
                both,
                cost=1,
                description="Escalate a payment-block recovery that exceeded 72 hours.",
                effects=_effects(("case_status", "ESCALATED"), ("recovery_case_status", "ESCALATED")),
            ),
        ]
        action = (
            OperationalActionType.CLOSE_PAYMENT_BLOCK_CASE
            if recovery <= 72.0
            else OperationalActionType.ESCALATE_PAYMENT_BLOCK_RECOVERY
        )
        return policies, action, {}

    if family == "INCIDENT_SLA_INVESTIGATION":
        status = str(_fact(episode, "sla_status"))
        policies = [
            _policy(
                OperationalActionType.ESCALATE_INCIDENT,
                both,
                cost=2,
                description="Escalate an incident review when the severity-specific resolution SLA was breached.",
                effects=_effects(("case_status", "ESCALATED"), ("incident_review_status", "ESCALATED")),
            ),
            _policy(
                OperationalActionType.CLOSE_INCIDENT_REVIEW,
                both,
                cost=1,
                description="Close the SLA review when the incident met its severity-specific resolution SLA.",
                effects=_effects(("case_status", "RESOLVED"), ("incident_review_status", "CLOSED")),
            ),
        ]
        if status == "BREACH":
            return policies, OperationalActionType.ESCALATE_INCIDENT, {}
        return policies, OperationalActionType.CLOSE_INCIDENT_REVIEW, {}

    if family == "SAFETY_CORRECTIVE_FOLLOWUP":
        escalation = bool(_fact(episode, "escalation_required"))
        policies = [
            _policy(
                OperationalActionType.ESCALATE_SAFETY_ACTION,
                both,
                cost=2,
                description="Escalate a safety corrective action when the published escalation policy requires it.",
                effects=_effects(("case_status", "ESCALATED"), ("safety_review_status", "ESCALATED")),
            ),
            _policy(
                OperationalActionType.CLOSE_SAFETY_REVIEW,
                both,
                cost=1,
                description="Close the safety follow-up when escalation is not required.",
                effects=_effects(("case_status", "RESOLVED"), ("safety_review_status", "CLOSED")),
            ),
        ]
        if escalation:
            return policies, OperationalActionType.ESCALATE_SAFETY_ACTION, {}
        return policies, OperationalActionType.CLOSE_SAFETY_REVIEW, {}

    if family == "CROSS_SYSTEM_CASH_CYCLE":
        cycle = _fact(episode, "order_to_cash_days")
        policies = [
            _policy(
                OperationalActionType.CERTIFY_CASH_CYCLE,
                [manager_role],
                cost=3,
                description="Certify the reconstructed order-to-cash duration for operational reporting.",
                effects=_effects(
                    ("case_status", "RESOLVED"),
                    ("cash_cycle_review_status", "CERTIFIED"),
                    parameters={"certified_order_to_cash_days": "order_to_cash_days"},
                ),
            ),
            _policy(
                OperationalActionType.ESCALATE_CASH_CYCLE_REVIEW,
                both,
                cost=1,
                description="Escalate a cash-cycle certification to a finance controller when the actor lacks certification authority.",
                effects=_effects(("case_status", "ESCALATED"), ("cash_cycle_review_status", "ESCALATED")),
            ),
        ]
        if actor_role == manager_role:
            return policies, OperationalActionType.CERTIFY_CASH_CYCLE, {"order_to_cash_days": cycle}
        return policies, OperationalActionType.ESCALATE_CASH_CYCLE_REVIEW, {}

    if family == "LEDGER_POSTING_RECONSTRUCTION":
        ar_debit = float(_fact(episode, "ar_debit_usd"))
        revenue_credit = float(_fact(episode, "revenue_credit_usd"))
        invoice_amount = float(
            _record_field(episode, "customer_invoice_posting_source", "invoice_amount_usd", 0.0)
        )
        balanced = (
            abs(ar_debit - revenue_credit) <= 0.01
            and abs(ar_debit - invoice_amount) <= 0.01
        )
        policies = [
            _policy(
                OperationalActionType.CERTIFY_LEDGER_POSTING,
                [manager_role],
                cost=3,
                description="Certify a source-to-ledger posting after reconciling both journal sides.",
                effects=_effects(
                    ("case_status", "RESOLVED"),
                    ("posting_review_status", "CERTIFIED"),
                    parameters={
                        "certified_ar_debit_usd": "ar_debit_usd",
                        "certified_revenue_credit_usd": "revenue_credit_usd",
                    },
                ),
            ),
            _policy(
                OperationalActionType.ESCALATE_LEDGER_REVIEW,
                both,
                cost=1,
                description="Escalate a ledger posting review that is unbalanced or requires controller certification.",
                effects=_effects(("case_status", "ESCALATED"), ("posting_review_status", "ESCALATED")),
            ),
        ]
        if balanced and actor_role == manager_role:
            return policies, OperationalActionType.CERTIFY_LEDGER_POSTING, {
                "ar_debit_usd": ar_debit,
                "revenue_credit_usd": revenue_credit,
            }
        return policies, OperationalActionType.ESCALATE_LEDGER_REVIEW, {}

    raise ValueError(f"unsupported interactive CompanyWorld family: {family}")


def _outcome_conditions(
    episode: CompanyWorldEpisode,
    policy: ActionPolicy,
    parameters: dict[str, Any],
) -> list[InteractiveOutcomeCondition]:
    conditions: list[InteractiveOutcomeCondition] = []
    for effect in policy.effects:
        if effect.parameter_name is not None:
            if effect.parameter_name not in parameters:
                raise ValueError(
                    f"expected action {policy.action_type} missing parameter {effect.parameter_name}"
                )
            value = parameters[effect.parameter_name]
        else:
            value = effect.constant_value
        conditions.append(
            InteractiveOutcomeCondition(
                object_type=episode.task.target_object_type,
                object_id=episode.task.target_object_id,
                field_name=effect.field_name,
                expected_value=value,
            )
        )
    return conditions


def compile_interactive_episode(episode: CompanyWorldEpisode) -> InteractiveCompanyWorldEpisode:
    manager_role, analyst_role = _role_pair(episode)
    actor_role = manager_role if _privileged(episode) else analyst_role
    policies, expected_action, expected_parameters = _plan(
        episode,
        actor_role,
        manager_role,
        analyst_role,
    )
    expected_policy = next(item for item in policies if item.action_type == expected_action)
    task_id = f"INT-{episode.task.task_id}"
    return InteractiveCompanyWorldEpisode(
        episode_id=f"INT-{episode.episode_id}",
        world_id=episode.world_id,
        investigation=episode,
        task=InteractiveCompanyWorldTask(
            task_id=task_id,
            world_id=episode.world_id,
            task_type=f"INTERACTIVE_{episode.task.task_type}",
            objective=(
                episode.task.objective
                + " Then take the authorized operational action that best resolves or routes the case."
            ),
            target_object_type=episode.task.target_object_type,
            target_object_id=episode.task.target_object_id,
            actor_role=actor_role,
            permitted_systems=episode.task.permitted_systems,
            available_actions=[item.action_type for item in policies],
            action_policies=policies,
            constraints={
                "must_cite_records": True,
                "private_ground_truth_unavailable": True,
                "must_submit_investigation": True,
                "operational_actions_mutate_simulated_state_only": True,
                "unauthorized_actions_are_rejected_and_penalized": True,
            },
            metadata={
                "base_task_type": episode.task.task_type,
                "interactive_distribution_version": INTERACTIVE_DISTRIBUTION_VERSION,
            },
        ),
        initial_state=[
            StateValue(
                object_type=episode.task.target_object_type,
                object_id=episode.task.target_object_id,
                field_name="case_status",
                value="OPEN",
            )
        ],
        oracle=InteractiveCompanyWorldOracle(
            task_id=task_id,
            expected_action_type=expected_action,
            expected_action_parameters=expected_parameters,
            outcome_conditions=_outcome_conditions(
                episode,
                expected_policy,
                expected_parameters,
            ),
            max_applied_actions=1,
        ),
        metadata={
            "base_episode_id": episode.episode_id,
            "base_task_type": episode.task.task_type,
            "interactive_distribution_version": INTERACTIVE_DISTRIBUTION_VERSION,
        },
    )


def compile_interactive_distribution(
    root: str | Path,
    *,
    config: InteractiveCompanyWorldConfig | None = None,
) -> list[InteractiveCompanyWorldEpisode]:
    cfg = config or InteractiveCompanyWorldConfig()
    _, episodes = compile_task_distribution(
        root,
        config=CompanyWorldTaskDistributionConfig(
            per_family=cfg.per_family,
            include_legacy=cfg.include_legacy,
            legacy_limit=cfg.legacy_limit,
        ),
    )
    return [compile_interactive_episode(episode) for episode in episodes]
