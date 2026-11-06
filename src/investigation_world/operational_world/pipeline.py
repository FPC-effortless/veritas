from __future__ import annotations

from random import Random

from investigation_world.operational_world.compiler import OperationalWorldCompiler as _BaseCompiler
from investigation_world.operational_world.models import (
    CompanySizeBand,
    CompiledOperationalWorld,
    IndustryFamily,
    OperationalEntity,
    OperationalRecord,
    OperationalWorldSpec,
    RegionGroup,
    ScenarioKind,
)


class OperationalWorldCompiler(_BaseCompiler):
    """Production compiler wrapper with integrity and calibration normalization.

    The base compiler intentionally keeps process generation straightforward. This wrapper
    rejects incompatible calibration profiles, prevents tiny auto-generated micro worlds from
    violating the department ontology, applies empirical procurement-structure calibration
    when available, and repairs accidental authority gaps by routing otherwise-valid approvals
    to a synthetic executive approver. Explicit APPROVAL_BYPASS scenarios remain untouched.
    """

    def compile(self, spec: OperationalWorldSpec) -> CompiledOperationalWorld:
        self._validate_calibration_compatibility(spec)
        normalized_spec = spec
        if spec.employee_count is None and spec.size_band == CompanySizeBand.MICRO:
            normalized_spec = spec.model_copy(update={"employee_count": 8 + (spec.seed % 13)})
        world = super().compile(normalized_spec)
        self._apply_calibrated_procurement_structure(world)
        self._apply_calibrated_financial_snapshot(world)
        self._repair_unintended_authority_gaps(world)
        return world

    def _validate_calibration_compatibility(self, spec: OperationalWorldSpec) -> None:
        calibration = self._calibration
        if calibration is None:
            return
        if calibration.region not in {RegionGroup.GLOBAL, spec.region}:
            raise ValueError(
                f"calibration region {calibration.region} cannot generate world region {spec.region}"
            )
        if calibration.industry not in {IndustryFamily.GENERIC, spec.industry}:
            raise ValueError(
                f"calibration industry {calibration.industry} cannot generate world industry {spec.industry}"
            )
        if not calibration.applies_to_size(spec.size_band):
            raise ValueError(
                f"calibration size band {calibration.size_band} ({calibration.size_scope}) cannot generate {spec.size_band} world"
            )

    @staticmethod
    def _apply_calibrated_procurement_structure(world: CompiledOperationalWorld) -> None:
        """Project empirical procurement complexity into generated operational records."""

        item_distribution = world.calibration.distributions.get("procurement.items_per_tender")
        party_distribution = world.calibration.distributions.get("procurement.parties_per_process")
        if item_distribution is None and party_distribution is None:
            return

        rng = Random(world.spec.seed ^ 0x5A17C0DE)
        event_by_id = {event.event_id: event for event in world.events}
        receipts_by_po: dict[str, list[OperationalRecord]] = {}
        invoices_by_po: dict[str, list[OperationalRecord]] = {}
        for record in world.records:
            if record.record_type == "goods_receipt":
                receipts_by_po.setdefault(str(record.fields.get("po_id", "")), []).append(record)
            elif record.record_type == "supplier_invoice":
                invoices_by_po.setdefault(str(record.fields.get("po_id", "")), []).append(record)

        for po in (record for record in world.records if record.record_type == "purchase_order"):
            po_id = po.object_id
            line_count = 1
            if item_distribution is not None:
                line_count = max(1, min(40, int(round(item_distribution.sample(rng)))))
            sourcing_parties = 2
            if party_distribution is not None:
                sourcing_parties = max(2, min(20, int(round(party_distribution.sample(rng)))))

            amount = float(po.fields.get("amount", 0.0))
            currency = str(po.fields.get("currency", "USD"))
            weights = [0.25 + rng.random() for _ in range(line_count)]
            weight_sum = sum(weights)
            remaining = round(amount, 2)
            line_items: list[dict[str, object]] = []
            for line_index, weight in enumerate(weights, start=1):
                if line_index == line_count:
                    line_amount = remaining
                else:
                    line_amount = round(amount * weight / weight_sum, 2)
                    remaining = round(remaining - line_amount, 2)
                line_items.append(
                    {
                        "line_id": f"{po_id}-L{line_index:03d}",
                        "sku": f"SKU-{(world.spec.seed * 97 + line_index * 7919 + rng.randrange(1000)) % 100000:05d}",
                        "quantity": 1 + rng.randrange(25),
                        "amount": line_amount,
                        "currency": currency,
                    }
                )

            po.fields["line_item_count"] = line_count
            po.fields["line_items"] = line_items
            po.fields["sourcing_party_count"] = sourcing_parties
            po.fields["calibration_metrics"] = [
                metric
                for metric, present in (
                    ("procurement.items_per_tender", item_distribution is not None),
                    ("procurement.parties_per_process", party_distribution is not None),
                )
                if present
            ]
            for event_id in po.source_event_ids:
                event = event_by_id.get(event_id)
                if event is not None:
                    event.payload.update(
                        {
                            "line_item_count": line_count,
                            "line_items": line_items,
                            "sourcing_party_count": sourcing_parties,
                        }
                    )

            for receipt in receipts_by_po.get(po_id, []):
                receipt.fields["line_item_count"] = line_count
                receipt.fields["received_lines"] = [
                    {
                        "line_id": item["line_id"],
                        "sku": item["sku"],
                        "received_quantity": item["quantity"],
                    }
                    for item in line_items
                ]
                for event_id in receipt.source_event_ids:
                    event = event_by_id.get(event_id)
                    if event is not None:
                        event.payload["line_item_count"] = line_count
                        event.payload["received_lines"] = receipt.fields["received_lines"]

            for invoice in invoices_by_po.get(po_id, []):
                invoice.fields["line_item_count"] = line_count
                invoice.fields["line_items"] = line_items
                for event_id in invoice.source_event_ids:
                    event = event_by_id.get(event_id)
                    if event is not None:
                        event.payload["line_item_count"] = line_count
                        event.payload["line_items"] = line_items

    @staticmethod
    def _apply_calibrated_financial_snapshot(world: CompiledOperationalWorld) -> None:
        """Add a coherent balance-sheet snapshot when calibrated finance evidence exists.

        SEC-derived ratios are not used to overwrite transactional ledger truth. They provide a
        synthetic opening/enterprise-scale context record, while the procure-to-pay ledger remains
        generated from canonical operational events. This keeps calibration and episode truth
        causally separate and avoids forcing public-company scale onto profiles that do not carry it.
        """

        distributions = world.calibration.distributions
        asset_distribution = distributions.get("finance.assets_usd")
        liability_ratio_distribution = distributions.get("finance.liabilities_to_assets")
        payable_ratio_distribution = distributions.get("finance.accounts_payable_to_assets")
        revenue_ratio_distribution = distributions.get("finance.revenue_to_assets")
        if asset_distribution is None:
            return

        rng = Random(world.spec.seed ^ 0xF1A4C3)
        assets_usd = max(1.0, asset_distribution.sample(rng))
        liabilities_ratio = (
            max(0.0, liability_ratio_distribution.sample(rng))
            if liability_ratio_distribution is not None
            else 0.5
        )
        liabilities_usd = min(assets_usd * 5.0, assets_usd * liabilities_ratio)
        equity_usd = assets_usd - liabilities_usd
        payable_usd = None
        if payable_ratio_distribution is not None:
            payable_usd = max(0.0, min(liabilities_usd, assets_usd * payable_ratio_distribution.sample(rng)))
        revenue_usd = None
        if revenue_ratio_distribution is not None:
            revenue_usd = max(0.0, assets_usd * revenue_ratio_distribution.sample(rng))

        from datetime import datetime, timezone
        from investigation_world.operational_world.models import OperationalEvent, OperationalRecord

        timestamp = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc)
        event_id = f"OEVENT-{len(world.events) + 1:08d}"
        payload = {
            "assets_usd": round(assets_usd, 2),
            "liabilities_usd": round(liabilities_usd, 2),
            "equity_usd": round(equity_usd, 2),
            "accounts_payable_usd": round(payable_usd, 2) if payable_usd is not None else None,
            "annual_revenue_usd": round(revenue_usd, 2) if revenue_usd is not None else None,
            "source_metrics": [
                metric
                for metric in (
                    "finance.assets_usd",
                    "finance.liabilities_to_assets",
                    "finance.accounts_payable_to_assets",
                    "finance.revenue_to_assets",
                )
                if metric in distributions
            ],
        }
        world.events.append(
            OperationalEvent(
                event_id=event_id,
                event_type="FinancialSnapshotEstablished",
                timestamp=timestamp,
                actor_id=None,
                object_ids=["ORG-000001"],
                payload=payload,
            )
        )
        world.records.append(
            OperationalRecord(
                record_id=f"OWREC-{len(world.records) + 1:09d}",
                system="LEDGER",
                record_type="financial_snapshot",
                object_type="ORGANIZATION",
                object_id="ORG-000001",
                observed_at=timestamp,
                fields=payload,
                related_object_ids=[],
                source_event_ids=[event_id],
            )
        )
        world.metadata["financial_snapshot_calibrated"] = True

    @staticmethod
    def _repair_unintended_authority_gaps(world: CompiledOperationalWorld) -> None:
        intentional_targets = {
            fact.object_id
            for finding in world.ground_truth
            if finding.scenario_type == ScenarioKind.APPROVAL_BYPASS
            for fact in finding.facts
        }
        approvals = [record for record in world.records if record.record_type == "approval"]
        violations = [
            record
            for record in approvals
            if record.object_id not in intentional_targets
            and float(record.fields.get("amount", 0.0))
            > float(record.fields.get("approval_limit", 0.0))
        ]
        if not violations:
            return

        currency = str(world.spec.metadata.get("currency_code", "USD"))
        max_amount = max(float(record.fields.get("amount", 0.0)) for record in violations)
        executive_id = "EMP-EXEC-000001"
        world.entities[executive_id] = OperationalEntity(
            entity_id=executive_id,
            entity_type="employee",
            name="Morgan Executive",
            attributes={
                "department": "finance",
                "role": "chief_financial_officer",
                "approval_limit": round(max_amount * 1.25 + 1.0, 2),
                "currency": currency,
                "synthetic_escalation_authority": True,
            },
        )
        executive_limit = world.entities[executive_id].attributes["approval_limit"]

        event_by_id = {event.event_id: event for event in world.events}
        po_by_request = {
            str(record.fields.get("request_id")): record
            for record in world.records
            if record.record_type == "purchase_order"
        }
        for approval in violations:
            approval.fields["approval_limit"] = executive_limit
            approval.fields["escalated"] = True
            approval.related_object_ids = [
                value for value in approval.related_object_ids if not value.startswith("EMP-")
            ] + [executive_id]
            for event_id in approval.source_event_ids:
                event = event_by_id.get(event_id)
                if event is not None:
                    event.actor_id = executive_id
                    event.payload["approval_limit"] = executive_limit
                    event.payload["escalated"] = True
            po = po_by_request.get(approval.object_id)
            if po is not None:
                po.fields["approver_id"] = executive_id
