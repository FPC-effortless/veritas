from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_texas_city_2005"
MANIFEST_PATH = PILOT_DIR / "manifest.json"
REVIEW_PATH = PILOT_DIR / "review_record.json"
CATALOG = load_catalog()


def load_manifest(*, as_of: datetime | None = None) -> FusionManifest:
    manifest = FusionManifest.model_validate_json(MANIFEST_PATH.read_text(encoding="utf-8"))
    if as_of is None:
        return manifest
    payload = manifest.model_dump(mode="python")
    payload["simulation_as_of"] = as_of
    return FusionManifest.model_validate(payload)


def public_ids(as_of: datetime) -> tuple[str, ...]:
    result = fuse_manifest(load_manifest(as_of=as_of), CATALOG)
    return result.report.public_fragment_ids


def test_texas_city_pilot_enforces_historical_release_cutoffs() -> None:
    preliminary = "csb-preliminary-findings-2005-10-27"
    organizational = "csb-organizational-findings-2006-10-30"
    final_findings = "csb-final-findings-release-2007-03-20"
    video = "csb-anatomy-of-a-disaster-2008-03-21"

    assert public_ids(datetime(2005, 10, 28, tzinfo=UTC)) == (preliminary,)
    assert public_ids(datetime(2006, 10, 31, tzinfo=UTC)) == (
        preliminary,
        organizational,
    )
    assert public_ids(datetime(2007, 3, 21, tzinfo=UTC)) == (
        preliminary,
        organizational,
        final_findings,
    )
    assert public_ids(datetime(2008, 3, 22, tzinfo=UTC)) == (
        preliminary,
        organizational,
        final_findings,
        video,
    )


def test_texas_city_video_is_multimodal_and_reviewed() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2008, 3, 22, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}
    video = by_id["csb-anatomy-of-a-disaster-2008-03-21"]

    assert video.kind == "video:official_finding"
    assert video.provenance[0].locator == "https://www.youtube.com/watch?v=XuJtdQOU_Z4"
    assert result.report.reviewed_fragment_ids == (
        "csb-preliminary-findings-2005-10-27",
        "csb-organizational-findings-2006-10-30",
        "csb-final-findings-release-2007-03-20",
        "csb-anatomy-of-a-disaster-2008-03-21",
    )


def test_texas_city_review_id_matches_checked_in_review_record() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-texas-city-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}


def test_texas_city_official_conclusion_stays_in_private_oracle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json()

    assert "organizational and safety deficiencies" not in public_json.lower()
    assert result.bundle.oracle.ground_truth_claims == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert (
        result.bundle.oracle.official_findings[0].finding_id
        == "csb-final-organizational-cause-2007"
    )
