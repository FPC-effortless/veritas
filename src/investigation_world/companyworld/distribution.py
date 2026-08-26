from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable

from investigation_world.companyworld.adapter import CompanyWorldAdapter, _coerce
from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)


DISTRIBUTION_VERSION = "0.2.0"


@dataclass(frozen=True)
class CompanyWorldTaskDistributionConfig:
    per_family: int = 200
    include_legacy: bool = True
    legacy_limit: int | None = None
    families: tuple[str, ...] = (
        "O2C_FULFILLMENT_TIMING",
        "P2P_RECONCILIATION",
        "CUSTOMER_SETTLEMENT_RECONSTRUCTION",
        "PAYMENT_BLOCK_RECOVERY",
        "INCIDENT_SLA_INVESTIGATION",
        "SAFETY_CORRECTIVE_FOLLOWUP",
        "CROSS_SYSTEM_CASH_CYCLE",
        "LEDGER_POSTING_RECONSTRUCTION",
    )


@dataclass(frozen=True)
class _Candidate:
    object_id: str
    stratum: str
    payload: dict[str, Any]


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _days(start: str, end: str) -> float:
    return round((_dt(end) - _dt(start)).total_seconds() / 86400.0, 2)


def _hours(start: str, end: str) -> float:
    return round((_dt(end) - _dt(start)).total_seconds() / 3600.0, 2)


def _stable_rank(world_id: str, family: str, object_id: str) -> str:
    return hashlib.sha256(f"{world_id}|{family}|{object_id}".encode()).hexdigest()


def _balanced_sample(
    world_id: str,
    family: str,
    candidates: Iterable[_Candidate],
    limit: int,
) -> list[_Candidate]:
    if limit <= 0:
        return []
    grouped: dict[str, list[_Candidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.stratum].append(candidate)
    for items in grouped.values():
        items.sort(key=lambda item: _stable_rank(world_id, family, item.object_id))
    strata = sorted(grouped)
    selected: list[_Candidate] = []
    index = 0
    while len(selected) < limit and strata:
        remaining: list[str] = []
        for stratum in strata:
            items = grouped[stratum]
            if index < len(items) and len(selected) < limit:
                selected.append(items[index])
            if index + 1 < len(items):
                remaining.append(stratum)
        strata = remaining
        index += 1
    return selected


def _task_id(family: str, object_id: str) -> str:
    digest = hashlib.sha256(f"{family}|{object_id}".encode()).hexdigest()[:16].upper()
    return f"CWX-{digest}"


def _episode(
    adapter: CompanyWorldAdapter,
    *,
    family: str,
    target_object_type: str,
    target_object_id: str,
    objective: str,
    records: list[CompanyWorldRecord],
    facts: list[OperationalFactTarget],
    answer_class: str,
    expected_resolution: str,
) -> CompanyWorldEpisode:
    records = sorted(
        {record.record_id: record for record in records}.values(),
        key=lambda item: item.record_id,
    )
    systems = sorted({record.system for record in records}, key=lambda item: item.value)
    task_id = _task_id(family, target_object_id)
    return CompanyWorldEpisode(
        episode_id=f"CWX-{task_id}",
        world_id=adapter.world_id,
        task=CompanyWorldTask(
            task_id=task_id,
            world_id=adapter.world_id,
            task_type=family,
            objective=objective,
            target_object_type=target_object_type,
            target_object_id=target_object_id,
            permitted_systems=systems,
            constraints={
                "must_cite_records": True,
                "private_ground_truth_unavailable": True,
                "return_structured_facts": True,
            },
            metadata={
                "adapter_version": DISTRIBUTION_VERSION,
                "distribution": "expanded-v1",
                "record_count": len(records),
                "system_count": len(systems),
            },
        ),
        records=records,
        oracle=CompanyWorldOracle(
            task_id=task_id,
            answer_class=answer_class,
            expected_resolution=expected_resolution,
            answerable=bool(records),
            answerability_reason="Required operational evidence is present in the projected systems.",
            facts=facts,
        ),
        metadata={
            "company_id": adapter._company.get("company_id"),
            "world_seed": _coerce(adapter._company.get("world_seed")),
            "world_start": adapter._company.get("world_start"),
            "world_end": adapter._company.get("world_end"),
            "distribution_version": DISTRIBUTION_VERSION,
        },
    )


def _record(
    adapter: CompanyWorldAdapter,
    *,
    system: CompanySystem,
    record_type: str,
    object_type: str,
    object_id: str,
    fields: dict[str, Any],
    source_file: str,
    suffix: str = "",
    related: list[str] | None = None,
) -> CompanyWorldRecord:
    return adapter._record(
        system=system,
        record_type=record_type,
        object_type=object_type,
        object_id=object_id,
        fields=fields,
        source_file=source_file,
        suffix=suffix,
        related_object_ids=related,
    )


def _o2c_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    shipments = adapter._index("canonical/shipments.csv.gz", "sales_order_id")
    out: list[_Candidate] = []
    for order in adapter._rows("canonical/sales_orders.csv.gz"):
        shipment = shipments.get(order.get("sales_order_id", ""))
        if not shipment:
            continue
        delay = max(0.0, _days(order["requested_ship_date"], shipment["ship_date"]))
        out.append(
            _Candidate(
                order["sales_order_id"],
                "LATE" if delay > 0 else "ON_TIME",
                {"order": order, "shipment": shipment, "delay": delay},
            )
        )
    return out


def _build_o2c(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    order = candidate.payload["order"]
    shipment = candidate.payload["shipment"]
    order_id = order["sales_order_id"]
    erp = _record(
        adapter,
        system=CompanySystem.ERP,
        record_type="sales_order_commitment",
        object_type="SALES_ORDER",
        object_id=order_id,
        fields={
            "customer_id": order["customer_id"],
            "order_date": order["order_date"],
            "requested_ship_date": order["requested_ship_date"],
            "fulfillment_facility_id": order["fulfillment_facility_id"],
            "order_total_usd": _coerce(order["order_total_usd"]),
        },
        source_file="canonical/sales_orders.csv.gz",
    )
    wms = _record(
        adapter,
        system=CompanySystem.WMS,
        record_type="shipment_timeline",
        object_type="SHIPMENT",
        object_id=shipment["shipment_id"],
        fields={
            "sales_order_id": order_id,
            "ship_date": shipment["ship_date"],
            "delivered_date": shipment["delivered_date"],
            "carrier": shipment["carrier"],
        },
        source_file="canonical/shipments.csv.gz",
        related=[order_id],
    )
    support = [erp.record_id, wms.record_id]
    delay = candidate.payload["delay"]
    facts = [
        OperationalFactTarget(
            object_type="SALES_ORDER",
            object_id=order_id,
            field_name="fulfillment_delay_days",
            expected_value=delay,
            supporting_record_ids=support,
            support_mode="listed_count",
            minimum_support_records=2,
        ),
        OperationalFactTarget(
            object_type="SALES_ORDER",
            object_id=order_id,
            field_name="ship_commitment_status",
            expected_value="LATE" if delay > 0 else "ON_TIME",
            supporting_record_ids=support,
            support_mode="listed_count",
            minimum_support_records=2,
        ),
    ]
    return _episode(
        adapter,
        family="O2C_FULFILLMENT_TIMING",
        target_object_type="SALES_ORDER",
        target_object_id=order_id,
        objective=(
            f"Reconstruct fulfillment timing for sales order {order_id}. Determine whether the "
            "requested ship commitment was met and quantify any fulfillment delay using ERP and "
            "warehouse evidence."
        ),
        records=[erp, wms],
        facts=facts,
        answer_class="o2c_fulfillment_timing",
        expected_resolution="Reconcile the sales-order commitment with the actual shipment timeline.",
    )


def _p2p_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    po_index = adapter._index("canonical/purchase_orders.csv.gz", "purchase_order_id")
    lines = adapter._group("canonical/purchase_order_lines.csv.gz", "purchase_order_id")
    receipts = adapter._group("canonical/goods_receipts.csv.gz", "purchase_order_id")
    out: list[_Candidate] = []
    for invoice in adapter._rows("canonical/supplier_invoices.csv.gz"):
        po = po_index.get(invoice.get("purchase_order_id", ""))
        if not po:
            continue
        po_id = po["purchase_order_id"]
        ordered = sum(
            int(float(item.get("ordered_quantity") or 0))
            for item in lines.get(po_id, [])
        )
        received = sum(
            int(float(item.get("received_quantity") or 0))
            for item in receipts.get(po_id, [])
        )
        po_total = float(po["order_total_usd"])
        invoice_total = float(invoice["invoice_amount_usd"])
        tolerance = max(10.0, po_total * 0.002)
        status = (
            "MATCH"
            if abs(invoice_total - po_total) <= tolerance and received >= ordered
            else "REVIEW"
        )
        out.append(
            _Candidate(
                invoice["supplier_invoice_id"],
                status,
                {
                    "invoice": invoice,
                    "po": po,
                    "ordered": ordered,
                    "received": received,
                    "status": status,
                },
            )
        )
    return out


def _build_p2p(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    invoice = candidate.payload["invoice"]
    po = candidate.payload["po"]
    invoice_id = invoice["supplier_invoice_id"]
    po_id = po["purchase_order_id"]
    po_record = _record(
        adapter,
        system=CompanySystem.ERP,
        record_type="purchase_order_reconciliation",
        object_type="PURCHASE_ORDER",
        object_id=po_id,
        fields={
            "supplier_id": po["supplier_id"],
            "order_total_usd": _coerce(po["order_total_usd"]),
            "match_policy": po["match_policy"],
            "order_date": po["order_date"],
        },
        source_file="canonical/purchase_orders.csv.gz",
        related=[invoice_id],
    )
    inv_record = _record(
        adapter,
        system=CompanySystem.AP_WORKFLOW,
        record_type="supplier_invoice_reconciliation",
        object_type="SUPPLIER_INVOICE",
        object_id=invoice_id,
        fields={
            "purchase_order_id": po_id,
            "supplier_id": invoice["supplier_id"],
            "invoice_amount_usd": _coerce(invoice["invoice_amount_usd"]),
            "invoice_date": invoice["invoice_date"],
            "due_date": invoice["due_date"],
        },
        source_file="canonical/supplier_invoices.csv.gz",
        related=[po_id],
    )
    receipt_record = _record(
        adapter,
        system=CompanySystem.WMS,
        record_type="receipt_reconciliation_summary",
        object_type="PURCHASE_ORDER",
        object_id=po_id,
        fields={
            "ordered_quantity": candidate.payload["ordered"],
            "received_quantity": candidate.payload["received"],
        },
        source_file="derived/p2p_receipt_summary",
        related=[invoice_id],
    )
    policy_record = _record(
        adapter,
        system=CompanySystem.AP_WORKFLOW,
        record_type="three_way_match_policy",
        object_type="MATCH_POLICY",
        object_id="POLICY-P2P-3WAY-V1",
        fields={
            "amount_tolerance_pct": 0.2,
            "minimum_amount_tolerance_usd": 10.0,
            "quantity_tolerance_units": 0,
        },
        source_file="derived/p2p_match_policy",
        related=[po_id, invoice_id],
    )
    support = [
        po_record.record_id,
        inv_record.record_id,
        receipt_record.record_id,
        policy_record.record_id,
    ]
    fact = OperationalFactTarget(
        object_type="SUPPLIER_INVOICE",
        object_id=invoice_id,
        field_name="reconciliation_status",
        expected_value=candidate.payload["status"],
        supporting_record_ids=support,
        support_mode="listed_count",
        minimum_support_records=4,
    )
    return _episode(
        adapter,
        family="P2P_RECONCILIATION",
        target_object_type="SUPPLIER_INVOICE",
        target_object_id=invoice_id,
        objective=(
            f"Perform a three-way reconciliation for supplier invoice {invoice_id}. Use the "
            "purchase order, receiving summary, invoice, and matching policy to determine whether "
            "it should match automatically or require review."
        ),
        records=[po_record, inv_record, receipt_record, policy_record],
        facts=[fact],
        answer_class="p2p_reconciliation",
        expected_resolution=(
            "Apply the published matching tolerance to PO, receipt, and supplier-invoice evidence."
        ),
    )


def _settlement_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    payments = adapter._group("canonical/customer_payments.csv.gz", "customer_invoice_id")
    out: list[_Candidate] = []
    for invoice in adapter._rows("canonical/customer_invoices.csv.gz"):
        amount = float(invoice["invoice_amount_usd"])
        linked = payments.get(invoice["customer_invoice_id"], [])
        paid = round(sum(float(item.get("amount_usd") or 0) for item in linked), 2)
        status = "PAID" if paid >= amount - 0.01 else "PARTIAL" if paid > 0 else "OPEN"
        out.append(
            _Candidate(
                invoice["customer_invoice_id"],
                status,
                {"invoice": invoice, "payments": linked, "paid": paid, "status": status},
            )
        )
    return out


def _build_settlement(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    invoice = candidate.payload["invoice"]
    invoice_id = invoice["customer_invoice_id"]
    inv_record = _record(
        adapter,
        system=CompanySystem.AR_WORKFLOW,
        record_type="customer_invoice",
        object_type="CUSTOMER_INVOICE",
        object_id=invoice_id,
        fields={
            "sales_order_id": invoice["sales_order_id"],
            "customer_id": invoice["customer_id"],
            "invoice_date": invoice["invoice_date"],
            "due_date": invoice["due_date"],
            "invoice_amount_usd": _coerce(invoice["invoice_amount_usd"]),
        },
        source_file="canonical/customer_invoices.csv.gz",
    )
    summary = _record(
        adapter,
        system=CompanySystem.TREASURY,
        record_type="cash_application_summary",
        object_type="CUSTOMER_INVOICE",
        object_id=invoice_id,
        fields={
            "payment_count": len(candidate.payload["payments"]),
            "applied_amount_usd": candidate.payload["paid"],
            "last_payment_date": max(
                (item["payment_date"] for item in candidate.payload["payments"]),
                default=None,
            ),
        },
        source_file="derived/customer_cash_application",
    )
    support = [inv_record.record_id, summary.record_id]
    facts = [
        OperationalFactTarget(
            object_type="CUSTOMER_INVOICE",
            object_id=invoice_id,
            field_name="settlement_status",
            expected_value=candidate.payload["status"],
            supporting_record_ids=support,
            support_mode="listed_count",
            minimum_support_records=2,
        ),
        OperationalFactTarget(
            object_type="CUSTOMER_INVOICE",
            object_id=invoice_id,
            field_name="settled_amount_usd",
            expected_value=candidate.payload["paid"],
            supporting_record_ids=support,
            support_mode="listed_count",
            minimum_support_records=2,
        ),
    ]
    return _episode(
        adapter,
        family="CUSTOMER_SETTLEMENT_RECONSTRUCTION",
        target_object_type="CUSTOMER_INVOICE",
        target_object_id=invoice_id,
        objective=(
            f"Reconstruct settlement for customer invoice {invoice_id}. Reconcile the invoice "
            "amount with treasury cash application and determine both the settled amount and the "
            "resulting settlement status."
        ),
        records=[inv_record, summary],
        facts=facts,
        answer_class="customer_settlement",
        expected_resolution=(
            "Reconcile accounts-receivable and treasury evidence without trusting the invoice status field."
        ),
    )


def _recovery_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    events = adapter._group("canonical/process_events.csv.gz", "process_instance_id")
    out: list[_Candidate] = []
    for po_id, rows in events.items():
        p2p = sorted(
            (row for row in rows if row.get("procedure_id") == "PROC-P2P"),
            key=lambda item: item["event_time"],
        )
        block = next((row for row in p2p if row.get("activity") == "Payment Block"), None)
        remove = next(
            (row for row in p2p if row.get("activity") == "Remove Payment Block"),
            None,
        )
        if not block or not remove:
            continue
        recovery = _hours(block["event_time"], remove["event_time"])
        out.append(
            _Candidate(
                po_id,
                "FAST" if recovery <= 72 else "SLOW",
                {"block": block, "remove": remove, "recovery": recovery},
            )
        )
    return out


def _process_record(
    adapter: CompanyWorldAdapter,
    event: dict[str, str],
    related: list[str] | None = None,
) -> CompanyWorldRecord:
    return _record(
        adapter,
        system=CompanySystem.PROCESS,
        record_type="process_event",
        object_type="PROCESS_EVENT",
        object_id=event["process_event_id"],
        fields={
            "process_instance_id": event["process_instance_id"],
            "procedure_id": event["procedure_id"],
            "activity": event["activity"],
            "event_time": event["event_time"],
            "resource_id": event["resource_id"],
        },
        source_file="canonical/process_events.csv.gz",
        related=[event["process_instance_id"], *(related or [])],
    )


def _build_recovery(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    po_id = candidate.object_id
    block = _process_record(adapter, candidate.payload["block"])
    remove = _process_record(adapter, candidate.payload["remove"])
    support = [block.record_id, remove.record_id]
    fact = OperationalFactTarget(
        object_type="PURCHASE_ORDER",
        object_id=po_id,
        field_name="payment_block_recovery_hours",
        expected_value=candidate.payload["recovery"],
        supporting_record_ids=support,
        support_mode="listed_count",
        minimum_support_records=2,
    )
    return _episode(
        adapter,
        family="PAYMENT_BLOCK_RECOVERY",
        target_object_type="PURCHASE_ORDER",
        target_object_id=po_id,
        objective=(
            f"Reconstruct the payment-block recovery for purchase order {po_id}. Determine the "
            "elapsed time between the payment block and its removal from process evidence."
        ),
        records=[block, remove],
        facts=[fact],
        answer_class="payment_block_recovery",
        expected_resolution=(
            "Use the process timestamps for block creation and removal to quantify recovery time."
        ),
    )


INCIDENT_SLA_HOURS = {"P1": 4.0, "P2": 12.0, "P3": 72.0, "P4": 168.0}


def _incident_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    process = adapter._group("canonical/process_events.csv.gz", "process_instance_id")
    out: list[_Candidate] = []
    for ticket in adapter._rows("canonical/incident_tickets.csv.gz"):
        incident_id = ticket["incident_ticket_id"]
        events = sorted(
            (
                row
                for row in process.get(incident_id, [])
                if row.get("procedure_id") == "PROC-INC"
            ),
            key=lambda item: item["event_time"],
        )
        report = next((row for row in events if row.get("activity") == "Report"), None)
        resolve = next((row for row in events if row.get("activity") == "Resolve"), None)
        if not report or not resolve:
            continue
        threshold = INCIDENT_SLA_HOURS[ticket["severity"]]
        resolution = _hours(report["event_time"], resolve["event_time"])
        status = "BREACH" if resolution > threshold else "MET"
        out.append(
            _Candidate(
                incident_id,
                status,
                {
                    "ticket": ticket,
                    "report": report,
                    "resolve": resolve,
                    "resolution": resolution,
                    "status": status,
                },
            )
        )
    return out


def _build_incident(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    ticket = candidate.payload["ticket"]
    incident_id = ticket["incident_ticket_id"]
    ticket_record = _record(
        adapter,
        system=CompanySystem.ITSM,
        record_type="incident_ticket",
        object_type="INCIDENT_TICKET",
        object_id=incident_id,
        fields={
            "service": ticket["service"],
            "created_at": ticket["created_at"],
            "severity": ticket["severity"],
            "assigned_team": ticket["assigned_team"],
            "reassignments": _coerce(ticket["reassignments"]),
            "resolved_at": ticket["resolved_at"],
        },
        source_file="canonical/incident_tickets.csv.gz",
    )
    sla = _record(
        adapter,
        system=CompanySystem.ITSM,
        record_type="incident_sla_policy",
        object_type="INCIDENT_POLICY",
        object_id="POLICY-INC-SLA-V1",
        fields={"P1_hours": 4.0, "P2_hours": 12.0, "P3_hours": 72.0, "P4_hours": 168.0},
        source_file="derived/incident_sla_policy",
        related=[incident_id],
    )
    report = candidate.payload["report"]
    resolve = candidate.payload["resolve"]
    process_records = [
        _process_record(adapter, event, [incident_id]) for event in (report, resolve)
    ]
    support_resolution = [item.record_id for item in process_records]
    facts = [
        OperationalFactTarget(
            object_type="INCIDENT_TICKET",
            object_id=incident_id,
            field_name="resolution_hours",
            expected_value=candidate.payload["resolution"],
            supporting_record_ids=support_resolution,
            support_mode="listed_count",
            minimum_support_records=2,
        ),
        OperationalFactTarget(
            object_type="INCIDENT_TICKET",
            object_id=incident_id,
            field_name="sla_status",
            expected_value=candidate.payload["status"],
            supporting_record_ids=[ticket_record.record_id, sla.record_id, *support_resolution],
            support_mode="listed_count",
            minimum_support_records=4,
        ),
    ]
    return _episode(
        adapter,
        family="INCIDENT_SLA_INVESTIGATION",
        target_object_type="INCIDENT_TICKET",
        target_object_id=incident_id,
        objective=(
            f"Investigate incident {incident_id}. Reconstruct resolution duration and determine "
            "whether the severity-specific response SLA was met using ticket, process, and policy evidence."
        ),
        records=[ticket_record, sla, *process_records],
        facts=facts,
        answer_class="incident_sla",
        expected_resolution=(
            "Compare reconstructed incident duration with the published severity-specific SLA."
        ),
    )


SAFETY_ESCALATION_SEVERITIES = {"SERIOUS", "DAYS_AWAY"}


def _safety_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    actions = adapter._group("canonical/corrective_actions.csv.gz", "source_id")
    out: list[_Candidate] = []
    for incident in adapter._rows("canonical/safety_incidents.csv.gz"):
        linked = [
            row
            for row in actions.get(incident["safety_incident_id"], [])
            if row.get("source_type") == "SAFETY_INCIDENT"
        ]
        if not linked:
            continue
        action = linked[0]
        escalation = (
            incident["severity"] in SAFETY_ESCALATION_SEVERITIES
            and action["status"] != "CLOSED"
        ) or action["status"] == "OVERDUE"
        out.append(
            _Candidate(
                incident["safety_incident_id"],
                "ESCALATE" if escalation else "NO_ESCALATION",
                {"incident": incident, "action": action, "escalation": escalation},
            )
        )
    return out


def _build_safety(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    incident = candidate.payload["incident"]
    action = candidate.payload["action"]
    incident_id = incident["safety_incident_id"]
    incident_record = _record(
        adapter,
        system=CompanySystem.SAFETY,
        record_type="safety_incident",
        object_type="SAFETY_INCIDENT",
        object_id=incident_id,
        fields={
            "facility_id": incident["facility_id"],
            "event_time": incident["event_time"],
            "incident_type": incident["incident_type"],
            "severity": incident["severity"],
            "days_away": _coerce(incident["days_away"]),
            "affected_role_profile_id": incident["affected_role_profile_id"],
        },
        source_file="canonical/safety_incidents.csv.gz",
    )
    action_record = _record(
        adapter,
        system=CompanySystem.COMPLIANCE,
        record_type="corrective_action",
        object_type="CORRECTIVE_ACTION",
        object_id=action["corrective_action_id"],
        fields={
            "source_type": action["source_type"],
            "source_id": action["source_id"],
            "owner_id": action["owner_id"],
            "due_date": action["due_date"],
            "status": action["status"],
        },
        source_file="canonical/corrective_actions.csv.gz",
        related=[incident_id],
    )
    policy = _record(
        adapter,
        system=CompanySystem.COMPLIANCE,
        record_type="safety_escalation_policy",
        object_type="SAFETY_POLICY",
        object_id="POLICY-SAFETY-ESC-V1",
        fields={
            "escalate_severities": sorted(SAFETY_ESCALATION_SEVERITIES),
            "escalate_if_overdue": True,
            "escalate_if_serious_action_open": True,
        },
        source_file="derived/safety_escalation_policy",
        related=[incident_id],
    )
    support = [incident_record.record_id, action_record.record_id, policy.record_id]
    fact = OperationalFactTarget(
        object_type="SAFETY_INCIDENT",
        object_id=incident_id,
        field_name="escalation_required",
        expected_value=candidate.payload["escalation"],
        supporting_record_ids=support,
        support_mode="listed_count",
        minimum_support_records=3,
    )
    return _episode(
        adapter,
        family="SAFETY_CORRECTIVE_FOLLOWUP",
        target_object_type="SAFETY_INCIDENT",
        target_object_id=incident_id,
        objective=(
            f"Review safety incident {incident_id} and its corrective action. Apply the published "
            "escalation policy to determine whether management escalation is required."
        ),
        records=[incident_record, action_record, policy],
        facts=[fact],
        answer_class="safety_corrective_followup",
        expected_resolution=(
            "Combine incident severity, corrective-action state, and escalation policy."
        ),
    )


def _cash_cycle_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    shipments = adapter._index("canonical/shipments.csv.gz", "sales_order_id")
    invoices = adapter._index("canonical/customer_invoices.csv.gz", "sales_order_id")
    payments = adapter._group("canonical/customer_payments.csv.gz", "customer_invoice_id")
    raw: list[tuple[dict[str, str], dict[str, str], dict[str, str], list[dict[str, str]], float]] = []
    for order in adapter._rows("canonical/sales_orders.csv.gz"):
        order_id = order["sales_order_id"]
        shipment = shipments.get(order_id)
        invoice = invoices.get(order_id)
        if not shipment or not invoice:
            continue
        linked = payments.get(invoice["customer_invoice_id"], [])
        paid = sum(float(item.get("amount_usd") or 0) for item in linked)
        if paid < float(invoice["invoice_amount_usd"]) - 0.01 or not linked:
            continue
        last_payment = max(linked, key=lambda item: item["payment_date"])
        cycle = _days(order["order_date"], last_payment["payment_date"])
        raw.append((order, shipment, invoice, linked, cycle))
    median = sorted(item[4] for item in raw)[len(raw) // 2] if raw else 0.0
    return [
        _Candidate(
            order["sales_order_id"],
            "LONG" if cycle > median else "SHORT",
            {
                "order": order,
                "shipment": shipment,
                "invoice": invoice,
                "payments": linked,
                "cycle": cycle,
            },
        )
        for order, shipment, invoice, linked, cycle in raw
    ]


def _build_cash_cycle(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    order = candidate.payload["order"]
    shipment = candidate.payload["shipment"]
    invoice = candidate.payload["invoice"]
    payments = candidate.payload["payments"]
    order_id = order["sales_order_id"]
    order_record = _record(
        adapter,
        system=CompanySystem.ERP,
        record_type="sales_order",
        object_type="SALES_ORDER",
        object_id=order_id,
        fields={
            "order_date": order["order_date"],
            "customer_id": order["customer_id"],
            "order_total_usd": _coerce(order["order_total_usd"]),
        },
        source_file="canonical/sales_orders.csv.gz",
    )
    shipment_record = _record(
        adapter,
        system=CompanySystem.WMS,
        record_type="shipment",
        object_type="SHIPMENT",
        object_id=shipment["shipment_id"],
        fields={
            "sales_order_id": order_id,
            "ship_date": shipment["ship_date"],
            "delivered_date": shipment["delivered_date"],
        },
        source_file="canonical/shipments.csv.gz",
        related=[order_id],
    )
    invoice_record = _record(
        adapter,
        system=CompanySystem.AR_WORKFLOW,
        record_type="customer_invoice",
        object_type="CUSTOMER_INVOICE",
        object_id=invoice["customer_invoice_id"],
        fields={
            "sales_order_id": order_id,
            "invoice_date": invoice["invoice_date"],
            "invoice_amount_usd": _coerce(invoice["invoice_amount_usd"]),
        },
        source_file="canonical/customer_invoices.csv.gz",
        related=[order_id],
    )
    last_payment = max(payments, key=lambda item: item["payment_date"])
    payment_record = _record(
        adapter,
        system=CompanySystem.TREASURY,
        record_type="settlement_payment",
        object_type="CUSTOMER_PAYMENT",
        object_id=last_payment["payment_id"],
        fields={
            "customer_invoice_id": invoice["customer_invoice_id"],
            "payment_date": last_payment["payment_date"],
            "amount_usd": _coerce(last_payment["amount_usd"]),
        },
        source_file="canonical/customer_payments.csv.gz",
        related=[order_id, invoice["customer_invoice_id"]],
    )
    support = [
        order_record.record_id,
        shipment_record.record_id,
        invoice_record.record_id,
        payment_record.record_id,
    ]
    fact = OperationalFactTarget(
        object_type="SALES_ORDER",
        object_id=order_id,
        field_name="order_to_cash_days",
        expected_value=candidate.payload["cycle"],
        supporting_record_ids=support,
        support_mode="listed_count",
        minimum_support_records=4,
    )
    return _episode(
        adapter,
        family="CROSS_SYSTEM_CASH_CYCLE",
        target_object_type="SALES_ORDER",
        target_object_id=order_id,
        objective=(
            f"Reconstruct the end-to-end order-to-cash cycle for sales order {order_id}. Use ERP, "
            "warehouse, receivables, and treasury records to determine elapsed days from order "
            "creation to final settlement."
        ),
        records=[order_record, shipment_record, invoice_record, payment_record],
        facts=[fact],
        answer_class="cross_system_cash_cycle",
        expected_resolution=(
            "Reconstruct the linked order, shipment, invoice, and final payment timeline."
        ),
    )


def _ledger_candidates(adapter: CompanyWorldAdapter) -> list[_Candidate]:
    entries = adapter._group("canonical/ledger_entries.csv.gz", "object_id")
    out: list[_Candidate] = []
    for invoice in adapter._rows("canonical/customer_invoices.csv.gz"):
        rows = entries.get(invoice["customer_invoice_id"], [])
        ar_debit = round(
            sum(
                float(row.get("debit_usd") or 0)
                for row in rows
                if row.get("account") == "1100-Accounts Receivable"
            ),
            2,
        )
        revenue_credit = round(
            sum(
                float(row.get("credit_usd") or 0)
                for row in rows
                if row.get("account") == "4000-Sales Revenue"
            ),
            2,
        )
        if ar_debit <= 0 or revenue_credit <= 0:
            continue
        amount = float(invoice["invoice_amount_usd"])
        out.append(
            _Candidate(
                invoice["customer_invoice_id"],
                "LARGE" if amount >= 50000 else "SMALL",
                {
                    "invoice": invoice,
                    "rows": rows,
                    "ar_debit": ar_debit,
                    "revenue_credit": revenue_credit,
                },
            )
        )
    return out


def _build_ledger(adapter: CompanyWorldAdapter, candidate: _Candidate) -> CompanyWorldEpisode:
    invoice = candidate.payload["invoice"]
    invoice_id = invoice["customer_invoice_id"]
    invoice_record = _record(
        adapter,
        system=CompanySystem.AR_WORKFLOW,
        record_type="customer_invoice_posting_source",
        object_type="CUSTOMER_INVOICE",
        object_id=invoice_id,
        fields={
            "invoice_date": invoice["invoice_date"],
            "invoice_amount_usd": _coerce(invoice["invoice_amount_usd"]),
            "customer_id": invoice["customer_id"],
        },
        source_file="canonical/customer_invoices.csv.gz",
    )
    ledger_records: list[CompanyWorldRecord] = []
    for row in candidate.payload["rows"]:
        if row.get("account") not in {
            "1100-Accounts Receivable",
            "4000-Sales Revenue",
        }:
            continue
        ledger_records.append(
            _record(
                adapter,
                system=CompanySystem.LEDGER,
                record_type="journal_entry",
                object_type="LEDGER_ENTRY",
                object_id=row["journal_entry_id"],
                fields={
                    "transaction_id": row["transaction_id"],
                    "entry_date": row["entry_date"],
                    "description": row["description"],
                    "account": row["account"],
                    "debit_usd": _coerce(row["debit_usd"]),
                    "credit_usd": _coerce(row["credit_usd"]),
                },
                source_file="canonical/ledger_entries.csv.gz",
                related=[invoice_id],
            )
        )
    ar_support = [
        invoice_record.record_id,
        *[
            record.record_id
            for record in ledger_records
            if record.fields.get("account") == "1100-Accounts Receivable"
        ],
    ]
    rev_support = [
        invoice_record.record_id,
        *[
            record.record_id
            for record in ledger_records
            if record.fields.get("account") == "4000-Sales Revenue"
        ],
    ]
    facts = [
        OperationalFactTarget(
            object_type="CUSTOMER_INVOICE",
            object_id=invoice_id,
            field_name="ar_debit_usd",
            expected_value=candidate.payload["ar_debit"],
            supporting_record_ids=ar_support,
            support_mode="listed_count",
            minimum_support_records=len(ar_support),
        ),
        OperationalFactTarget(
            object_type="CUSTOMER_INVOICE",
            object_id=invoice_id,
            field_name="revenue_credit_usd",
            expected_value=candidate.payload["revenue_credit"],
            supporting_record_ids=rev_support,
            support_mode="listed_count",
            minimum_support_records=len(rev_support),
        ),
    ]
    return _episode(
        adapter,
        family="LEDGER_POSTING_RECONSTRUCTION",
        target_object_type="CUSTOMER_INVOICE",
        target_object_id=invoice_id,
        objective=(
            f"Reconstruct the accounting posting for customer invoice {invoice_id}. Determine the "
            "Accounts Receivable debit and Sales Revenue credit from the source invoice and journal evidence."
        ),
        records=[invoice_record, *ledger_records],
        facts=facts,
        answer_class="ledger_posting_reconstruction",
        expected_resolution=(
            "Reconcile the source invoice to the relevant debit and credit journal lines."
        ),
    )


_FAMILY_BUILDERS: dict[
    str,
    tuple[
        Callable[[CompanyWorldAdapter], list[_Candidate]],
        Callable[[CompanyWorldAdapter, _Candidate], CompanyWorldEpisode],
    ],
] = {
    "O2C_FULFILLMENT_TIMING": (_o2c_candidates, _build_o2c),
    "P2P_RECONCILIATION": (_p2p_candidates, _build_p2p),
    "CUSTOMER_SETTLEMENT_RECONSTRUCTION": (_settlement_candidates, _build_settlement),
    "PAYMENT_BLOCK_RECOVERY": (_recovery_candidates, _build_recovery),
    "INCIDENT_SLA_INVESTIGATION": (_incident_candidates, _build_incident),
    "SAFETY_CORRECTIVE_FOLLOWUP": (_safety_candidates, _build_safety),
    "CROSS_SYSTEM_CASH_CYCLE": (_cash_cycle_candidates, _build_cash_cycle),
    "LEDGER_POSTING_RECONSTRUCTION": (_ledger_candidates, _build_ledger),
}


def compile_expanded_episodes(
    adapter: CompanyWorldAdapter,
    *,
    per_family: int = 200,
    families: tuple[str, ...] | None = None,
) -> list[CompanyWorldEpisode]:
    selected_families = families or tuple(_FAMILY_BUILDERS)
    unknown = sorted(set(selected_families) - set(_FAMILY_BUILDERS))
    if unknown:
        raise ValueError(f"unknown CompanyWorld task families: {', '.join(unknown)}")
    episodes: list[CompanyWorldEpisode] = []
    for family in selected_families:
        candidate_fn, build_fn = _FAMILY_BUILDERS[family]
        candidates = candidate_fn(adapter)
        sampled = _balanced_sample(adapter.world_id, family, candidates, per_family)
        episodes.extend(build_fn(adapter, candidate) for candidate in sampled)
    return episodes


def compile_task_distribution(
    root: str | Path,
    *,
    config: CompanyWorldTaskDistributionConfig | None = None,
) -> tuple[CompanyWorldAdapter, list[CompanyWorldEpisode]]:
    cfg = config or CompanyWorldTaskDistributionConfig()
    adapter = CompanyWorldAdapter(root)
    report = adapter.validate()
    if not report.valid:
        raise ValueError("invalid CompanyWorld dataset: " + "; ".join(report.errors))
    episodes: list[CompanyWorldEpisode] = []
    if cfg.include_legacy:
        episodes.extend(adapter.compile_episodes(limit=cfg.legacy_limit))
    episodes.extend(
        compile_expanded_episodes(
            adapter,
            per_family=cfg.per_family,
            families=cfg.families,
        )
    )
    return adapter, episodes
