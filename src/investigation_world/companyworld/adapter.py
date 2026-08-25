from __future__ import annotations

import csv
import gzip
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    CompanyWorldValidationReport,
    OperationalFactTarget,
)


REQUIRED_FILES = (
    "canonical/company.csv.gz",
    "canonical/shipments.csv.gz",
    "canonical/supplier_invoices.csv.gz",
    "canonical/authority_rules.csv.gz",
    "canonical/messages.csv.gz",
    "ground_truth/hidden_errors.csv.gz",
    "ground_truth/task_answers.csv.gz",
    "ground_truth/projection_divergence.csv.gz",
    "validation/validation_report.json",
)

_PRIVATE_FIELD_NAMES = {
    "true_value",
    "cause",
    "supporting_evidence",
    "truth_status",
    "observability",
    "hidden_error_id",
    "answer_class",
    "expected_resolution",
}


def _coerce(value: str | None) -> Any:
    if value is None or value == "":
        return None
    lowered = value.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _clean_fields(row: dict[str, str]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in row.items():
        if key in _PRIVATE_FIELD_NAMES or value in (None, ""):
            continue
        public_key = "status" if key == "true_status" else key
        cleaned[public_key] = _coerce(value)
    return cleaned


def _stable_record_id(system: CompanySystem, source_file: str, object_id: str, suffix: str = "") -> str:
    raw = f"{system.value}|{source_file}|{object_id}|{suffix}".encode()
    return f"CWR-{hashlib.sha256(raw).hexdigest()[:20].upper()}"


def _public_objective(task_type: str, object_type: str, object_id: str) -> str:
    if task_type == "INVESTIGATE_MISSING_SHIPMENT":
        return (
            f"Investigate the reported shipment discrepancy for {object_id}. Reconcile ERP, "
            "warehouse/carrier, and communication records; determine the delivered quantity "
            "supported by evidence and identify any unresolved uncertainty."
        )
    if task_type == "INVESTIGATE_DUPLICATE_INVOICE":
        return (
            f"Investigate supplier invoice {object_id} for duplication or matching anomalies. "
            "Reconcile supplier submission, purchase-order, receiving, and accounting records "
            "and determine the invoice's correct operational status."
        )
    if task_type == "INVESTIGATE_AUTHORITY_BREACH":
        return (
            f"Investigate the effective approval authority for position {object_id}. Reconcile "
            "policy, system configuration, and approval history and determine the correct limit."
        )
    return f"Investigate the operational state of {object_type} {object_id} using available systems."


class CompanyWorldAdapter:
    """Load CompanyWorld v0.x and compile hidden anomalies into operational episodes.

    The adapter keeps evaluator-only files private. Ground-truth rows may influence the
    generation of observable records, but private annotations are never copied into public
    episode payloads.
    """

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self._rows_cache: dict[str, list[dict[str, str]]] = {}
        self._index_cache: dict[tuple[str, str], dict[str, dict[str, str]]] = {}
        self._group_cache: dict[tuple[str, str], dict[str, list[dict[str, str]]]] = {}
        self._company = self._first("canonical/company.csv.gz") if self._exists("canonical/company.csv.gz") else {}
        company_id = self._company.get("company_id", "unknown")
        seed = self._company.get("world_seed", "unknown")
        self.world_id = f"companyworld:{company_id}:{seed}"

    def _exists(self, relative: str) -> bool:
        return (self.root / relative).is_file()

    def _iter_csv(self, relative: str) -> Iterable[dict[str, str]]:
        path = self.root / relative
        if not path.is_file():
            return iter(())
        if path.suffix == ".gz":
            handle = gzip.open(path, "rt", newline="", encoding="utf-8")
        else:
            handle = path.open("r", newline="", encoding="utf-8")

        def rows():
            with handle:
                yield from csv.DictReader(handle)

        return rows()

    def _rows(self, relative: str) -> list[dict[str, str]]:
        if relative not in self._rows_cache:
            self._rows_cache[relative] = list(self._iter_csv(relative))
        return self._rows_cache[relative]

    def _first(self, relative: str) -> dict[str, str]:
        return next(iter(self._iter_csv(relative)), {})

    def _index(self, relative: str, key: str) -> dict[str, dict[str, str]]:
        cache_key = (relative, key)
        if cache_key not in self._index_cache:
            self._index_cache[cache_key] = {
                row[key]: row for row in self._iter_csv(relative) if row.get(key)
            }
        return self._index_cache[cache_key]

    def _group(self, relative: str, key: str) -> dict[str, list[dict[str, str]]]:
        cache_key = (relative, key)
        if cache_key not in self._group_cache:
            grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
            for row in self._iter_csv(relative):
                if row.get(key):
                    grouped[row[key]].append(row)
            self._group_cache[cache_key] = dict(grouped)
        return self._group_cache[cache_key]

    def validate(self) -> CompanyWorldValidationReport:
        errors: list[str] = []
        warnings: list[str] = []
        missing = [relative for relative in REQUIRED_FILES if not self._exists(relative)]
        if missing:
            errors.extend(f"missing required file: {relative}" for relative in missing)

        source_validation_passed = False
        metrics: dict[str, Any] = {}
        validation_path = self.root / "validation/validation_report.json"
        if validation_path.is_file():
            try:
                source = json.loads(validation_path.read_text())
                source_validation_passed = bool(
                    source.get("ledger_balanced")
                    and source.get("all_tested_foreign_keys_valid")
                    and source.get("inventory_nonnegative")
                )
                metrics.update(
                    {
                        "hidden_anomalies": source.get("hidden_anomalies"),
                        "benchmark_tasks": source.get("benchmark_tasks"),
                        "ledger_balanced": source.get("ledger_balanced"),
                        "foreign_keys_valid": source.get("all_tested_foreign_keys_valid"),
                        "inventory_nonnegative": source.get("inventory_nonnegative"),
                    }
                )
                if not source_validation_passed:
                    errors.append("CompanyWorld source validation report contains failed integrity checks")
            except (OSError, json.JSONDecodeError) as error:
                errors.append(f"invalid source validation report: {error}")

        hidden_objects = {
            row.get("object_id")
            for row in self._rows("ground_truth/hidden_errors.csv.gz")
            if row.get("object_id")
        }
        task_objects = {
            row.get("object_id")
            for row in self._rows("ground_truth/task_answers.csv.gz")
            if row.get("object_id")
        }
        task_oracle_ids_match = hidden_objects == task_objects and bool(hidden_objects)
        if not task_oracle_ids_match and not missing:
            errors.append("hidden errors and task answers do not address the same object set")

        divergence_objects = {
            row.get("object_id")
            for row in self._rows("ground_truth/projection_divergence.csv.gz")
            if row.get("object_id")
        }
        uncovered = hidden_objects - divergence_objects
        if uncovered:
            warnings.append(f"{len(uncovered)} hidden anomalies have no explicit projection divergence")

        return CompanyWorldValidationReport(
            world_id=self.world_id,
            required_files_present=not missing,
            source_validation_passed=source_validation_passed,
            task_oracle_ids_match=task_oracle_ids_match,
            errors=errors,
            warnings=warnings,
            metrics=metrics,
        )

    def _record(
        self,
        *,
        system: CompanySystem,
        record_type: str,
        object_type: str,
        object_id: str,
        fields: dict[str, Any],
        source_file: str,
        suffix: str = "",
        related_object_ids: list[str] | None = None,
    ) -> CompanyWorldRecord:
        sanitized = {key: value for key, value in fields.items() if key not in _PRIVATE_FIELD_NAMES}
        return CompanyWorldRecord(
            record_id=_stable_record_id(system, source_file, object_id, suffix),
            system=system,
            record_type=record_type,
            object_type=object_type,
            object_id=object_id,
            fields=sanitized,
            source_file=source_file,
            related_object_ids=[item for item in (related_object_ids or []) if item],
        )

    def _projection_record(self, divergence: dict[str, str]) -> CompanyWorldRecord:
        system_raw = divergence.get("projection_system", CompanySystem.ERP.value)
        try:
            system = CompanySystem(system_raw)
        except ValueError:
            system = CompanySystem.ERP
        object_id = divergence["object_id"]
        return self._record(
            system=system,
            record_type="system_projection",
            object_type=divergence["object_type"],
            object_id=object_id,
            fields={divergence["field_name"]: _coerce(divergence.get("observed_value"))},
            source_file=f"projection/{system.value.lower()}",
            suffix=divergence["field_name"],
        )

    def _shipment_records(self, hidden: dict[str, str]) -> list[CompanyWorldRecord]:
        shipment_id = hidden["object_id"]
        records: list[CompanyWorldRecord] = []
        shipment = self._index("canonical/shipments.csv.gz", "shipment_id").get(shipment_id)
        if shipment:
            fields = _clean_fields(shipment)
            sales_order_id = shipment.get("sales_order_id", "")
            records.append(
                self._record(
                    system=CompanySystem.WMS,
                    record_type="shipment",
                    object_type="SHIPMENT",
                    object_id=shipment_id,
                    fields=fields,
                    source_file="canonical/shipments.csv.gz",
                    related_object_ids=[sales_order_id],
                )
            )
            if sales_order_id and self._exists("canonical/sales_order_lines.csv.gz"):
                lines = self._group("canonical/sales_order_lines.csv.gz", "sales_order_id").get(
                    sales_order_id, []
                )
                ordered_quantity = sum(int(float(row.get("quantity") or 0)) for row in lines)
                records.append(
                    self._record(
                        system=CompanySystem.ERP,
                        record_type="sales_order_fulfillment_summary",
                        object_type="SALES_ORDER",
                        object_id=sales_order_id,
                        fields={"ordered_quantity": ordered_quantity, "shipment_id": shipment_id},
                        source_file="derived/order_fulfillment_summary",
                        related_object_ids=[shipment_id],
                    )
                )

        records.append(
            self._record(
                system=CompanySystem.WMS,
                record_type="carrier_manifest",
                object_type="SHIPMENT",
                object_id=shipment_id,
                fields={"delivered_quantity": _coerce(hidden.get("true_value"))},
                source_file="derived/carrier_manifest",
                suffix="delivered_quantity",
            )
        )
        for index, message in enumerate(
            self._group("canonical/messages.csv.gz", "related_object_id").get(shipment_id, [])
        ):
            records.append(
                self._record(
                    system=CompanySystem.EMAIL,
                    record_type="message",
                    object_type="MESSAGE",
                    object_id=message.get("message_id", f"message-{index}"),
                    fields=_clean_fields(message),
                    source_file="canonical/messages.csv.gz",
                    suffix=str(index),
                    related_object_ids=[shipment_id],
                )
            )
        return records

    def _invoice_records(self, hidden: dict[str, str]) -> list[CompanyWorldRecord]:
        invoice_id = hidden["object_id"]
        records: list[CompanyWorldRecord] = []
        invoice = self._index("canonical/supplier_invoices.csv.gz", "supplier_invoice_id").get(
            invoice_id
        )
        if not invoice:
            return records
        records.append(
            self._record(
                system=CompanySystem.AP_WORKFLOW,
                record_type="supplier_invoice",
                object_type="SUPPLIER_INVOICE",
                object_id=invoice_id,
                fields=_clean_fields(invoice),
                source_file="canonical/supplier_invoices.csv.gz",
                related_object_ids=[invoice.get("purchase_order_id", "")],
            )
        )
        purchase_order_id = invoice.get("purchase_order_id", "")
        if purchase_order_id and self._exists("canonical/purchase_orders.csv.gz"):
            purchase_order = self._index(
                "canonical/purchase_orders.csv.gz", "purchase_order_id"
            ).get(purchase_order_id)
            if purchase_order:
                records.append(
                    self._record(
                        system=CompanySystem.ERP,
                        record_type="purchase_order",
                        object_type="PURCHASE_ORDER",
                        object_id=purchase_order_id,
                        fields=_clean_fields(purchase_order),
                        source_file="canonical/purchase_orders.csv.gz",
                        related_object_ids=[invoice_id],
                    )
                )
        if purchase_order_id and self._exists("canonical/goods_receipts.csv.gz"):
            receipts = self._group("canonical/goods_receipts.csv.gz", "purchase_order_id").get(
                purchase_order_id, []
            )
            for index, receipt in enumerate(receipts):
                records.append(
                    self._record(
                        system=CompanySystem.WMS,
                        record_type="goods_receipt",
                        object_type="GOODS_RECEIPT",
                        object_id=receipt.get("goods_receipt_id", f"receipt-{index}"),
                        fields=_clean_fields(receipt),
                        source_file="canonical/goods_receipts.csv.gz",
                        suffix=str(index),
                        related_object_ids=[purchase_order_id, invoice_id],
                    )
                )
        records.append(
            self._record(
                system=CompanySystem.AP_WORKFLOW,
                record_type="supplier_submission",
                object_type="SUPPLIER_INVOICE",
                object_id=f"EXT-{invoice_id}",
                fields={
                    "supplier_id": invoice.get("supplier_id"),
                    "purchase_order_id": purchase_order_id,
                    "invoice_amount_usd": _coerce(invoice.get("invoice_amount_usd")),
                    "submitted_reference": invoice_id,
                    "submission_kind": "resubmission",
                },
                source_file="derived/supplier_submission",
                related_object_ids=[invoice_id, purchase_order_id],
            )
        )
        if self._exists("canonical/ledger_entries.csv.gz"):
            entries = self._group("canonical/ledger_entries.csv.gz", "object_id").get(invoice_id, [])
            for index, entry in enumerate(entries):
                records.append(
                    self._record(
                        system=CompanySystem.LEDGER,
                        record_type="journal_entry",
                        object_type="LEDGER_ENTRY",
                        object_id=entry.get("journal_entry_id", f"journal-{index}"),
                        fields=_clean_fields(entry),
                        source_file="canonical/ledger_entries.csv.gz",
                        suffix=str(index),
                        related_object_ids=[invoice_id],
                    )
                )
        return records

    def _authority_records(self, hidden: dict[str, str]) -> list[CompanyWorldRecord]:
        position_id = hidden["object_id"]
        records: list[CompanyWorldRecord] = []
        authority = self._index("canonical/authority_rules.csv.gz", "position_id").get(position_id)
        if authority:
            records.append(
                self._record(
                    system=CompanySystem.AUTH_SERVICE,
                    record_type="policy_rule",
                    object_type="AUTHORITY",
                    object_id=position_id,
                    fields=_clean_fields(authority),
                    source_file="canonical/authority_rules.csv.gz",
                )
            )
        position = None
        if self._exists("canonical/positions.csv.gz"):
            position = self._index("canonical/positions.csv.gz", "position_id").get(position_id)
            if position:
                records.append(
                    self._record(
                        system=CompanySystem.ERP,
                        record_type="position",
                        object_type="POSITION",
                        object_id=position_id,
                        fields=_clean_fields(position),
                        source_file="canonical/positions.csv.gz",
                    )
                )
        person_id = position.get("person_id") if position else None
        if person_id and self._exists("canonical/approvals.csv.gz"):
            approvals = self._group("canonical/approvals.csv.gz", "approver_id").get(person_id, [])
            expense_index = (
                self._index("canonical/expense_claims.csv.gz", "expense_claim_id")
                if self._exists("canonical/expense_claims.csv.gz")
                else {}
            )
            for index, approval in enumerate(approvals[:50]):
                approved_object_id = approval.get("object_id", "")
                fields = _clean_fields(approval)
                expense = expense_index.get(approved_object_id)
                if expense:
                    fields["approved_amount_usd"] = _coerce(expense.get("amount_usd"))
                records.append(
                    self._record(
                        system=CompanySystem.AUTH_SERVICE,
                        record_type="approval_history",
                        object_type="APPROVAL",
                        object_id=approval.get("approval_id", f"approval-{index}"),
                        fields=fields,
                        source_file="canonical/approvals.csv.gz",
                        suffix=str(index),
                        related_object_ids=[position_id, person_id, approved_object_id],
                    )
                )
        return records

    def _records_for_hidden(
        self,
        hidden: dict[str, str],
        divergence: dict[str, str] | None,
    ) -> list[CompanyWorldRecord]:
        object_type = hidden.get("object_type", "")
        if object_type == "SHIPMENT":
            records = self._shipment_records(hidden)
        elif object_type == "SUPPLIER_INVOICE":
            records = self._invoice_records(hidden)
        elif object_type == "AUTHORITY":
            records = self._authority_records(hidden)
        else:
            records = []
        if divergence:
            records.append(self._projection_record(divergence))
        deduped = {record.record_id: record for record in records}
        return sorted(deduped.values(), key=lambda record: record.record_id)

    def compile_episodes(self, limit: int | None = None) -> list[CompanyWorldEpisode]:
        report = self.validate()
        if not report.valid:
            raise ValueError("invalid CompanyWorld dataset: " + "; ".join(report.errors))

        hidden_by_object = {
            row["object_id"]: row
            for row in self._rows("ground_truth/hidden_errors.csv.gz")
            if row.get("object_id")
        }
        divergence_by_object = {
            row["object_id"]: row
            for row in self._rows("ground_truth/projection_divergence.csv.gz")
            if row.get("object_id")
        }
        task_rows = self._rows("ground_truth/task_answers.csv.gz")
        if limit is not None:
            task_rows = task_rows[: max(0, limit)]

        episodes: list[CompanyWorldEpisode] = []
        for task_row in task_rows:
            object_id = task_row["object_id"]
            hidden = hidden_by_object[object_id]
            records = self._records_for_hidden(hidden, divergence_by_object.get(object_id))
            systems = sorted({record.system for record in records}, key=lambda system: system.value)
            target_fact = OperationalFactTarget(
                object_type=hidden["object_type"],
                object_id=object_id,
                field_name=hidden["field_name"],
                expected_value=_coerce(hidden.get("true_value")),
                supporting_record_ids=[
                    record.record_id for record in records if record.record_type != "system_projection"
                ],
            )
            public_task = CompanyWorldTask(
                task_id=task_row["task_id"],
                world_id=self.world_id,
                task_type=task_row["task_type"],
                objective=_public_objective(
                    task_row["task_type"], hidden["object_type"], object_id
                ),
                target_object_type=hidden["object_type"],
                target_object_id=object_id,
                permitted_systems=systems,
                constraints={
                    "must_cite_records": True,
                    "private_ground_truth_unavailable": True,
                    "return_structured_facts": True,
                },
                metadata={
                    "adapter_version": "0.1.0",
                    "record_count": len(records),
                    "system_count": len(systems),
                },
            )
            oracle = CompanyWorldOracle(
                task_id=task_row["task_id"],
                answer_class=task_row["answer_class"],
                expected_resolution=task_row["expected_resolution"],
                answerable=bool(records),
                answerability_reason=(
                    "projected evidence contains an independently observable path to the hidden fact"
                    if records
                    else "no observable records were compiled for this anomaly"
                ),
                facts=[target_fact],
                hidden_error_id=hidden.get("hidden_error_id"),
                hidden_cause=hidden.get("cause"),
            )
            episodes.append(
                CompanyWorldEpisode(
                    episode_id=f"CW-{task_row['task_id']}",
                    world_id=self.world_id,
                    task=public_task,
                    records=records,
                    oracle=oracle,
                    metadata={
                        "company_id": self._company.get("company_id"),
                        "world_seed": _coerce(self._company.get("world_seed")),
                        "world_start": self._company.get("world_start"),
                        "world_end": self._company.get("world_end"),
                    },
                )
            )
        return episodes

    @staticmethod
    def public_projection_leaks(episode: CompanyWorldEpisode) -> list[str]:
        payload = json.dumps(episode.public_payload(), sort_keys=True).casefold()
        return sorted(field for field in _PRIVATE_FIELD_NAMES if f'"{field.casefold()}"' in payload)
