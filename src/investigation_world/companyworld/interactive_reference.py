from __future__ import annotations

from typing import Any

from investigation_world.companyworld.interactive_models import (
    OperationalAction,
    OperationalActionType,
)
from investigation_world.core.models import InvestigationResult


def _claims(result: InvestigationResult) -> dict[str, Any]:
    return {
        str(item.get("field_name")): item.get("value")
        for item in result.claims
        if item.get("field_name") is not None
    }


def _record_field(payload: dict[str, Any], record_type: str, field_name: str, default=None):
    for record in payload.get("investigation", {}).get("records", []):
        if record.get("record_type") == record_type:
            return record.get("fields", {}).get(field_name, default)
    return default


def _authorized(task: dict[str, Any], action_type: OperationalActionType) -> bool:
    role = task.get("actor_role")
    for policy in task.get("action_policies", []):
        if policy.get("action_type") == action_type.value:
            return role in policy.get("allowed_roles", [])
    return False


def _action(
    task: dict[str, Any],
    action_type: OperationalActionType,
    parameters: dict[str, Any] | None = None,
) -> OperationalAction:
    return OperationalAction(
        action_type=action_type,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
        parameters=parameters or {},
    )


def solve_interactive_public(
    payload: dict[str, Any],
) -> tuple[InvestigationResult, OperationalAction]:
    """Solve an interactive episode using only its public evidence, procedures, and actor role."""
    # Keep this import lazy. Importing benchmark.policies while companyworld.__init__ is still
    # initializing causes benchmark.__init__ to import companyworld again from a built wheel.
    from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy

    investigation_payload = payload["investigation"]
    result = PublicEvidenceReferencePolicy()(investigation_payload)
    facts = _claims(result)
    task = payload["task"]
    family = task.get("metadata", {}).get("base_task_type")

    if family == "INVESTIGATE_MISSING_SHIPMENT":
        ordered = float(
            _record_field(payload, "sales_order_fulfillment_summary", "ordered_quantity", 0)
        )
        delivered = float(facts["delivered_quantity"])
        if _authorized(task, OperationalActionType.CREATE_RESHIPMENT):
            return result, _action(
                task,
                OperationalActionType.CREATE_RESHIPMENT,
                {"quantity": max(0.0, ordered - delivered)},
            )
        return result, _action(task, OperationalActionType.ESCALATE_SHIPMENT_EXCEPTION)

    if family == "INVESTIGATE_DUPLICATE_INVOICE":
        if _authorized(task, OperationalActionType.BLOCK_SUPPLIER_INVOICE):
            return result, _action(task, OperationalActionType.BLOCK_SUPPLIER_INVOICE)
        return result, _action(task, OperationalActionType.ESCALATE_INVOICE_EXCEPTION)

    if family == "INVESTIGATE_AUTHORITY_BREACH":
        if _authorized(task, OperationalActionType.RESTORE_AUTHORITY_LIMIT):
            return result, _action(
                task,
                OperationalActionType.RESTORE_AUTHORITY_LIMIT,
                {"approval_limit_usd": facts["approval_limit_usd"]},
            )
        return result, _action(task, OperationalActionType.ESCALATE_AUTHORITY_REPAIR)

    if family == "O2C_FULFILLMENT_TIMING":
        if str(facts["ship_commitment_status"]) == "ON_TIME":
            return result, _action(task, OperationalActionType.CONFIRM_FULFILLMENT)
        if _authorized(task, OperationalActionType.EXPEDITE_ORDER):
            return result, _action(task, OperationalActionType.EXPEDITE_ORDER)
        return result, _action(task, OperationalActionType.ESCALATE_FULFILLMENT_DELAY)

    if family == "P2P_RECONCILIATION":
        if str(facts["reconciliation_status"]) != "MATCH":
            return result, _action(task, OperationalActionType.ROUTE_INVOICE_REVIEW)
        if _authorized(task, OperationalActionType.APPROVE_SUPPLIER_INVOICE):
            return result, _action(task, OperationalActionType.APPROVE_SUPPLIER_INVOICE)
        return result, _action(task, OperationalActionType.REQUEST_INVOICE_APPROVAL)

    if family == "CUSTOMER_SETTLEMENT_RECONSTRUCTION":
        if str(facts["settlement_status"]) == "PAID":
            return result, _action(task, OperationalActionType.CLOSE_AR_CASE)
        return result, _action(task, OperationalActionType.OPEN_COLLECTIONS_CASE)

    if family == "PAYMENT_BLOCK_RECOVERY":
        if float(facts["payment_block_recovery_hours"]) <= 72.0:
            return result, _action(task, OperationalActionType.CLOSE_PAYMENT_BLOCK_CASE)
        return result, _action(task, OperationalActionType.ESCALATE_PAYMENT_BLOCK_RECOVERY)

    if family == "INCIDENT_SLA_INVESTIGATION":
        if str(facts["sla_status"]) == "BREACH":
            return result, _action(task, OperationalActionType.ESCALATE_INCIDENT)
        return result, _action(task, OperationalActionType.CLOSE_INCIDENT_REVIEW)

    if family == "SAFETY_CORRECTIVE_FOLLOWUP":
        if bool(facts["escalation_required"]):
            return result, _action(task, OperationalActionType.ESCALATE_SAFETY_ACTION)
        return result, _action(task, OperationalActionType.CLOSE_SAFETY_REVIEW)

    if family == "CROSS_SYSTEM_CASH_CYCLE":
        if _authorized(task, OperationalActionType.CERTIFY_CASH_CYCLE):
            return result, _action(
                task,
                OperationalActionType.CERTIFY_CASH_CYCLE,
                {"order_to_cash_days": facts["order_to_cash_days"]},
            )
        return result, _action(task, OperationalActionType.ESCALATE_CASH_CYCLE_REVIEW)

    if family == "LEDGER_POSTING_RECONSTRUCTION":
        ar_debit = float(facts["ar_debit_usd"])
        revenue_credit = float(facts["revenue_credit_usd"])
        invoice_amount = float(
            _record_field(payload, "customer_invoice_posting_source", "invoice_amount_usd", 0)
        )
        balanced = (
            abs(ar_debit - revenue_credit) <= 0.01
            and abs(ar_debit - invoice_amount) <= 0.01
        )
        if balanced and _authorized(task, OperationalActionType.CERTIFY_LEDGER_POSTING):
            return result, _action(
                task,
                OperationalActionType.CERTIFY_LEDGER_POSTING,
                {"ar_debit_usd": ar_debit, "revenue_credit_usd": revenue_credit},
            )
        return result, _action(task, OperationalActionType.ESCALATE_LEDGER_REVIEW)

    raise ValueError(f"unsupported public interactive CompanyWorld family: {family}")
