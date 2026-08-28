from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_tesoro_anacortes_2010"
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


def test_tesoro_pilot_enforces_staged_release_cutoffs() -> None:
    deployment = "csb-tesoro-deployment-2010-04-02"
    anniversary = "csb-tesoro-anniversary-message-2011-04-01"
    draft = "csb-tesoro-draft-findings-2014-01-29"
    animation = "csb-tesoro-animation-2014-01-30-release"
    final = "csb-tesoro-final-approval-2014-05-01"
    video = "csb-tesoro-behind-curve-2014-10-28"

    assert public_ids(datetime(2010, 4, 3, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2010, 4, 3, 12, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2011, 4, 2, 12, tzinfo=UTC)) == (deployment, anniversary)
    assert public_ids(datetime(2014, 1, 30, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        anniversary,
    )
    assert public_ids(datetime(2014, 1, 30, 12, tzinfo=UTC)) == (
        deployment,
        anniversary,
        draft,
    )
    assert public_ids(datetime(2014, 1, 31, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        anniversary,
        draft,
    )
    assert public_ids(datetime(2014, 1, 31, 12, tzinfo=UTC)) == (
        deployment,
        anniversary,
        draft,
        animation,
    )
    assert public_ids(datetime(2014, 5, 2, 12, tzinfo=UTC)) == (
        deployment,
        anniversary,
        draft,
        animation,
        final,
    )
    assert public_ids(datetime(2014, 10, 29, 12, tzinfo=UTC)) == (
        deployment,
        anniversary,
        draft,
        animation,
        final,
        video,
    )


def test_tesoro_animation_is_not_backdated_to_landing_page_display_date() -> None:
    animation = "csb-tesoro-animation-2014-01-30-release"

    assert animation not in public_ids(datetime(2014, 1, 30, 23, 59, 59, tzinfo=UTC))
    assert animation in public_ids(datetime(2014, 1, 31, 12, tzinfo=UTC))


def test_tesoro_pilot_preserves_context_draft_and_final_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2014, 10, 29, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-tesoro-deployment-2010-04-02"].kind == "document:context"
    assert by_id["csb-tesoro-anniversary-message-2011-04-01"].kind == "video:context"
    assert by_id["csb-tesoro-draft-findings-2014-01-29"].kind == "document:official_finding"
    assert by_id["csb-tesoro-animation-2014-01-30-release"].kind == "video:official_finding"
    assert by_id["csb-tesoro-final-approval-2014-05-01"].kind == "document:official_finding"
    assert by_id["csb-tesoro-behind-curve-2014-10-28"].kind == "video:official_finding"


def test_tesoro_review_records_animation_date_conflict() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    scope = " ".join(review["scope"])

    assert "January 28, 2014" in scope
    assert "January 30, 2014" in scope
    assert review["review_id"] == "review-csb-tesoro-anacortes-link-only-v1"


def test_tesoro_link_only_scope_and_private_truth_boundary() -> None:
    manifest = load_manifest()
    result = fuse_manifest(manifest, CATALOG)

    assert {item.rights_review_id for item in manifest.fragments} == {
        "review-csb-tesoro-anacortes-link-only-v1"
    }
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)
    assert all(not item.locator.lower().endswith(".pdf") for item in manifest.fragments)
    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.actual_timeline == ()
    assert result.bundle.oracle.official_findings[0].finding_id == (
        "csb-tesoro-final-institutional-findings-2014"
    )


def test_tesoro_pilot_is_bound_to_gold_10() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2010-08-I-WA")
    manifest = load_manifest()

    assert case.slug == "tesoro-anacortes-2010"
    assert manifest.source_case_ids == ("CSB-2010-08-I-WA",)
    assert {
        "metallurgy",
        "high-temperature-hydrogen-attack",
        "maintenance",
        "startup",
    }.issubset(set(case.capability_tags))
    assert {item.release_id for item in case.evidence_releases} == {
        "tesoro-behind-curve-2014"
    }
    assert case.evidence_releases[0].release_date.isoformat() == "2014-10-28"
