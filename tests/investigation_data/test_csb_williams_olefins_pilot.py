from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_williams_olefins_2013"
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


def test_williams_pilot_enforces_sparse_release_cutoffs() -> None:
    deployment = "csb-williams-deployment-2013-06-14"
    final = "csb-williams-final-release-2016-10-19"
    video = "csb-williams-blocked-in-2017-01-25"

    assert public_ids(datetime(2013, 6, 15, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2013, 6, 15, 12, tzinfo=UTC)) == (deployment,)

    assert public_ids(datetime(2016, 10, 20, 11, 59, 59, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2016, 10, 20, 12, tzinfo=UTC)) == (deployment, final)

    assert public_ids(datetime(2017, 1, 26, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        final,
    )
    assert public_ids(datetime(2017, 1, 26, 12, tzinfo=UTC)) == (
        deployment,
        final,
        video,
    )


def test_williams_pilot_does_not_invent_pre_final_evidence() -> None:
    manifest = load_manifest()
    fragment_ids = tuple(item.fragment_id for item in manifest.fragments)

    assert fragment_ids == (
        "csb-williams-deployment-2013-06-14",
        "csb-williams-final-release-2016-10-19",
        "csb-williams-blocked-in-2017-01-25",
    )
    assert public_ids(datetime(2015, 1, 1, 12, tzinfo=UTC)) == (
        "csb-williams-deployment-2013-06-14",
    )


def test_williams_pilot_preserves_evidence_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2017, 1, 26, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-williams-deployment-2013-06-14"].kind == "document:context"
    assert by_id["csb-williams-final-release-2016-10-19"].kind == (
        "document:official_finding"
    )
    assert by_id["csb-williams-blocked-in-2017-01-25"].kind == "video:official_finding"


def test_williams_pilot_preserves_identifier_aliases() -> None:
    manifest = load_manifest()
    aliases = {"CSB-2013-03-I-LA", "CSB-2013-3-I-LA"}

    assert set(manifest.source_case_ids) == aliases
    assert all(set(fragment.case_ids) == aliases for fragment in manifest.fragments)

    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    assert set(review["source_case_aliases"]) == aliases
    assert review["case_id"] == "CSB-2013-03-I-LA"


def test_williams_pilot_review_and_link_only_scope_are_consistent() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-williams-olefins-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)
    assert all(not item.locator.lower().endswith(".pdf") for item in manifest.fragments)


def test_williams_final_findings_remain_institutional_not_private_truth() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)

    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.actual_timeline == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert result.bundle.oracle.official_findings[0].finding_id == (
        "csb-williams-final-institutional-findings-2016"
    )


def test_williams_pilot_is_bound_to_gold_10() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2013-03-I-LA")
    manifest = load_manifest()

    assert case.slug == "williams-olefins-2013"
    assert "CSB-2013-03-I-LA" in manifest.source_case_ids
    assert "CSB-2013-3-I-LA" in manifest.source_case_ids
    assert {
        "overpressure",
        "equipment-isolation",
        "nonroutine-operations",
        "process-safety-management",
    }.issubset(set(case.capability_tags))
    assert {item.release_id for item in case.evidence_releases} == {
        "williams-blocked-in-2017"
    }
    assert case.evidence_releases[0].release_date.isoformat() == "2017-01-25"
