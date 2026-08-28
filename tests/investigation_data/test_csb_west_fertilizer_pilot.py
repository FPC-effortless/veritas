from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_west_fertilizer_2013"
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


def test_west_pilot_enforces_staged_release_cutoffs() -> None:
    release_news = "csb-west-video-release-news-2013-05-03"
    damage_video = "csb-west-blast-damage-video-page-2013-05-10"
    preliminary = "csb-west-preliminary-findings-2014-04-22"
    final = "csb-west-final-approval-2016-01-29"
    final_video = "csb-west-dangerously-close-2016-01-29"

    assert public_ids(datetime(2013, 5, 4, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2013, 5, 4, 12, tzinfo=UTC)) == (release_news,)

    assert public_ids(datetime(2013, 5, 11, 11, 59, 59, tzinfo=UTC)) == (release_news,)
    assert public_ids(datetime(2013, 5, 11, 12, tzinfo=UTC)) == (
        release_news,
        damage_video,
    )

    assert public_ids(datetime(2014, 4, 23, 11, 59, 59, tzinfo=UTC)) == (
        release_news,
        damage_video,
    )
    assert public_ids(datetime(2014, 4, 23, 12, tzinfo=UTC)) == (
        release_news,
        damage_video,
        preliminary,
    )

    assert public_ids(datetime(2016, 1, 30, 11, 59, 59, tzinfo=UTC)) == (
        release_news,
        damage_video,
        preliminary,
    )
    assert public_ids(datetime(2016, 1, 30, 12, tzinfo=UTC)) == (
        release_news,
        damage_video,
        preliminary,
        final,
        final_video,
    )


def test_west_pilot_preserves_release_announcement_vs_primary_media_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2016, 1, 30, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-west-video-release-news-2013-05-03"].kind == "document:context"
    assert by_id["csb-west-blast-damage-video-page-2013-05-10"].kind == "video:primary_evidence"
    assert by_id["csb-west-preliminary-findings-2014-04-22"].kind == "document:official_finding"
    assert by_id["csb-west-final-approval-2016-01-29"].kind == "document:official_finding"
    assert by_id["csb-west-dangerously-close-2016-01-29"].kind == "video:official_finding"


def test_west_pilot_keeps_may_3_and_may_10_provenance_separate() -> None:
    manifest = load_manifest()
    by_id = {item.fragment_id: item for item in manifest.fragments}

    assert by_id["csb-west-video-release-news-2013-05-03"].available_from == datetime(
        2013, 5, 4, 12, tzinfo=UTC
    )
    assert by_id["csb-west-blast-damage-video-page-2013-05-10"].available_from == datetime(
        2013, 5, 11, 12, tzinfo=UTC
    )
    assert by_id["csb-west-video-release-news-2013-05-03"].locator != by_id[
        "csb-west-blast-damage-video-page-2013-05-10"
    ].locator


def test_west_pilot_review_id_matches_checked_in_review_record() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-west-fertilizer-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)


def test_west_pilot_does_not_time_gate_final_report_pdf() -> None:
    locators = tuple(item.locator.lower() for item in load_manifest().fragments)

    assert all(not locator.endswith(".pdf") for locator in locators)
    assert all("west_fertilizer_final_report" not in locator for locator in locators)


def test_west_final_conclusion_stays_in_private_oracle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json().lower()

    assert "land-use planning around the facility" not in public_json
    assert result.bundle.oracle.ground_truth_claims == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert (
        result.bundle.oracle.official_findings[0].finding_id
        == "csb-west-final-institutional-findings-2016"
    )


def test_west_pilot_is_bound_to_gold_10_without_rewriting_video_page_date() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2013-02-I-TX")
    release = next(
        item for item in case.evidence_releases if item.release_id == "west-blast-damage-2013"
    )
    manifest = load_manifest()

    assert case.slug == "west-fertilizer-2013"
    assert manifest.source_case_ids == ("CSB-2013-02-I-TX",)
    assert {"emergency-response", "community-risk", "land-use"}.issubset(
        set(case.capability_tags)
    )
    assert release.release_date.isoformat() == "2013-05-10"
    assert any(
        item.fragment_id == "csb-west-video-release-news-2013-05-03"
        for item in manifest.fragments
    )
    assert any(
        item.fragment_id == "csb-west-blast-damage-video-page-2013-05-10"
        for item in manifest.fragments
    )
