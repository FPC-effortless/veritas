from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from investigation_world.companyworld import (
    CompanySystem,
    CompanyWorldAdapter,
    public_bundle_payload,
    verify_companyworld,
)
from investigation_world.core.models import InvestigationResult


def _write_csv(root: Path, relative: str, rows: list[dict]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    opener = gzip.open if path.suffix == ".gz" else path.open
    if path.suffix == ".gz":
        handle = opener(path, "wt", newline="", encoding="utf-8")
    else:
        handle = opener("w", newline="", encoding="utf-8")
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root: Path) -> Path:
    _write_csv(
        root,
        "canonical/company.csv.gz",
        [{
            "company_id": "ORG-1",
            "legal_name": "Fixture Co",
            "trading_name": "Fixture",
            "industry": "Testing",
            "world_start": "2023-01-01",
            "world_end": "2025-12-31",
            "world_seed": "42",
            "truth_status": "ground_truth",
            "observability": "public",
        }],
    )
    _write_csv(
        root,
        "canonical/shipments.csv.gz",
        [{
            "shipment_id": "SHP-1",
            "sales_order_id": "SO-1",
            "facility_id": "FAC-1",
            "ship_date": "2025-01-02",
            "delivered_date": "2025-01-05",
            "true_status": "DELIVERED",
            "carrier": "Fixture Freight",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/sales_order_lines.csv.gz",
        [{
            "sales_order_line_id": "SOL-1",
            "sales_order_id": "SO-1",
            "line_number": "1",
            "product_id": "SKU-1",
            "quantity": "10",
            "unit_price_usd": "5",
            "extended_amount_usd": "50",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/messages.csv.gz",
        [{
            "message_id": "MSG-1",
            "thread_id": "THR-1",
            "sent_at": "2025-01-06",
            "sender_id": "PER-1",
            "recipient_id": "PER-2",
            "subject": "Shipment discrepancy",
            "body": "Customer reports a short shipment.",
            "related_object_id": "SHP-1",
            "message_type": "operational",
            "truth_status": "system_record",
            "observability": "role_restricted",
        }],
    )
    _write_csv(
        root,
        "canonical/supplier_invoices.csv.gz",
        [{
            "supplier_invoice_id": "SINV-1",
            "purchase_order_id": "PO-1",
            "supplier_id": "SUP-1",
            "invoice_date": "2025-02-01",
            "due_date": "2025-03-03",
            "invoice_amount_usd": "1250",
            "blocked": "false",
            "status": "APPROVED",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/purchase_orders.csv.gz",
        [{
            "purchase_order_id": "PO-1",
            "supplier_id": "SUP-1",
            "buyer_id": "PER-3",
            "order_date": "2025-01-15",
            "match_policy": "THREE_WAY_GR",
            "status": "CLOSED",
            "order_total_usd": "1250",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/goods_receipts.csv.gz",
        [{
            "goods_receipt_id": "GR-1",
            "purchase_order_id": "PO-1",
            "purchase_order_line_id": "POL-1",
            "product_id": "SKU-1",
            "received_quantity": "25",
            "received_at": "2025-01-20",
            "receiver_id": "PER-4",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/ledger_entries.csv.gz",
        [{
            "journal_entry_id": "JRN-1",
            "transaction_id": "TX-SINV-1",
            "entry_date": "2025-02-01",
            "description": "Supplier invoice",
            "account": "2100-Accounts Payable",
            "debit_usd": "0",
            "credit_usd": "1250",
            "object_type": "SUPPLIER_INVOICE",
            "object_id": "SINV-1",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/authority_rules.csv.gz",
        [{
            "position_id": "POS-1",
            "role_profile_id": "ROLE-1",
            "approval_limit_usd": "1000",
            "can_execute_payment": "false",
            "can_modify_supplier_bank": "false",
            "can_override_shipment": "false",
            "effective_from": "2023-01-01",
        }],
    )
    _write_csv(
        root,
        "canonical/positions.csv.gz",
        [{
            "position_id": "POS-1",
            "person_id": "PER-5",
            "role_profile_id": "ROLE-1",
            "business_unit_id": "BU-1",
            "facility_id": "FAC-1",
            "canonical_title": "Manager",
            "default_approval_limit_usd": "1000",
            "company_id": "ORG-1",
            "active": "true",
        }],
    )
    _write_csv(
        root,
        "canonical/approvals.csv.gz",
        [{
            "approval_id": "APR-1",
            "object_type": "expense_claim",
            "object_id": "EXP-1",
            "requester_id": "PER-6",
            "approver_id": "PER-5",
            "requested_at": "2025-03-01",
            "decided_at": "2025-03-02",
            "decision": "APPROVED",
            "truth_status": "ground_truth",
        }],
    )
    _write_csv(
        root,
        "canonical/expense_claims.csv.gz",
        [{
            "expense_claim_id": "EXP-1",
            "person_id": "PER-6",
            "submitted_at": "2025-03-01",
            "expense_type": "TRAVEL",
            "amount_usd": "1500",
            "project_code": "PRJ-1",
            "overspent": "false",
            "status": "APPROVED",
            "truth_status": "ground_truth",
        }],
    )

    hidden = [
        {
            "hidden_error_id": "HE-1",
            "object_type": "SHIPMENT",
            "object_id": "SHP-1",
            "field_name": "delivered_quantity",
            "true_value": "9",
            "observed_value": "10",
            "cause": "short pick",
            "supporting_evidence": "carrier_manifest;warehouse_scan;customer_report",
            "truth_status": "ground_truth",
            "observability": "private_hidden",
        },
        {
            "hidden_error_id": "HE-2",
            "object_type": "SUPPLIER_INVOICE",
            "object_id": "SINV-1",
            "field_name": "duplicate_status",
            "true_value": "DUPLICATE",
            "observed_value": "UNIQUE",
            "cause": "alternate reference",
            "supporting_evidence": "po_match;invoice_amount;supplier",
            "truth_status": "ground_truth",
            "observability": "private_hidden",
        },
        {
            "hidden_error_id": "HE-3",
            "object_type": "AUTHORITY",
            "object_id": "POS-1",
            "field_name": "approval_limit_usd",
            "true_value": "1000",
            "observed_value": "3000",
            "cause": "misconfigured policy",
            "supporting_evidence": "authority_table;approval_history",
            "truth_status": "ground_truth",
            "observability": "private_hidden",
        },
    ]
    _write_csv(root, "ground_truth/hidden_errors.csv.gz", hidden)
    _write_csv(
        root,
        "ground_truth/task_answers.csv.gz",
        [
            {"task_id": "TASK-1", "task_type": "INVESTIGATE_MISSING_SHIPMENT", "object_id": "SHP-1", "expected_resolution": "Reconcile shipment evidence.", "answer_class": "shipment_short_pick", "observability": "private_hidden"},
            {"task_id": "TASK-2", "task_type": "INVESTIGATE_DUPLICATE_INVOICE", "object_id": "SINV-1", "expected_resolution": "Block duplicate liability.", "answer_class": "duplicate_supplier_invoice", "observability": "private_hidden"},
            {"task_id": "TASK-3", "task_type": "INVESTIGATE_AUTHORITY_BREACH", "object_id": "POS-1", "expected_resolution": "Restore policy limit.", "answer_class": "authority_misconfiguration", "observability": "private_hidden"},
        ],
    )
    _write_csv(
        root,
        "ground_truth/projection_divergence.csv.gz",
        [
            {"hidden_error_id": "HE-1", "object_type": "SHIPMENT", "object_id": "SHP-1", "field_name": "delivered_quantity", "true_value": "9", "observed_value": "10", "projection_system": "ERP", "observability": "role_restricted"},
            {"hidden_error_id": "HE-2", "object_type": "SUPPLIER_INVOICE", "object_id": "SINV-1", "field_name": "duplicate_status", "true_value": "DUPLICATE", "observed_value": "UNIQUE", "projection_system": "AP_WORKFLOW", "observability": "role_restricted"},
            {"hidden_error_id": "HE-3", "object_type": "AUTHORITY", "object_id": "POS-1", "field_name": "approval_limit_usd", "true_value": "1000", "observed_value": "3000", "projection_system": "AUTH_SERVICE", "observability": "role_restricted"},
        ],
    )
    validation = root / "validation/validation_report.json"
    validation.parent.mkdir(parents=True, exist_ok=True)
    validation.write_text(json.dumps({
        "ledger_balanced": True,
        "all_tested_foreign_keys_valid": True,
        "inventory_nonnegative": True,
        "hidden_anomalies": 3,
        "benchmark_tasks": 3,
    }))
    return root


def test_companyworld_compiles_three_operational_families(tmp_path: Path):
    adapter = CompanyWorldAdapter(_fixture(tmp_path))
    report = adapter.validate()
    assert report.valid
    episodes = adapter.compile_episodes()
    assert len(episodes) == 3
    assert {episode.task.task_type for episode in episodes} == {
        "INVESTIGATE_MISSING_SHIPMENT",
        "INVESTIGATE_DUPLICATE_INVOICE",
        "INVESTIGATE_AUTHORITY_BREACH",
    }
    shipment = episodes[0]
    assert {record.system for record in shipment.records} >= {
        CompanySystem.ERP,
        CompanySystem.WMS,
        CompanySystem.EMAIL,
    }


def test_public_payload_does_not_expose_oracle_truth(tmp_path: Path):
    adapter = CompanyWorldAdapter(_fixture(tmp_path))
    episodes = adapter.compile_episodes()
    payload = public_bundle_payload(episodes)
    serialized = json.dumps(payload).casefold()
    for private_name in ["true_value", "cause", "supporting_evidence", "hidden_error_id"]:
        assert f'"{private_name}"' not in serialized
    assert "oracle" not in payload["episodes"][0]
    assert all(not adapter.public_projection_leaks(episode) for episode in episodes)


def test_compilation_is_deterministic(tmp_path: Path):
    root = _fixture(tmp_path)
    first = CompanyWorldAdapter(root).compile_episodes()
    second = CompanyWorldAdapter(root).compile_episodes()
    assert [episode.model_dump(mode="json") for episode in first] == [
        episode.model_dump(mode="json") for episode in second
    ]


def test_companyworld_verifier_requires_correct_fact_and_evidence(tmp_path: Path):
    episode = CompanyWorldAdapter(_fixture(tmp_path)).compile_episodes(limit=1)[0]
    target = episode.oracle.facts[0]
    evidence_id = target.supporting_record_ids[0]
    correct = InvestigationResult(
        claims=[{
            "object_type": target.object_type,
            "object_id": target.object_id,
            "field_name": target.field_name,
            "value": target.expected_value,
        }],
        evidence=[{"record_id": evidence_id}],
        overall_confidence=1.0,
    )
    scored = verify_companyworld(correct, episode)
    assert scored.fact_score == 1.0
    assert scored.evidence_support == 1.0
    assert scored.overall_reward == 1.0

    wrong = InvestigationResult(
        claims=[{
            "object_type": target.object_type,
            "object_id": target.object_id,
            "field_name": target.field_name,
            "value": "definitely wrong",
        }],
        evidence=[{"record_id": evidence_id}],
        overall_confidence=0.0,
    )
    assert verify_companyworld(wrong, episode).overall_reward == 0.0


def test_false_fact_stuffing_reduces_score(tmp_path: Path):
    episode = CompanyWorldAdapter(_fixture(tmp_path)).compile_episodes(limit=1)[0]
    target = episode.oracle.facts[0]
    base = {
        "object_type": target.object_type,
        "object_id": target.object_id,
        "field_name": target.field_name,
        "value": target.expected_value,
    }
    clean = InvestigationResult(
        claims=[base],
        evidence=[{"record_id": target.supporting_record_ids[0]}],
        overall_confidence=1.0,
    )
    stuffed = InvestigationResult(
        claims=[base, {"object_type": "SHIPMENT", "object_id": "OTHER", "field_name": "status", "value": "OK"}],
        evidence=[{"record_id": target.supporting_record_ids[0]}],
        overall_confidence=1.0,
    )
    assert verify_companyworld(stuffed, episode).overall_reward < verify_companyworld(clean, episode).overall_reward
