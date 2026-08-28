from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_husky_superior_2018"
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


def test_husky_pilot_enforces_staged_release_cutoffs() -> None:
    deployment = "csb-husky-deployment-2018-04-26"
    update = "csb-husky-factual-update-2018-08-02"
    animation = "csb-husky-interim-animation-2018-08-02"
    final = "csb-husky-final-release-2022-12-29"
    video = "csb-husky-transient-hazards-2023-06-09"

    assert public_ids(datetime(2018, 4, 27, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2018, 4, 27, 12, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2018, 8, 3, 11, 59, 59, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2018, 8, 3, 12, tzinfo=UTC)) == (
        deployment,
        update,
        animation,
    )
    assert public_ids(datetime(2022, 12, 30, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        update,
        animation,
    )
    assert public_ids(datetime(2022, 12, 30, 12, tzinfo=UTC)) == (
        deployment,
        update,
        animation,
        final,
    )
    assert public_ids(datetime(2023, 6, 10, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        update,
        animation,
        final,
    )
    assert public_ids(datetime(2023, 6, 10, 12, tzinfo=UTC)) == (
        deployment,
        update,
        animation,
        final,
        video,
    )


def test_husky_pilot_preserves_stage_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2023, 6, 10, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-husky-deployment-2018-04-26"].kind == "document:context"
    assert by_id["csb-husky-factual-update-2018-08-02"].kind == "document:official_finding"
    assert by_id["csb-husky-interim-animation-2018-08-02"].kind == "video:official_finding"
    assert by_id["csb-husky-final-release-2022-12-29"].kind == "document:official_finding"
    assert by_id["csb-husky-transient-hazards-2023-06-09"].kind == "video:official_finding"


def test_husky_pilot_refuses_approximate_private_timestamp() -> None:
    manifest = load_manifest()

    assert manifest.actual_timeline == ()
    assert manifest.constraints["approximate_event_times_are_not_exact_private_timestamps"] is True


def test_husky_review_id_matches_checked_in_review_record() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-husky-superior-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)


def test_husky_pilot_does_not_time_gate_source_pdfs() -> None:
    locators = tuple(item.locator.lower() for item in load_manifest().fragments)

    assert all(not locator.endswith(".pdf") for locator in locators)
    assert all("assets/" not in locator for locator in locators)


def test_husky_final_conclusion_stays_in_private_oracle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json().lower()

    assert "inadequate transient-operation safeguards" not in public_json
    assert result.bundle.oracle.ground_truth_claims == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert (
        result.bundle.oracle.official_findings[0].finding_id
        == "csb-husky-final-institutional-findings-2022"
    )


def test_husky_pilot_is_bound_to_gold_10_case_selection() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2018-02-I-WI")
    release = next(
        item
        for item in case.evidence_releases
        if item.release_id == "husky-interim-animation-2018"
    )
    manifest = load_manifest()

    assert case.slug == "husky-superior-2018"
    assert manifest.source_case_ids == ("CSB-2018-02-I-WI",)
    expected_tags = {"turnaround", "transient-operations", "fcc", "evacuation", "brittle-fracture"}
    assert expected_tags.issubset(set(case.capability_tags))
    assert release.release_date.isoformat() == "2018-08-02"
