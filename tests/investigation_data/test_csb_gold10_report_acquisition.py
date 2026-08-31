from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

from investigation_world.investigation_data.catalog import find_source, load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus

ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = ROOT / "docs" / "investigation_data"
CORPUS_ROOT = DATA_ROOT / "corpora" / "csb_gold_10"
INDEX_PATH = CORPUS_ROOT / "index.json"
COVERAGE_PATH = CORPUS_ROOT / "pilot_coverage.json"
ACQUISITION_PATH = CORPUS_ROOT / "report_acquisition.json"
VERIFIED_PATH = DATA_ROOT / "verified_artifacts.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "csb-gold10-report-acquisition.yml"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_report_queue_exactly_covers_gold10_and_registered_pilots() -> None:
    index = load_fusion_corpus(INDEX_PATH)
    coverage = load_json(COVERAGE_PATH)
    acquisition = load_json(ACQUISITION_PATH)
    entries = acquisition["artifacts"]
    pilot_entries = coverage["pilots"]
    assert isinstance(entries, list)
    assert isinstance(pilot_entries, list)

    canonical = {case.case_id: case for case in index.cases}
    registered = {entry["case_id"]: entry["pilot_dir"] for entry in pilot_entries}
    queued = {entry["case_id"]: entry for entry in entries}

    assert acquisition["schema_version"] == "1.0"
    assert acquisition["corpus_id"] == index.corpus_id == coverage["corpus_id"]
    assert acquisition["source_id"] == index.source_id == "uscsb"
    assert acquisition["artifact_class"] == "final_report"
    assert set(queued) == set(canonical) == set(registered)
    assert len(entries) == index.target_cases == 10
    assert len({entry["artifact_id"] for entry in entries}) == len(entries)
    assert len({entry["source_url"] for entry in entries}) == len(entries)

    for case_id, entry in queued.items():
        assert entry["pilot_dir"] == registered[case_id]
        assert entry["report_date"] == canonical[case_id].final_report_date.isoformat()


def test_report_queue_matches_csb_acquisition_policy_and_official_host() -> None:
    acquisition = load_json(ACQUISITION_PATH)
    entries = acquisition["artifacts"]
    assert isinstance(entries, list)

    source = find_source(load_catalog(), "uscsb")
    assert source.rights.acquisition.value == "approved"
    assert source.rights.redistribution.value == "review_required"

    for entry in entries:
        parsed = urlparse(entry["source_url"])
        host = (parsed.hostname or "").lower()
        assert parsed.scheme == "https"
        assert host == "csb.gov" or host.endswith(".csb.gov")
        assert entry["url_resolution"] == "official_url_resolved"
        assert entry["artifact_review_status"] in {
            "pending_artifact_level_review",
            "reviewed",
        }


def test_report_verification_state_is_receipt_bound() -> None:
    acquisition = load_json(ACQUISITION_PATH)
    verified_registry = load_json(VERIFIED_PATH)
    entries = acquisition["artifacts"]
    verified_entries = verified_registry["artifacts"]
    assert isinstance(entries, list)
    assert isinstance(verified_entries, list)
    verified_by_id = {item["artifact_id"]: item for item in verified_entries}

    for entry in entries:
        status = entry["verification_status"]
        if status == "pending_binary_acquisition":
            assert entry["sha256"] is None
            assert entry["byte_count"] is None
            assert entry["receipt_sha256"] is None
            assert entry["verified_artifact_id"] is None
            continue

        assert status == "verified"
        verified_artifact_id = entry["verified_artifact_id"]
        assert isinstance(verified_artifact_id, str)
        receipt = verified_by_id[verified_artifact_id]

        assert entry["artifact_id"] == verified_artifact_id
        assert entry["sha256"] == receipt["sha256"]
        assert entry["byte_count"] == receipt["byte_count"]
        assert entry["receipt_sha256"] == receipt["receipt_sha256"]
        assert entry["source_url"] == receipt["source_url"]
        assert entry["resolved_url"] == receipt["resolved_url"]
        assert entry["retrieved_at"] == receipt["retrieved_at"]
        assert entry["catalog_sha256"] == receipt["catalog_sha256"]
        assert receipt["source_id"] == "uscsb"
        assert receipt["content_type"] == "application/pdf"

        assert isinstance(entry["sha256"], str)
        assert SHA256_RE.fullmatch(entry["sha256"])
        assert isinstance(entry["receipt_sha256"], str)
        assert SHA256_RE.fullmatch(entry["receipt_sha256"])
        assert isinstance(entry["catalog_sha256"], str)
        assert SHA256_RE.fullmatch(entry["catalog_sha256"])


def test_all_gold10_final_reports_are_now_byte_verified() -> None:
    acquisition = load_json(ACQUISITION_PATH)
    entries = acquisition["artifacts"]
    assert isinstance(entries, list)
    assert len(entries) == 10
    assert {entry["verification_status"] for entry in entries} == {"verified"}


def test_gold10_corpus_does_not_commit_report_bytes() -> None:
    committed_pdfs = [
        path.relative_to(CORPUS_ROOT).as_posix()
        for path in CORPUS_ROOT.rglob("*")
        if path.is_file() and path.suffix.lower() == ".pdf"
    ]
    assert not committed_pdfs


def test_acquisition_workflow_uses_only_the_bounded_queue_runner() -> None:
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert "Fingerprint both T2 official byte variants" not in workflow
    assert "urllib.request" not in workflow
    assert "for sample in range" not in workflow
    assert "investigation_world.investigation_data.queued_acquisition" in workflow
