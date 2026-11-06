from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import Random
from typing import Any

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.operational_world.fusion import build_bootstrap_calibration
from investigation_world.operational_world.models import (
    CalibrationProfile,
    CompiledOperationalWorld,
    GroundTruthFact,
    GroundTruthFinding,
    OperationalEntity,
    OperationalEvent,
    OperationalRecord,
    OperationalWorldSpec,
    ScenarioKind,
)


_SYSTEM_BY_EVENT = {
    "PurchaseRequestCreated": "ERP",
    "PurchaseRequestApproved": "AUTH_SERVICE",
    "PurchaseOrderIssued": "ERP",
    "GoodsReceiptRecorded": "WMS",
    "SupplierInvoiceReceived": "AP_WORKFLOW",
    "SupplierInvoiceApproved": "AP_WORKFLOW",
    "PaymentExecuted": "TREASURY",
    "LedgerPosted": "LEDGER",
    "ProcurementEmail": "EMAIL",
    "InventoryCount": "WMS",
    "VendorMasterObserved": "ERP",
    "EmployeeDisclosureObserved": "COMPLIANCE",
}


class OperationalWorldCompiler:
    """Compile a seeded operational specification into a hidden-truth world.

    The canonical event graph is authoritative. Public records are deterministic projections
    from that graph; scenarios are explicit causal interventions with separate hidden truth.
    """

    def __init__(self, calibration: CalibrationProfile | None = None) -> None:
        self._calibration = calibration

    def compile(self, spec: OperationalWorldSpec) -> CompiledOperationalWorld:
        rng = Random(spec.seed)
        calibration = self._calibration or build_bootstrap_calibration(
            region=spec.region,
            industry=spec.industry,
            size_band=spec.size_band,
        )
        world = CompiledOperationalWorld(
            world_id=f"OWORLD-{spec.seed:08d}",
            spec=spec,
            calibration=calibration,
            metadata={
                "compiler_version": "operational-world-v1",
                "truth_first": True,
                "calibration_state": calibration.state,
                "calibration_source_ids": calibration.source_ids,
            },
        )

        employee_count = spec.employee_count or max(
            5, int(round(calibration.sample("firm.employee_count", rng)))
        )
        self._build_organization(world, rng, employee_count)
        self._build_procure_to_pay(world, rng, employee_count)
        for scenario_index, scenario_type in enumerate(spec.scenario_types, start=1):
            self._apply_scenario(world, rng, scenario_type, scenario_index)
        return world

    def compile_investigation_episode(
        self,
        spec: OperationalWorldSpec,
        *,
        budget: float = 80.0,
    ) -> tuple[CompiledOperationalWorld, CompanyWorldEpisode]:
        if not spec.scenario_types:
            raise ValueError("an investigation episode requires at least one scenario type")
        world = self.compile(spec)
        finding = world.ground_truth[0]
        target_fact = finding.facts[0]
        task_id = f"OWTASK-{spec.seed:08d}-001"
        records = [self._to_companyworld_record(item) for item in world.records]
        task = CompanyWorldTask(
            task_id=task_id,
            world_id=world.world_id,
            task_type="operational_procurement_investigation",
            objective=(
                "Investigate the supplied procurement and finance records for material "
                "transaction, authorization, receipt, vendor, or reconciliation irregularities. "
                "Return only evidence-backed findings and distinguish uncertainty from fact."
            ),
            target_object_type=target_fact.object_type,
            target_object_id=target_fact.object_id,
            permitted_systems=sorted({record.system for record in records}, key=str),
            constraints={"budget": budget, "false_positive_sensitive": True},
            metadata={
                "compiler": "operational-world-v1",
                "calibration_state": world.calibration.state,
            },
        )
        oracle = CompanyWorldOracle(
            task_id=task_id,
            answer_class="operational_irregularity",
            expected_resolution=finding.summary,
            facts=[
                OperationalFactTarget(
                    object_type=fact.object_type,
                    object_id=fact.object_id,
                    field_name=fact.field_name,
                    expected_value=fact.expected_value,
                    supporting_record_ids=fact.supporting_record_ids,
                )
                for fact in finding.facts
            ],
            hidden_error_id=finding.finding_id,
            hidden_cause=finding.scenario_type,
        )
        episode = CompanyWorldEpisode(
            episode_id=f"OWEP-{spec.seed:08d}-001",
            world_id=world.world_id,
            task=task,
            records=records,
            oracle=oracle,
            metadata={
                "source": "operational_world_compiler",
                "scenario_count": len(world.ground_truth),
            },
        )
        return world, episode

    def _build_organization(
        self,
        world: CompiledOperationalWorld,
        rng: Random,
        employee_count: int,
    ) -> None:
        spec = world.spec
        company_name = f"Atlas {spec.industry.value.replace('_', ' ').title()} {spec.seed % 997:03d}"
        world.entities["ORG-000001"] = OperationalEntity(
            entity_id="ORG-000001",
            entity_type="organization",
            name=company_name,
            attributes={
                "country_code": spec.country_code,
                "region": spec.region,
                "industry": spec.industry,
                "employee_count": employee_count,
            },
        )

        mix = world.calibration.categories["organization.department_mix"].weights
        departments = list(mix)
        remaining = employee_count
        department_counts: dict[str, int] = {}
        for index, department in enumerate(departments):
            if index == len(departments) - 1:
                count = remaining
            else:
                count = max(1, int(round(employee_count * mix[department])))
                count = min(count, remaining - max(0, len(departments) - index - 1))
            department_counts[department] = count
            remaining -= count
            department_id = f"DEPT-{index + 1:03d}"
            world.entities[department_id] = OperationalEntity(
                entity_id=department_id,
                entity_type="department",
                name=department.replace("_", " ").title(),
                attributes={"headcount": count},
            )

        first_names = (
            "Ada",
            "Amina",
            "Chidi",
            "Daniel",
            "Elena",
            "Fatima",
            "Grace",
            "Hiro",
            "Ife",
            "Javier",
            "Kofi",
            "Lina",
            "Maya",
            "Nadia",
            "Omar",
            "Priya",
            "Ravi",
            "Sara",
            "Tariq",
            "Wei",
        )
        last_names = (
            "Adeyemi",
            "Bello",
            "Chen",
            "Costa",
            "Diallo",
            "Garcia",
            "Hassan",
            "Ibrahim",
            "Kim",
            "Mensah",
            "Nwosu",
            "Okafor",
            "Patel",
            "Rahman",
            "Santos",
            "Singh",
            "Tanaka",
            "Williams",
        )
        department_queue: list[str] = []
        for department, count in department_counts.items():
            department_queue.extend([department] * count)
        rng.shuffle(department_queue)

        base_limit_usd = world.calibration.distributions["controls.approval_limit_usd"].p50
        fx = float(spec.metadata.get("usd_to_local", 1.0))
        currency = str(spec.metadata.get("currency_code", "USD"))
        for index in range(1, employee_count + 1):
            department = department_queue[index - 1]
            role = "manager" if index % 11 == 0 else "analyst"
            if department in {"procurement", "finance"} and index % 7 == 0:
                role = "manager"
            limit = 0.0
            if role == "manager":
                limit = base_limit_usd * fx * (1.0 + (index % 5))
            employee_id = f"EMP-{index:06d}"
            world.entities[employee_id] = OperationalEntity(
                entity_id=employee_id,
                entity_type="employee",
                name=f"{first_names[(index - 1) % len(first_names)]} {last_names[(index * 7) % len(last_names)]}",
                attributes={
                    "department": department,
                    "role": role,
                    "approval_limit": round(limit, 2),
                    "currency": currency,
                },
            )

        vendor_count = max(
            6,
            int(
                round(
                    world.calibration.sample("procurement.vendors_per_100_employees", rng)
                    * employee_count
                    / 100
                )
            ),
        )
        vendor_prefixes = (
            "Aster",
            "Beacon",
            "Cobalt",
            "Delta",
            "Evergreen",
            "Frontier",
            "Harbor",
            "Indigo",
            "Juniper",
            "Kestrel",
            "Lattice",
            "Meridian",
            "Nimbus",
            "Orchid",
            "Pioneer",
        )
        vendor_suffixes = (
            "Industrial",
            "Supply",
            "Logistics",
            "Services",
            "Trading",
            "Technologies",
            "Works",
        )
        for index in range(1, vendor_count + 1):
            vendor_id = f"VEN-{index:06d}"
            world.entities[vendor_id] = OperationalEntity(
                entity_id=vendor_id,
                entity_type="vendor",
                name=(
                    f"{vendor_prefixes[(index - 1) % len(vendor_prefixes)]} "
                    f"{vendor_suffixes[(index * 3) % len(vendor_suffixes)]} {index:03d}"
                ),
                attributes={
                    "country_code": spec.country_code,
                    "active": True,
                    "risk_tier": ("low", "medium", "high")[index % 3],
                    "bank_fingerprint": f"BANK-{(index * 7919) % 100_000:05d}",
                },
            )

    def _build_procure_to_pay(
        self,
        world: CompiledOperationalWorld,
        rng: Random,
        employee_count: int,
    ) -> None:
        spec = world.spec
        start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
        if "simulation_start" in spec.metadata:
            start = datetime.fromisoformat(str(spec.metadata["simulation_start"]))
            if start.tzinfo is None:
                start = start.replace(tzinfo=timezone.utc)

        annual_rate = world.calibration.sample(
            "procurement.purchase_orders_per_employee_year", rng
        )
        expected = annual_rate * employee_count * spec.simulation_days / 365.0
        process_count = max(12, min(5000, int(round(expected))))
        fx = float(spec.metadata.get("usd_to_local", 1.0))
        currency = str(spec.metadata.get("currency_code", "USD"))

        employees = [
            entity for entity in world.entities.values() if entity.entity_type == "employee"
        ]
        requesters = [
            entity
            for entity in employees
            if entity.attributes.get("department") in {"operations", "procurement", "warehouse", "technology"}
        ] or employees
        approvers = [
            entity
            for entity in employees
            if float(entity.attributes.get("approval_limit", 0.0)) > 0
        ]
        vendors = [entity for entity in world.entities.values() if entity.entity_type == "vendor"]

        for index in range(1, process_count + 1):
            requester = rng.choice(requesters)
            vendor = rng.choice(vendors)
            normalized_amount = max(
                1.0, world.calibration.sample("procurement.po_amount_usd", rng)
            )
            amount = round(normalized_amount * fx, 2)
            eligible = [
                item
                for item in approvers
                if float(item.attributes.get("approval_limit", 0.0)) >= amount
            ]
            approver = rng.choice(eligible or approvers or [requester])
            day = rng.randrange(spec.simulation_days)
            minute = rng.randrange(8 * 60)
            request_time = start + timedelta(days=day, minutes=minute)
            approval_time = request_time + timedelta(minutes=10 + rng.randrange(24 * 60))
            po_time = approval_time + timedelta(minutes=5 + rng.randrange(180))
            receipt_time = po_time + timedelta(
                days=max(0.1, world.calibration.sample("procurement.receipt_lag_days", rng))
            )
            invoice_time = receipt_time + timedelta(
                days=max(0.0, world.calibration.sample("finance.invoice_lag_days", rng))
            )
            payment_time = invoice_time + timedelta(
                days=max(0.1, world.calibration.sample("finance.payment_lag_days", rng))
            )

            pr_id = f"PR-{index:07d}"
            po_id = f"PO-{index:07d}"
            receipt_id = f"GR-{index:07d}"
            invoice_id = f"INV-{index:07d}"
            payment_id = f"PAY-{index:07d}"
            quantity = 1 + rng.randrange(40)

            pr_event = self._event(
                world,
                "PurchaseRequestCreated",
                request_time,
                actor_id=requester.entity_id,
                object_ids=[pr_id, vendor.entity_id],
                payload={
                    "request_id": pr_id,
                    "vendor_id": vendor.entity_id,
                    "amount": amount,
                    "normalized_usd": round(normalized_amount, 2),
                    "currency": currency,
                    "quantity": quantity,
                },
            )
            approval_event = self._event(
                world,
                "PurchaseRequestApproved",
                approval_time,
                actor_id=approver.entity_id,
                object_ids=[pr_id],
                payload={
                    "request_id": pr_id,
                    "approved": True,
                    "approval_limit": approver.attributes.get("approval_limit", 0.0),
                    "amount": amount,
                    "currency": currency,
                },
                caused_by=[pr_event.event_id],
            )
            po_event = self._event(
                world,
                "PurchaseOrderIssued",
                po_time,
                actor_id=requester.entity_id,
                object_ids=[po_id, pr_id, vendor.entity_id],
                payload={
                    "po_id": po_id,
                    "request_id": pr_id,
                    "vendor_id": vendor.entity_id,
                    "amount": amount,
                    "normalized_usd": round(normalized_amount, 2),
                    "currency": currency,
                    "quantity": quantity,
                    "approver_id": approver.entity_id,
                },
                caused_by=[approval_event.event_id],
            )
            receipt_event = self._event(
                world,
                "GoodsReceiptRecorded",
                receipt_time,
                actor_id=rng.choice(requesters).entity_id,
                object_ids=[receipt_id, po_id],
                payload={
                    "receipt_id": receipt_id,
                    "po_id": po_id,
                    "received_quantity": quantity,
                    "condition": "accepted",
                },
                caused_by=[po_event.event_id],
            )
            invoice_event = self._event(
                world,
                "SupplierInvoiceReceived",
                invoice_time,
                actor_id=None,
                object_ids=[invoice_id, po_id, vendor.entity_id],
                payload={
                    "invoice_id": invoice_id,
                    "po_id": po_id,
                    "vendor_id": vendor.entity_id,
                    "amount": amount,
                    "currency": currency,
                    "quantity": quantity,
                    "duplicate_status": "unique",
                },
                caused_by=[receipt_event.event_id],
            )
            payment_event = self._event(
                world,
                "PaymentExecuted",
                payment_time,
                actor_id=None,
                object_ids=[payment_id, invoice_id, vendor.entity_id],
                payload={
                    "payment_id": payment_id,
                    "invoice_id": invoice_id,
                    "vendor_id": vendor.entity_id,
                    "amount": amount,
                    "currency": currency,
                    "status": "settled",
                },
                caused_by=[invoice_event.event_id],
            )
            self._event(
                world,
                "LedgerPosted",
                payment_time + timedelta(minutes=5),
                actor_id=None,
                object_ids=[f"JE-{index:07d}", payment_id],
                payload={
                    "journal_id": f"JE-{index:07d}",
                    "payment_id": payment_id,
                    "debit": amount,
                    "credit": amount,
                    "currency": currency,
                    "balanced": True,
                },
                caused_by=[payment_event.event_id],
            )
            if index % 4 == 0:
                self._event(
                    world,
                    "ProcurementEmail",
                    po_time + timedelta(minutes=30),
                    actor_id=requester.entity_id,
                    object_ids=[po_id, vendor.entity_id],
                    payload={
                        "subject": f"Purchase order {po_id}",
                        "sender_id": requester.entity_id,
                        "vendor_id": vendor.entity_id,
                        "body": (
                            f"Please confirm receipt of {po_id}. The approved order value is "
                            f"{amount:.2f} {currency}."
                        ),
                    },
                    caused_by=[po_event.event_id],
                )

    def _event(
        self,
        world: CompiledOperationalWorld,
        event_type: str,
        timestamp: datetime,
        *,
        actor_id: str | None,
        object_ids: list[str],
        payload: dict[str, Any],
        caused_by: list[str] | None = None,
    ) -> OperationalEvent:
        event = OperationalEvent(
            event_id=f"OEVENT-{len(world.events) + 1:09d}",
            event_type=event_type,
            timestamp=timestamp,
            actor_id=actor_id,
            object_ids=object_ids,
            payload=payload,
            caused_by=caused_by or [],
        )
        world.events.append(event)
        system = _SYSTEM_BY_EVENT.get(event_type, "PROCESS")
        primary = object_ids[0] if object_ids else event.event_id
        object_type = self._object_type(primary)
        record = OperationalRecord(
            record_id=f"OWR-{len(world.records) + 1:09d}",
            system=system,
            record_type=self._record_type(event_type),
            object_type=object_type,
            object_id=primary,
            observed_at=timestamp,
            fields=dict(payload),
            related_object_ids=list(dict.fromkeys(object_ids[1:] + ([actor_id] if actor_id else []))),
            source_event_ids=[event.event_id],
        )
        world.records.append(record)
        return event

    def _apply_scenario(
        self,
        world: CompiledOperationalWorld,
        rng: Random,
        scenario: ScenarioKind,
        scenario_index: int,
    ) -> None:
        if scenario == ScenarioKind.DUPLICATE_INVOICE:
            self._inject_duplicate_invoice(world, rng, scenario_index)
        elif scenario == ScenarioKind.APPROVAL_BYPASS:
            self._inject_approval_bypass(world, rng, scenario_index)
        elif scenario == ScenarioKind.SHELL_VENDOR_CONFLICT:
            self._inject_shell_vendor_conflict(world, rng, scenario_index)
        elif scenario == ScenarioKind.PHANTOM_RECEIPT:
            self._inject_phantom_receipt(world, rng, scenario_index)
        elif scenario == ScenarioKind.SPLIT_PURCHASE_ORDERS:
            self._inject_split_purchase_orders(world, rng, scenario_index)
        else:  # pragma: no cover - exhaustive enum guard
            raise ValueError(f"unsupported scenario: {scenario}")

    def _inject_duplicate_invoice(
        self, world: CompiledOperationalWorld, rng: Random, scenario_index: int
    ) -> None:
        invoices = [r for r in world.records if r.record_type == "supplier_invoice"]
        original = rng.choice(invoices)
        duplicate_id = f"INV-DUP-{scenario_index:03d}-{rng.randrange(10_000):04d}"
        timestamp = original.observed_at + timedelta(hours=2 + rng.randrange(72))
        event = self._event(
            world,
            "SupplierInvoiceReceived",
            timestamp,
            actor_id=None,
            object_ids=[duplicate_id, str(original.fields["po_id"]), str(original.fields["vendor_id"])],
            payload={
                **original.fields,
                "invoice_id": duplicate_id,
                "duplicate_status": "suspected_duplicate",
            },
            caused_by=list(original.source_event_ids),
        )
        duplicate_record = world.records[-1]
        original.fields["duplicate_status"] = "possible_original"
        finding = GroundTruthFinding(
            finding_id=f"FIND-{scenario_index:04d}",
            scenario_type=ScenarioKind.DUPLICATE_INVOICE,
            summary=f"{duplicate_id} duplicates {original.object_id} for the same PO and vendor.",
            affected_object_ids=[original.object_id, duplicate_id],
            causal_event_ids=event.caused_by + [event.event_id],
            facts=[
                GroundTruthFact(
                    object_type="SUPPLIER_INVOICE",
                    object_id=duplicate_id,
                    field_name="duplicate_of",
                    expected_value=original.object_id,
                    supporting_record_ids=[original.record_id, duplicate_record.record_id],
                )
            ],
        )
        world.ground_truth.append(finding)

    def _inject_approval_bypass(
        self, world: CompiledOperationalWorld, rng: Random, scenario_index: int
    ) -> None:
        approvals = [r for r in world.records if r.record_type == "approval"]
        target = rng.choice(approvals)
        amount = float(target.fields.get("amount", 0.0))
        low_limit_employees = [
            entity
            for entity in world.entities.values()
            if entity.entity_type == "employee"
            and float(entity.attributes.get("approval_limit", 0.0)) < amount
        ]
        actor = rng.choice(low_limit_employees) if low_limit_employees else None
        if actor is not None:
            target.related_object_ids = [
                item for item in target.related_object_ids if not item.startswith("EMP-")
            ] + [actor.entity_id]
            target.fields["approval_limit"] = actor.attributes.get("approval_limit", 0.0)
            for event in world.events:
                if target.source_event_ids and event.event_id == target.source_event_ids[0]:
                    event.actor_id = actor.entity_id
                    event.payload["approval_limit"] = actor.attributes.get("approval_limit", 0.0)
                    break
        target.fields["authority_check"] = "not_satisfied"
        finding = GroundTruthFinding(
            finding_id=f"FIND-{scenario_index:04d}",
            scenario_type=ScenarioKind.APPROVAL_BYPASS,
            summary=f"Approval for {target.object_id} exceeded the recorded approver authority.",
            affected_object_ids=[target.object_id],
            causal_event_ids=list(target.source_event_ids),
            facts=[
                GroundTruthFact(
                    object_type="PURCHASE_REQUEST",
                    object_id=target.object_id,
                    field_name="authorized",
                    expected_value=False,
                    supporting_record_ids=[target.record_id],
                )
            ],
        )
        world.ground_truth.append(finding)

    def _inject_shell_vendor_conflict(
        self, world: CompiledOperationalWorld, rng: Random, scenario_index: int
    ) -> None:
        vendors = [e for e in world.entities.values() if e.entity_type == "vendor"]
        employees = [e for e in world.entities.values() if e.entity_type == "employee"]
        vendor = rng.choice(vendors)
        employee = rng.choice(employees)
        fingerprint = str(vendor.attributes["bank_fingerprint"])
        vendor_event = self._event(
            world,
            "VendorMasterObserved",
            datetime(2025, 1, 15, 10, 0, tzinfo=timezone.utc) + timedelta(days=scenario_index),
            actor_id=None,
            object_ids=[vendor.entity_id],
            payload={
                "vendor_id": vendor.entity_id,
                "bank_fingerprint": fingerprint,
                "onboarding_status": "approved",
            },
        )
        disclosure_event = self._event(
            world,
            "EmployeeDisclosureObserved",
            vendor_event.timestamp + timedelta(hours=1),
            actor_id=employee.entity_id,
            object_ids=[employee.entity_id],
            payload={
                "employee_id": employee.entity_id,
                "declared_related_bank_fingerprint": fingerprint,
                "declared_vendor_relationship": "none",
            },
        )
        finding = GroundTruthFinding(
            finding_id=f"FIND-{scenario_index:04d}",
            scenario_type=ScenarioKind.SHELL_VENDOR_CONFLICT,
            summary=(
                f"Vendor {vendor.entity_id} shares a financial-control fingerprint with "
                f"employee {employee.entity_id} despite no declared vendor relationship."
            ),
            affected_object_ids=[vendor.entity_id, employee.entity_id],
            causal_event_ids=[vendor_event.event_id, disclosure_event.event_id],
            facts=[
                GroundTruthFact(
                    object_type="VENDOR",
                    object_id=vendor.entity_id,
                    field_name="conflict_of_interest",
                    expected_value=True,
                    supporting_record_ids=[world.records[-2].record_id, world.records[-1].record_id],
                )
            ],
        )
        world.ground_truth.append(finding)

    def _inject_phantom_receipt(
        self, world: CompiledOperationalWorld, rng: Random, scenario_index: int
    ) -> None:
        receipts = [r for r in world.records if r.record_type == "goods_receipt"]
        receipt = rng.choice(receipts)
        quantity = int(receipt.fields.get("received_quantity", 1))
        count_event = self._event(
            world,
            "InventoryCount",
            receipt.observed_at + timedelta(days=1),
            actor_id=None,
            object_ids=[receipt.object_id],
            payload={
                "receipt_id": receipt.object_id,
                "expected_quantity": quantity,
                "physical_quantity_found": 0,
                "count_status": "material_variance",
            },
            caused_by=list(receipt.source_event_ids),
        )
        finding = GroundTruthFinding(
            finding_id=f"FIND-{scenario_index:04d}",
            scenario_type=ScenarioKind.PHANTOM_RECEIPT,
            summary=f"{receipt.object_id} records goods that were absent in the subsequent physical count.",
            affected_object_ids=[receipt.object_id],
            causal_event_ids=list(receipt.source_event_ids) + [count_event.event_id],
            facts=[
                GroundTruthFact(
                    object_type="GOODS_RECEIPT",
                    object_id=receipt.object_id,
                    field_name="physical_receipt_confirmed",
                    expected_value=False,
                    supporting_record_ids=[receipt.record_id, world.records[-1].record_id],
                )
            ],
        )
        world.ground_truth.append(finding)

    def _inject_split_purchase_orders(
        self, world: CompiledOperationalWorld, rng: Random, scenario_index: int
    ) -> None:
        pos = [r for r in world.records if r.record_type == "purchase_order"]
        base = rng.choice(pos)
        threshold = max(100.0, float(base.fields.get("amount", 1000.0)) * 0.8)
        part_amount = round(threshold * 0.92, 2)
        sibling_id = f"PO-SPLIT-{scenario_index:03d}-{rng.randrange(10_000):04d}"
        sibling_event = self._event(
            world,
            "PurchaseOrderIssued",
            base.observed_at + timedelta(minutes=25),
            actor_id=next(
                (item for item in base.related_object_ids if item.startswith("EMP-")), None
            ),
            object_ids=[sibling_id, str(base.fields.get("request_id")), str(base.fields.get("vendor_id"))],
            payload={
                **base.fields,
                "po_id": sibling_id,
                "amount": part_amount,
                "structuring_group": f"STRUCT-{scenario_index:03d}",
            },
            caused_by=list(base.source_event_ids),
        )
        sibling = world.records[-1]
        base.fields["amount"] = part_amount
        base.fields["structuring_group"] = f"STRUCT-{scenario_index:03d}"
        finding = GroundTruthFinding(
            finding_id=f"FIND-{scenario_index:04d}",
            scenario_type=ScenarioKind.SPLIT_PURCHASE_ORDERS,
            summary=(
                f"{base.object_id} and {sibling_id} were structured as linked orders below a review threshold."
            ),
            affected_object_ids=[base.object_id, sibling_id],
            causal_event_ids=list(base.source_event_ids) + [sibling_event.event_id],
            facts=[
                GroundTruthFact(
                    object_type="PURCHASE_ORDER",
                    object_id=sibling_id,
                    field_name="structured_split",
                    expected_value=True,
                    supporting_record_ids=[base.record_id, sibling.record_id],
                )
            ],
        )
        world.ground_truth.append(finding)

    @staticmethod
    def _record_type(event_type: str) -> str:
        return {
            "PurchaseRequestCreated": "purchase_request",
            "PurchaseRequestApproved": "approval",
            "PurchaseOrderIssued": "purchase_order",
            "GoodsReceiptRecorded": "goods_receipt",
            "SupplierInvoiceReceived": "supplier_invoice",
            "SupplierInvoiceApproved": "invoice_approval",
            "PaymentExecuted": "payment",
            "LedgerPosted": "ledger_entry",
            "ProcurementEmail": "email",
            "InventoryCount": "inventory_count",
            "VendorMasterObserved": "vendor_master",
            "EmployeeDisclosureObserved": "employee_disclosure",
        }.get(event_type, event_type.lower())

    @staticmethod
    def _object_type(object_id: str) -> str:
        prefix = object_id.split("-", 1)[0]
        return {
            "PR": "PURCHASE_REQUEST",
            "PO": "PURCHASE_ORDER",
            "GR": "GOODS_RECEIPT",
            "INV": "SUPPLIER_INVOICE",
            "PAY": "PAYMENT",
            "JE": "JOURNAL_ENTRY",
            "VEN": "VENDOR",
            "EMP": "EMPLOYEE",
        }.get(prefix, "OPERATIONAL_OBJECT")

    @staticmethod
    def _to_companyworld_record(record: OperationalRecord) -> CompanyWorldRecord:
        return CompanyWorldRecord(
            record_id=record.record_id,
            system=CompanySystem(record.system),
            record_type=record.record_type,
            object_type=record.object_type,
            object_id=record.object_id,
            fields=record.fields,
            source_file="operational_world_compiler",
            observed_at=record.observed_at,
            related_object_ids=record.related_object_ids,
        )
