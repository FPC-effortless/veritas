from __future__ import annotations

import csv
import gzip
import json
from pathlib import Path

from investigation_world.benchmark import validate_companyworld_benchmark
from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.companyworld import (
    CompanyWorldAdapter,
    CompanyWorldTaskDistributionConfig,
    compile_expanded_episodes,
    compile_task_distribution,
    verify_companyworld,
)
from investigation_world.core.models import InvestigationResult


def _write_csv(root: Path, relative: str, rows: list[dict]) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0])
    opener = gzip.open if path.suffix == ".gz" else path.open
    handle = (
        opener(path, "wt", newline="", encoding="utf-8")
        if path.suffix == ".gz"
        else opener("w", newline="", encoding="utf-8")
    )
    with handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fixture(root: Path) -> Path:
    _write_csv(root, "canonical/company.csv.gz", [{"company_id":"ORG-1","legal_name":"Fixture Co","trading_name":"Fixture","industry":"Testing","world_start":"2023-01-01","world_end":"2025-12-31","world_seed":"42","truth_status":"ground_truth","observability":"public"}])
    _write_csv(root, "canonical/sales_orders.csv.gz", [{"sales_order_id":"SO-1","customer_id":"CUS-1","order_date":"2025-01-01 00:00:00","salesperson_id":"PER-1","fulfillment_facility_id":"FAC-1","requested_ship_date":"2025-01-03 00:00:00","status":"FULFILLED","truth_status":"ground_truth","order_total_usd":"1000"}])
    _write_csv(root, "canonical/shipments.csv.gz", [{"shipment_id":"SHP-1","sales_order_id":"SO-1","facility_id":"FAC-1","ship_date":"2025-01-05 00:00:00","delivered_date":"2025-01-07 00:00:00","true_status":"DELIVERED","carrier":"Fixture Freight","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/purchase_orders.csv.gz", [{"purchase_order_id":"PO-1","supplier_id":"SUP-1","buyer_id":"PER-2","order_date":"2025-01-01","match_policy":"THREE_WAY_GR","status":"CLOSED","order_total_usd":"1000","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/purchase_order_lines.csv.gz", [{"purchase_order_line_id":"POL-1","purchase_order_id":"PO-1","line_number":"1","product_id":"SKU-1","ordered_quantity":"10","unit_cost_usd":"100","line_total_usd":"1000","received_quantity":"10","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/goods_receipts.csv.gz", [{"goods_receipt_id":"GR-1","purchase_order_id":"PO-1","purchase_order_line_id":"POL-1","product_id":"SKU-1","received_quantity":"10","received_at":"2025-01-02","receiver_id":"PER-3","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/supplier_invoices.csv.gz", [{"supplier_invoice_id":"SINV-1","purchase_order_id":"PO-1","supplier_id":"SUP-1","invoice_date":"2025-01-03","due_date":"2025-02-02","invoice_amount_usd":"1001","blocked":"true","status":"BLOCKED","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/customer_invoices.csv.gz", [{"customer_invoice_id":"CINV-1","sales_order_id":"SO-1","customer_id":"CUS-1","invoice_date":"2025-01-08 00:00:00","due_date":"2025-02-07 00:00:00","invoice_amount_usd":"1000","status":"PAID","truth_status":"ground_truth","paid_amount_usd":"1000","open_amount_usd":"0"}])
    _write_csv(root, "canonical/customer_payments.csv.gz", [{"payment_id":"CPAY-1","customer_invoice_id":"CINV-1","customer_id":"CUS-1","payment_date":"2025-01-20 00:00:00","amount_usd":"1000","payment_method":"ACH","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/incident_tickets.csv.gz", [{"incident_ticket_id":"INC-1","service":"ERP","created_at":"2025-01-01 00:00:00","severity":"P2","reported_by":"PER-4","assigned_team":"Infrastructure","reassignments":"1","resolved_at":"2025-01-01 10:00:00","status":"RESOLVED","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/process_events.csv.gz", [
        {"process_event_id":"PE-P2P-1","process_instance_id":"PO-1","procedure_id":"PROC-P2P","activity":"Payment Block","event_time":"2025-01-05 00:00:00","resource_id":"PER-5","truth_status":"ground_truth"},
        {"process_event_id":"PE-P2P-2","process_instance_id":"PO-1","procedure_id":"PROC-P2P","activity":"Remove Payment Block","event_time":"2025-01-06 12:00:00","resource_id":"PER-5","truth_status":"ground_truth"},
        {"process_event_id":"PE-INC-1","process_instance_id":"INC-1","procedure_id":"PROC-INC","activity":"Report","event_time":"2025-01-01 00:00:00","resource_id":"PER-4","truth_status":"ground_truth"},
        {"process_event_id":"PE-INC-2","process_instance_id":"INC-1","procedure_id":"PROC-INC","activity":"Resolve","event_time":"2025-01-01 10:00:00","resource_id":"PER-6","truth_status":"ground_truth"},
    ])
    _write_csv(root, "canonical/safety_incidents.csv.gz", [{"safety_incident_id":"SAF-1","facility_id":"FAC-1","event_time":"2025-01-10 00:00:00","incident_type":"FORKLIFT","severity":"SERIOUS","days_away":"4","affected_role_profile_id":"ROLE-1","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/corrective_actions.csv.gz", [{"corrective_action_id":"CA-1","source_type":"SAFETY_INCIDENT","source_id":"SAF-1","owner_id":"PER-7","due_date":"2025-02-01","status":"OPEN","truth_status":"ground_truth"}])
    _write_csv(root, "canonical/ledger_entries.csv.gz", [
        {"journal_entry_id":"JRN-1","transaction_id":"TX-CINV-1","entry_date":"2025-01-08","description":"Customer invoice","account":"1100-Accounts Receivable","debit_usd":"1000","credit_usd":"0","object_type":"CUSTOMER_INVOICE","object_id":"CINV-1","truth_status":"ground_truth"},
        {"journal_entry_id":"JRN-2","transaction_id":"TX-CINV-1","entry_date":"2025-01-08","description":"Customer invoice","account":"4000-Sales Revenue","debit_usd":"0","credit_usd":"1000","object_type":"CUSTOMER_INVOICE","object_id":"CINV-1","truth_status":"ground_truth"},
    ])
    _write_csv(root, "canonical/messages.csv.gz", [{"message_id":"MSG-1","related_object_id":"SHP-1","body":"shipment note"}])
    _write_csv(root, "canonical/authority_rules.csv.gz", [{"position_id":"POS-1","approval_limit_usd":"1000"}])
    _write_csv(root, "ground_truth/hidden_errors.csv.gz", [{"hidden_error_id":"HE-1","object_type":"SHIPMENT","object_id":"SHP-1","field_name":"delivered_quantity","true_value":"9","observed_value":"10","cause":"short pick","supporting_evidence":"carrier_manifest","truth_status":"ground_truth","observability":"private_hidden"}])
    _write_csv(root, "ground_truth/task_answers.csv.gz", [{"task_id":"TASK-1","task_type":"INVESTIGATE_MISSING_SHIPMENT","object_id":"SHP-1","expected_resolution":"reconcile","answer_class":"shipment_short_pick","observability":"private_hidden"}])
    _write_csv(root, "ground_truth/projection_divergence.csv.gz", [{"hidden_error_id":"HE-1","object_type":"SHIPMENT","object_id":"SHP-1","field_name":"delivered_quantity","true_value":"9","observed_value":"10","projection_system":"ERP","observability":"role_restricted"}])
    validation = root / "validation/validation_report.json"
    validation.parent.mkdir(parents=True, exist_ok=True)
    validation.write_text(json.dumps({"ledger_balanced":True,"all_tested_foreign_keys_valid":True,"inventory_nonnegative":True,"hidden_anomalies":1,"benchmark_tasks":1}))
    return root


def test_expanded_distribution_compiles_all_families_and_public_solver_succeeds(tmp_path: Path):
    adapter = CompanyWorldAdapter(_fixture(tmp_path))
    episodes = compile_expanded_episodes(adapter, per_family=1)
    assert len(episodes) == 8
    assert len({episode.task.task_type for episode in episodes}) == 8
    policy = PublicEvidenceReferencePolicy()
    for episode in episodes:
        assert verify_companyworld(policy(episode.public_payload()), episode).overall_reward == 1.0
        assert not adapter.public_projection_leaks(episode)


def test_multi_record_fact_requires_complete_evidence(tmp_path: Path):
    adapter = CompanyWorldAdapter(_fixture(tmp_path))
    episode = compile_expanded_episodes(
        adapter,
        per_family=1,
        families=("O2C_FULFILLMENT_TIMING",),
    )[0]
    fact = episode.oracle.facts[0]
    complete = PublicEvidenceReferencePolicy()(episode.public_payload())
    result = InvestigationResult(
        claims=complete.claims,
        evidence=[{"record_id": fact.supporting_record_ids[0]}],
        overall_confidence=1.0,
    )
    scored = verify_companyworld(result, episode)
    assert scored.fact_score == 1.0
    assert scored.evidence_support == 0.5
    assert scored.overall_reward < 1.0


def test_distribution_benchmark_and_compilation_are_deterministic(tmp_path: Path):
    root = _fixture(tmp_path)
    config = CompanyWorldTaskDistributionConfig(per_family=1, include_legacy=False)
    first = compile_task_distribution(root, config=config)[1]
    second = compile_task_distribution(root, config=config)[1]
    assert [episode.model_dump(mode="json") for episode in first] == [
        episode.model_dump(mode="json") for episode in second
    ]
    report = validate_companyworld_benchmark(
        root,
        expanded=True,
        per_family=1,
        include_legacy=False,
    )
    assert report.passed
    assert report.episodes == 8
    assert report.metadata["expanded_distribution"] is True
