from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational_world.models import CompiledOperationalWorld, ScenarioKind


class WorldIntegrityReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, int | float] = Field(default_factory=dict)


def validate_operational_world(world: CompiledOperationalWorld) -> WorldIntegrityReport:
    """Validate structural, temporal and public/private invariants.

    Deliberate scenario violations are allowed only when a matching private finding exists.
    All other inconsistencies are treated as compiler defects.
    """

    errors: list[str] = []
    warnings: list[str] = []
    event_ids = {event.event_id for event in world.events}
    record_ids = {record.record_id for record in world.records}
    entity_ids = set(world.entities)

    if len(event_ids) != len(world.events):
        errors.append("duplicate canonical event IDs")
    if len(record_ids) != len(world.records):
        errors.append("duplicate public record IDs")

    for event in world.events:
        missing_causes = [item for item in event.caused_by if item not in event_ids]
        if missing_causes:
            errors.append(f"{event.event_id} references missing causes: {missing_causes}")
        if event.actor_id and event.actor_id.startswith("EMP-") and event.actor_id not in entity_ids:
            errors.append(f"{event.event_id} references unknown actor {event.actor_id}")

    for record in world.records:
        missing_events = [item for item in record.source_event_ids if item not in event_ids]
        if missing_events:
            errors.append(f"{record.record_id} references missing source events: {missing_events}")

    po_records = {r.object_id: r for r in world.records if r.record_type == "purchase_order"}
    receipt_records = [r for r in world.records if r.record_type == "goods_receipt"]
    invoice_records = [r for r in world.records if r.record_type == "supplier_invoice"]
    payment_records = [r for r in world.records if r.record_type == "payment"]
    ledger_records = [r for r in world.records if r.record_type == "ledger_entry"]

    for receipt in receipt_records:
        po_id = str(receipt.fields.get("po_id", ""))
        if po_id not in po_records:
            errors.append(f"{receipt.record_id} references unknown PO {po_id}")

    invoice_by_id = {record.object_id: record for record in invoice_records}
    for invoice in invoice_records:
        po_id = str(invoice.fields.get("po_id", ""))
        if po_id not in po_records:
            errors.append(f"{invoice.record_id} references unknown PO {po_id}")

    for payment in payment_records:
        invoice_id = str(payment.fields.get("invoice_id", ""))
        if invoice_id not in invoice_by_id:
            errors.append(f"{payment.record_id} references unknown invoice {invoice_id}")

    for ledger in ledger_records:
        debit = float(ledger.fields.get("debit", 0.0))
        credit = float(ledger.fields.get("credit", 0.0))
        if abs(debit - credit) > 1e-6:
            errors.append(f"{ledger.record_id} is not balanced")

    intentional_approval_targets = {
        fact.object_id
        for finding in world.ground_truth
        if finding.scenario_type == ScenarioKind.APPROVAL_BYPASS
        for fact in finding.facts
    }
    for approval in (r for r in world.records if r.record_type == "approval"):
        amount = float(approval.fields.get("amount", 0.0))
        limit = float(approval.fields.get("approval_limit", 0.0))
        if amount > limit and approval.object_id not in intentional_approval_targets:
            errors.append(
                f"{approval.record_id} is an unintended authority violation: {amount} > {limit}"
            )

    public_text = str(world.public_payload())
    for finding in world.ground_truth:
        if finding.finding_id in public_text:
            errors.append(f"private finding ID leaked into public world: {finding.finding_id}")
        if finding.summary and finding.summary in public_text:
            errors.append(f"private finding summary leaked into public world: {finding.finding_id}")
        if finding.scenario_type.value in public_text:
            errors.append(f"private scenario label leaked into public world: {finding.scenario_type}")

    process_counts: dict[str, int] = defaultdict(int)
    for record in world.records:
        process_counts[record.record_type] += 1

    if not po_records:
        errors.append("world contains no purchase orders")
    if not invoice_records:
        errors.append("world contains no supplier invoices")

    return WorldIntegrityReport(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        metrics={
            "entities": len(world.entities),
            "events": len(world.events),
            "records": len(world.records),
            "purchase_orders": len(po_records),
            "invoices": len(invoice_records),
            "payments": len(payment_records),
            "findings": len(world.ground_truth),
        },
    )
