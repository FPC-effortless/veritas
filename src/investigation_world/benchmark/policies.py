from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol

from investigation_world.core.models import InvestigationResult


PublicEpisode = dict[str, Any]


class PublicPolicy(Protocol):
    name: str

    def __call__(self, episode: PublicEpisode) -> InvestigationResult: ...


def _records(episode: PublicEpisode) -> list[dict[str, Any]]:
    return list(episode.get("records", []))


def _task(episode: PublicEpisode) -> dict[str, Any]:
    return dict(episode.get("task", {}))


def _record(episode: PublicEpisode, record_type: str, object_id: str | None = None):
    return next(
        (
            item
            for item in _records(episode)
            if item.get("record_type") == record_type
            and (object_id is None or item.get("object_id") == object_id)
        ),
        None,
    )


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _days(start: str, end: str) -> float:
    return round((_dt(end) - _dt(start)).total_seconds() / 86400.0, 2)


def _hours(start: str, end: str) -> float:
    return round((_dt(end) - _dt(start)).total_seconds() / 3600.0, 2)


def _answer(
    target_type: str,
    target_id: str,
    facts: dict[str, Any],
    evidence: list[str],
) -> InvestigationResult:
    return InvestigationResult(
        claims=[
            {
                "object_type": target_type,
                "object_id": target_id,
                "field_name": field_name,
                "value": value,
            }
            for field_name, value in facts.items()
        ],
        evidence=[{"record_id": record_id} for record_id in evidence],
        overall_confidence=1.0,
    )


class EmptyPolicy:
    name = "empty"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult()


class ConclusionOnlyPolicy:
    name = "conclusion_only"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult(conclusion="Investigation complete.", overall_confidence=1.0)


class AlwaysAbstainPolicy:
    name = "always_abstain"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult(
            unknowns=["Insufficient evidence to determine the answer."],
            overall_confidence=0.0,
        )


class CiteEverythingPolicy:
    name = "cite_everything"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        return InvestigationResult(
            evidence=[{"record_id": record["record_id"]} for record in _records(episode)],
            overall_confidence=1.0,
        )


class ProjectionTrustPolicy:
    """Blindly trusts a divergent operational system projection when one exists."""

    name = "projection_trust"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        task = _task(episode)
        target_object_id = task.get("target_object_id")
        target_object_type = task.get("target_object_type")
        for record in _records(episode):
            if (
                record.get("record_type") != "system_projection"
                or record.get("object_id") != target_object_id
            ):
                continue
            fields = record.get("fields", {})
            if not fields:
                continue
            field_name, value = next(iter(fields.items()))
            return _answer(
                target_object_type,
                target_object_id,
                {field_name: value},
                [record["record_id"]],
            )
        return InvestigationResult()


class StuffingPolicy:
    """Copies every visible record field into the answer and cites every record."""

    name = "field_stuffing"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        claims: list[dict[str, Any]] = []
        evidence: list[dict[str, str]] = []
        for record in _records(episode):
            evidence.append({"record_id": record["record_id"]})
            for field_name, value in record.get("fields", {}).items():
                claims.append(
                    {
                        "object_type": record.get("object_type"),
                        "object_id": record.get("object_id"),
                        "field_name": field_name,
                        "value": value,
                    }
                )
        return InvestigationResult(
            claims=claims,
            evidence=evidence,
            overall_confidence=1.0,
        )


class PublicEvidenceReferencePolicy:
    """Deterministic solver that uses only public records and published operational policy."""

    name = "public_evidence_reference"

    def __call__(self, episode: PublicEpisode) -> InvestigationResult:
        task = _task(episode)
        task_type = task.get("task_type")
        target_id = task.get("target_object_id")
        target_type = task.get("target_object_type")

        if task_type == "INVESTIGATE_MISSING_SHIPMENT":
            rec = _record(episode, "carrier_manifest", target_id)
            if rec and "delivered_quantity" in rec.get("fields", {}):
                return _answer(
                    target_type,
                    target_id,
                    {"delivered_quantity": rec["fields"]["delivered_quantity"]},
                    [rec["record_id"]],
                )

        if task_type == "INVESTIGATE_DUPLICATE_INVOICE":
            rec = next(
                (
                    item
                    for item in _records(episode)
                    if item.get("record_type") == "supplier_submission"
                    and target_id in item.get("related_object_ids", [])
                    and str(item.get("fields", {}).get("submission_kind", "")).casefold()
                    == "resubmission"
                ),
                None,
            )
            if rec:
                return _answer(
                    target_type,
                    target_id,
                    {"duplicate_status": "DUPLICATE"},
                    [rec["record_id"]],
                )

        if task_type == "INVESTIGATE_AUTHORITY_BREACH":
            rec = _record(episode, "policy_rule", target_id)
            if rec and "approval_limit_usd" in rec.get("fields", {}):
                return _answer(
                    target_type,
                    target_id,
                    {"approval_limit_usd": rec["fields"]["approval_limit_usd"]},
                    [rec["record_id"]],
                )

        if task_type == "O2C_FULFILLMENT_TIMING":
            order = _record(episode, "sales_order_commitment", target_id)
            shipment = _record(episode, "shipment_timeline")
            if order and shipment:
                delay = max(
                    0.0,
                    _days(
                        order["fields"]["requested_ship_date"],
                        shipment["fields"]["ship_date"],
                    ),
                )
                return _answer(
                    target_type,
                    target_id,
                    {
                        "fulfillment_delay_days": delay,
                        "ship_commitment_status": "LATE" if delay > 0 else "ON_TIME",
                    },
                    [order["record_id"], shipment["record_id"]],
                )

        if task_type == "P2P_RECONCILIATION":
            po = _record(episode, "purchase_order_reconciliation")
            invoice = _record(episode, "supplier_invoice_reconciliation", target_id)
            receipt = _record(episode, "receipt_reconciliation_summary")
            policy = _record(episode, "three_way_match_policy")
            if po and invoice and receipt and policy:
                po_total = float(po["fields"]["order_total_usd"])
                inv_total = float(invoice["fields"]["invoice_amount_usd"])
                tolerance = max(
                    float(policy["fields"]["minimum_amount_tolerance_usd"]),
                    po_total * float(policy["fields"]["amount_tolerance_pct"]) / 100.0,
                )
                quantity_ok = int(receipt["fields"]["received_quantity"]) >= (
                    int(receipt["fields"]["ordered_quantity"])
                    - int(policy["fields"]["quantity_tolerance_units"])
                )
                status = (
                    "MATCH"
                    if abs(inv_total - po_total) <= tolerance and quantity_ok
                    else "REVIEW"
                )
                return _answer(
                    target_type,
                    target_id,
                    {"reconciliation_status": status},
                    [
                        po["record_id"],
                        invoice["record_id"],
                        receipt["record_id"],
                        policy["record_id"],
                    ],
                )

        if task_type == "CUSTOMER_SETTLEMENT_RECONSTRUCTION":
            invoice = _record(episode, "customer_invoice", target_id)
            summary = _record(episode, "cash_application_summary", target_id)
            if invoice and summary:
                amount = float(invoice["fields"]["invoice_amount_usd"])
                settled = round(float(summary["fields"]["applied_amount_usd"]), 2)
                status = (
                    "PAID"
                    if settled >= amount - 0.01
                    else "PARTIAL"
                    if settled > 0
                    else "OPEN"
                )
                return _answer(
                    target_type,
                    target_id,
                    {"settlement_status": status, "settled_amount_usd": settled},
                    [invoice["record_id"], summary["record_id"]],
                )

        if task_type == "PAYMENT_BLOCK_RECOVERY":
            events = [
                item
                for item in _records(episode)
                if item.get("record_type") == "process_event"
            ]
            block = next(
                (
                    item
                    for item in events
                    if item.get("fields", {}).get("activity") == "Payment Block"
                ),
                None,
            )
            remove = next(
                (
                    item
                    for item in events
                    if item.get("fields", {}).get("activity") == "Remove Payment Block"
                ),
                None,
            )
            if block and remove:
                recovery = _hours(
                    block["fields"]["event_time"],
                    remove["fields"]["event_time"],
                )
                return _answer(
                    target_type,
                    target_id,
                    {"payment_block_recovery_hours": recovery},
                    [block["record_id"], remove["record_id"]],
                )

        if task_type == "INCIDENT_SLA_INVESTIGATION":
            ticket = _record(episode, "incident_ticket", target_id)
            policy = _record(episode, "incident_sla_policy")
            events = [
                item
                for item in _records(episode)
                if item.get("record_type") == "process_event"
            ]
            report = next(
                (
                    item
                    for item in events
                    if item.get("fields", {}).get("activity") == "Report"
                ),
                None,
            )
            resolve = next(
                (
                    item
                    for item in events
                    if item.get("fields", {}).get("activity") == "Resolve"
                ),
                None,
            )
            if ticket and policy and report and resolve:
                resolution = _hours(
                    report["fields"]["event_time"],
                    resolve["fields"]["event_time"],
                )
                severity = ticket["fields"]["severity"]
                threshold = float(policy["fields"][f"{severity}_hours"])
                return _answer(
                    target_type,
                    target_id,
                    {
                        "resolution_hours": resolution,
                        "sla_status": "BREACH" if resolution > threshold else "MET",
                    },
                    [
                        ticket["record_id"],
                        policy["record_id"],
                        report["record_id"],
                        resolve["record_id"],
                    ],
                )

        if task_type == "SAFETY_CORRECTIVE_FOLLOWUP":
            incident = _record(episode, "safety_incident", target_id)
            action = _record(episode, "corrective_action")
            policy = _record(episode, "safety_escalation_policy")
            if incident and action and policy:
                severities = set(policy["fields"]["escalate_severities"])
                severity = incident["fields"]["severity"]
                status = action["fields"]["status"]
                escalate = (
                    severity in severities and status != "CLOSED"
                ) or (
                    bool(policy["fields"].get("escalate_if_overdue"))
                    and status == "OVERDUE"
                )
                return _answer(
                    target_type,
                    target_id,
                    {"escalation_required": escalate},
                    [incident["record_id"], action["record_id"], policy["record_id"]],
                )

        if task_type == "CROSS_SYSTEM_CASH_CYCLE":
            order = _record(episode, "sales_order", target_id)
            shipment = _record(episode, "shipment")
            invoice = _record(episode, "customer_invoice")
            payment = _record(episode, "settlement_payment")
            if order and shipment and invoice and payment:
                cycle = _days(
                    order["fields"]["order_date"],
                    payment["fields"]["payment_date"],
                )
                return _answer(
                    target_type,
                    target_id,
                    {"order_to_cash_days": cycle},
                    [
                        order["record_id"],
                        shipment["record_id"],
                        invoice["record_id"],
                        payment["record_id"],
                    ],
                )

        if task_type == "LEDGER_POSTING_RECONSTRUCTION":
            invoice = _record(episode, "customer_invoice_posting_source", target_id)
            entries = [
                item
                for item in _records(episode)
                if item.get("record_type") == "journal_entry"
            ]
            if invoice and entries:
                ar = round(
                    sum(
                        float(item["fields"].get("debit_usd") or 0)
                        for item in entries
                        if item["fields"].get("account")
                        == "1100-Accounts Receivable"
                    ),
                    2,
                )
                revenue = round(
                    sum(
                        float(item["fields"].get("credit_usd") or 0)
                        for item in entries
                        if item["fields"].get("account") == "4000-Sales Revenue"
                    ),
                    2,
                )
                return _answer(
                    target_type,
                    target_id,
                    {"ar_debit_usd": ar, "revenue_credit_usd": revenue},
                    [invoice["record_id"], *[item["record_id"] for item in entries]],
                )

        return InvestigationResult(
            unknowns=["No public evidence rule matched this task."],
            overall_confidence=0.0,
        )


DEFAULT_PUBLIC_POLICIES: tuple[PublicPolicy, ...] = (
    EmptyPolicy(),
    ConclusionOnlyPolicy(),
    AlwaysAbstainPolicy(),
    CiteEverythingPolicy(),
    ProjectionTrustPolicy(),
    StuffingPolicy(),
    PublicEvidenceReferencePolicy(),
)
