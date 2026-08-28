from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_chevron_richmond_2012"
MANIFEST_PATH = PILOT_DIR / "manifest.json"
REVIEW_PATH = PILOT_DIR / "review_record.json"
CORPUS_PATH = ROOT / "docs" / "investigation_data" / "corpora" / "csb_gold_10" / "index.json"
CATALOG = load_catalog()


def load_manifest(*, as_of: datetime | None = None) -> FusionManifest:
    manifest = FusionManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    if as_of is None:
        return manifest
    payload = manifest.model_dump(mode="python")
    payload["simulation_as_of"] = as_of
    return FusionManifest.model_validate(payload)


def public_ids(as_of: datetime) -> tuple[str, ...]:
    return fuse_manifest(load_manifest(as_of=as_of), CATALOG).report.public_fragment_ids


def test_chevron_pilot_enforces_staged_release_cutoffs() -> None:
    surveillance = "csb-chevron-surveillance-2012-09-11"
    interim = "csb-chevron-interim-findings-2013-04-19"
    animation = "csb-chevron-animation-2013-04-19"
    final = "csb-chevron-final-approval-2015-01-30"

    assert public_ids(datetime(2012, 9, 12, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2012, 9, 12, 12, tzinfo=UTC)) == (surveillance,)

    assert public_ids(datetime(2013, 4, 20, 11, 59, 59, tzinfo=UTC)) == (surveillance,)
    assert public_ids(datetime(2013, 4, 20, 12, tzinfo=UTC)) == (
        surveillance,
        interim,
        animation,
    )

    assert public_ids(datetime(2015, 1, 31, 11, 59, 59, tzinfo=UTC)) == (
        surveillance,
        interim,
        animation,
    )
    assert public_ids(datetime(2015, 1, 31, 12, tzinfo=UTC)) == (
        surveillance,
        interim,
        animation,
        final,
    )


def test_chevron_pilot_preserves_primary_vs_institutional_evidence_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2015, 1, 31, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-chevron-surveillance-2012-09-11"].kind == "video:primary_evidence"
    assert by_id["csb-chevron-interim-findings-2013-04-19"].kind == "document:official_finding"
    assert by_id["csb-chevron-animation-2013-04-19"].kind == "video:official_finding"
    assert by_id["csb-chevron-final-approval-2015-01-30"].kind == "document:official_finding"


def test_chevron_pilot_review_id_matches_checked_in_review_record() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-chevron-richmond-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)


def test_chevron_pilot_does_not_time_gate_final_report_pdf() -> None:
    manifest = load_manifest()
    locators = tuple(item.locator.lower() for item in manifest.fragments)

    assert all("chevron_final_investigation_report" not in locator for locator in locators)
    assert all(not locator.endswith(".pdf") for locator in locators)


def test_chevron_final_conclusion_stays_in_private_oracle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json().lower()

    assert "shortcomings in chevron safety culture" not in public_json
    assert result.bundle.oracle.ground_truth_claims == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert (
        result.bundle.oracle.official_findings[0].finding_id
        == "csb-chevron-final-institutional-findings-2015"
    )


def test_chevron_pilot_is_bound_to_gold_10_case_selection() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2012-03-I-CA")
    manifest = load_manifest()

    assert case.slug == "chevron-richmond-2012"
    assert manifest.source_case_ids == ("CSB-2012-03-I-CA",)
    assert {"corrosion", "leak-response"}.issubset(set(case.capability_tags))
    assert {release.release_id for release in case.evidence_releases} == {
        "chevron-surveillance-2012",
        "chevron-animation-2013",
    }
