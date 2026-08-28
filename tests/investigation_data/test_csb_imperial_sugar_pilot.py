from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_imperial_sugar_2008"
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


def test_imperial_pilot_enforces_staged_release_cutoffs() -> None:
    deployment = "csb-imperial-deployment-2008-02-08"
    update = "csb-imperial-update-2008-02-17"
    preliminary = "csb-imperial-preliminary-propagation-2008-03-12"
    final = "csb-imperial-final-release-2009-09-24"
    video = "csb-imperial-inferno-video-2009-10-06"

    assert public_ids(datetime(2008, 2, 9, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2008, 2, 9, 12, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2008, 2, 18, 12, tzinfo=UTC)) == (deployment, update)
    assert public_ids(datetime(2008, 3, 13, 11, 59, 59, tzinfo=UTC)) == (deployment, update)
    assert public_ids(datetime(2008, 3, 13, 12, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
    )
    assert public_ids(datetime(2009, 9, 25, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
    )
    assert public_ids(datetime(2009, 9, 25, 12, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
        final,
    )
    assert public_ids(datetime(2009, 10, 7, 12, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
        final,
        video,
    )


def test_imperial_pilot_preserves_evidence_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2009, 10, 7, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-imperial-deployment-2008-02-08"].kind == "document:context"
    assert by_id["csb-imperial-update-2008-02-17"].kind == "document:context"
    assert by_id["csb-imperial-preliminary-propagation-2008-03-12"].kind == (
        "document:official_finding"
    )
    assert by_id["csb-imperial-final-release-2009-09-24"].kind == (
        "document:official_finding"
    )
    assert by_id["csb-imperial-inferno-video-2009-10-06"].kind == "video:official_finding"


def test_imperial_preliminary_stage_preserves_primary_event_uncertainty() -> None:
    manifest = load_manifest(as_of=datetime(2008, 3, 13, 12, tzinfo=UTC))

    assert manifest.constraints["primary_event_uncertainty_must_be_preserved"] is True
    result = fuse_manifest(manifest, CATALOG)
    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.actual_timeline == ()


def test_imperial_review_and_link_only_scope_are_consistent() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-imperial-sugar-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)
    assert all(not item.locator.lower().endswith(".pdf") for item in manifest.fragments)


def test_imperial_final_findings_remain_institutional_not_private_truth() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)

    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.actual_timeline == ()
    assert result.bundle.oracle.official_findings[0].finding_id == (
        "csb-imperial-final-institutional-findings-2009"
    )


def test_imperial_pilot_is_bound_to_gold_10() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2008-05-I-GA")
    manifest = load_manifest()

    assert case.slug == "imperial-sugar-2008"
    assert manifest.source_case_ids == ("CSB-2008-05-I-GA",)
    assert {
        "combustible-dust",
        "housekeeping",
        "equipment-design",
        "secondary-explosions",
    }.issubset(set(case.capability_tags))
    assert {item.release_id for item in case.evidence_releases} == {"imperial-inferno-2009"}
    assert case.evidence_releases[0].release_date.isoformat() == "2009-10-06"
