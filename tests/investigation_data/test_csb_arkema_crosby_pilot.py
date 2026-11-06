from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_arkema_crosby_2017"
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


def test_arkema_pilot_enforces_staged_release_cutoffs() -> None:
    statement = "csb-arkema-investigation-statement-2017-08-31"
    animation = "csb-arkema-preliminary-animation-2017-11-15"
    final = "csb-arkema-final-release-2018-05-24"

    assert public_ids(datetime(2017, 9, 1, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2017, 9, 1, 12, tzinfo=UTC)) == (statement,)
    assert public_ids(datetime(2017, 11, 16, 11, 59, 59, tzinfo=UTC)) == (statement,)
    assert public_ids(datetime(2017, 11, 16, 12, tzinfo=UTC)) == (
        statement,
        animation,
    )
    assert public_ids(datetime(2018, 5, 25, 11, 59, 59, tzinfo=UTC)) == (
        statement,
        animation,
    )
    assert public_ids(datetime(2018, 5, 25, 12, tzinfo=UTC)) == (
        statement,
        animation,
        final,
    )


def test_arkema_pilot_preserves_context_vs_reconstruction_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2018, 5, 25, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    statement = by_id["csb-arkema-investigation-statement-2017-08-31"]
    animation = by_id["csb-arkema-preliminary-animation-2017-11-15"]
    final = by_id["csb-arkema-final-release-2018-05-24"]

    assert statement.kind == "document:context"
    assert animation.kind == "video:official_finding"
    assert final.kind == "document:official_finding"


def test_arkema_pilot_refuses_invented_private_event_timestamps() -> None:
    manifest = load_manifest()

    assert manifest.actual_timeline == ()
    assert manifest.constraints["source_event_dates_are_date_precision_only"] is True


def test_arkema_review_id_matches_checked_in_review_record() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-arkema-crosby-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)


def test_arkema_pilot_does_not_time_gate_final_report_pdf() -> None:
    locators = tuple(item.locator.lower() for item in load_manifest().fragments)

    assert all(not locator.endswith(".pdf") for locator in locators)
    assert all("arkema_inc_chemical_plant_final" not in locator for locator in locators)


def test_arkema_final_conclusion_stays_in_private_oracle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json().lower()

    assert "significant lack of industry guidance" not in public_json
    assert result.bundle.oracle.ground_truth_claims == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert (
        result.bundle.oracle.official_findings[0].finding_id
        == "csb-arkema-final-institutional-findings-2018"
    )


def test_arkema_pilot_is_bound_to_gold_10_case_selection() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2017-08-I-TX")
    release = next(
        item
        for item in case.evidence_releases
        if item.release_id == "arkema-preliminary-animation-2017"
    )
    manifest = load_manifest()

    assert case.slug == "arkema-crosby-2017"
    assert manifest.source_case_ids == ("CSB-2017-08-I-TX",)
    assert {"extreme-weather", "flooding", "refrigeration-loss", "resilience"}.issubset(
        set(case.capability_tags)
    )
    assert release.release_date.isoformat() == "2017-11-15"
