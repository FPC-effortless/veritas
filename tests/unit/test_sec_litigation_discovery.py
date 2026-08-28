from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from investigation_world.foundry.sec_litigation_discovery import (
    discover_sec_litigation_dataset,
    parse_sec_litigation_page,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_PATH = REPO_ROOT / "tests/unit/fixtures/sec_litigation_sample.html"
PAGE_URL = "https://www.sec.gov/enforcement-litigation/litigation-releases?page=0"


def test_sec_parser_builds_only_paired_cases() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    cases = parse_sec_litigation_page(html, page_url=PAGE_URL, paired_only=True)

    assert [case.case_id for case in cases] == ["LR-26613", "LR-26604"]
    assert all(case.public_evidence for case in cases)
    assert all(case.verifier_references for case in cases)
    assert cases[0].public_evidence[0].title == "SEC Complaint"
    assert cases[0].verifier_references[0].title.startswith("Final Judgment")
    assert cases[0].metadata["release_url"].endswith("/lr-26613")


def test_sec_public_projection_contains_no_disposition_documents() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    cases = parse_sec_litigation_page(html, page_url=PAGE_URL, paired_only=True)

    public_text = json.dumps(cases[0].public_projection(), sort_keys=True)
    assert "Final Judgment" not in public_text
    assert "Consent of Defendant" not in public_text
    assert "final-judgment-26613.pdf" not in public_text
    assert "consent-26613.pdf" not in public_text


def test_sec_parser_ignores_external_hosts() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    cases = parse_sec_litigation_page(html, page_url=PAGE_URL, paired_only=True)
    blaylock = next(case for case in cases if case.case_id == "LR-26604")

    serialized = json.dumps(blaylock.model_dump(mode="json"), sort_keys=True)
    assert "example.com" not in serialized


def test_sec_discovery_deduplicates_and_stops_on_empty_page() -> None:
    html = FIXTURE_PATH.read_text(encoding="utf-8")
    calls: list[str] = []

    def fake_fetcher(url: str) -> str:
        calls.append(url)
        if len(calls) == 1:
            return html
        return "<html><body><table></table></body></html>"

    dataset = discover_sec_litigation_dataset(
        as_of=date(2026, 8, 28),
        max_pages=5,
        delay_seconds=0,
        fetcher=fake_fetcher,
    )

    assert len(dataset.cases) == 2
    assert len(calls) == 2
    assert dataset.source_registry_id == "veritas-public-operations-sources"
    assert all(case.split.value == "train_reference" for case in dataset.cases)
