from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_t2_laboratories_2007"
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


def test_t2_pilot_enforces_staged_release_cutoffs() -> None:
    deployment = "csb-t2-deployment-2007-12-19"
    update = "csb-t2-investigation-update-2008-01-03"
    preliminary = "csb-t2-field-findings-2008-01-25"
    final = "csb-t2-final-release-2009-09-15"
    video = "csb-t2-runaway-video-2009-09-22"

    assert public_ids(datetime(2007, 12, 20, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2007, 12, 20, 12, tzinfo=UTC)) == (deployment,)

    assert public_ids(datetime(2008, 1, 4, 11, 59, 59, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2008, 1, 4, 12, tzinfo=UTC)) == (deployment, update)

    assert public_ids(datetime(2008, 1, 26, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        update,
    )
    assert public_ids(datetime(2008, 1, 26, 12, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
    )

    assert public_ids(datetime(2009, 9, 16, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
    )
    assert public_ids(datetime(2009, 9, 16, 12, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
        final,
    )

    assert public_ids(datetime(2009, 9, 23, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
        final,
    )
    assert public_ids(datetime(2009, 9, 23, 12, tzinfo=UTC)) == (
        deployment,
        update,
        preliminary,
        final,
        video,
    )


def test_t2_pilot_preserves_context_preliminary_and_final_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2009, 9, 23, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-t2-deployment-2007-12-19"].kind == "document:context"
    assert by_id["csb-t2-investigation-update-2008-01-03"].kind == "document:context"
    assert by_id["csb-t2-field-findings-2008-01-25"].kind == "document:official_finding"
    assert by_id["csb-t2-final-release-2009-09-15"].kind == "document:official_finding"
    assert by_id["csb-t2-runaway-video-2009-09-22"].kind == "video:official_finding"


def test_t2_preliminary_findings_do_not_become_private_truth() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2008, 1, 26, 12, tzinfo=UTC)),
        CATALOG,
    )

    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.actual_timeline == ()
    assert len(result.bundle.oracle.official_findings) == 1


def test_t2_review_id_and_link_only_scope_are_consistent() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-t2-laboratories-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)
    assert all(not item.locator.lower().endswith(".pdf") for item in manifest.fragments)


def test_t2_public_exact_times_are_not_promoted_to_private_timeline() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)

    assert result.bundle.oracle.actual_timeline == ()
    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.official_findings[0].finding_id == (
        "csb-t2-final-institutional-findings-2009"
    )


def test_t2_final_conclusion_stays_out_of_initial_public_bundle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json().lower()

    assert "insufficient reactor cooling" not in public_json
    assert "did not recognize the reactive hazards" not in public_json


def test_t2_pilot_is_bound_to_gold_10() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2008-03-I-FL")
    manifest = load_manifest()

    assert case.slug == "t2-laboratories-2007"
    assert manifest.source_case_ids == ("CSB-2008-03-I-FL",)
    assert {
        "reactive-chemistry",
        "thermal-runaway",
        "hazard-recognition",
        "process-design",
    }.issubset(set(case.capability_tags))
    assert {item.release_id for item in case.evidence_releases} == {"t2-runaway-2009"}
    assert case.evidence_releases[0].release_date.isoformat() == "2009-09-22"
