from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from investigation_world.investigation_data.catalog import load_catalog
from investigation_world.investigation_data.corpus import load_fusion_corpus
from investigation_world.investigation_data.fusion import FusionManifest, fuse_manifest

ROOT = Path(__file__).resolve().parents[2]
PILOT_DIR = ROOT / "docs" / "investigation_data" / "pilots" / "csb_pes_philadelphia_2019"
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


def test_pes_pilot_enforces_staged_release_cutoffs() -> None:
    deployment = "csb-pes-deployment-2019-06-21"
    factual = "csb-pes-factual-update-2019-10-16"
    animation = "csb-pes-preliminary-animation-2019-10-16"
    final = "csb-pes-final-release-2022-10-11"
    wake_up = "csb-pes-wake-up-call-2022-10-27"

    assert public_ids(datetime(2019, 6, 22, 11, 59, 59, tzinfo=UTC)) == ()
    assert public_ids(datetime(2019, 6, 22, 12, tzinfo=UTC)) == (deployment,)

    assert public_ids(datetime(2019, 10, 17, 11, 59, 59, tzinfo=UTC)) == (deployment,)
    assert public_ids(datetime(2019, 10, 17, 12, tzinfo=UTC)) == (
        deployment,
        factual,
        animation,
    )

    assert public_ids(datetime(2022, 10, 12, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        factual,
        animation,
    )
    assert public_ids(datetime(2022, 10, 12, 12, tzinfo=UTC)) == (
        deployment,
        factual,
        animation,
        final,
    )

    assert public_ids(datetime(2022, 10, 28, 11, 59, 59, tzinfo=UTC)) == (
        deployment,
        factual,
        animation,
        final,
    )
    assert public_ids(datetime(2022, 10, 28, 12, tzinfo=UTC)) == (
        deployment,
        factual,
        animation,
        final,
        wake_up,
    )


def test_pes_pilot_preserves_evidence_roles() -> None:
    result = fuse_manifest(
        load_manifest(as_of=datetime(2022, 10, 28, 12, tzinfo=UTC)),
        CATALOG,
    )
    by_id = {item.evidence_id: item for item in result.bundle.public.evidence}

    assert by_id["csb-pes-deployment-2019-06-21"].kind == "document:context"
    assert by_id["csb-pes-factual-update-2019-10-16"].kind == "document:official_finding"
    assert by_id["csb-pes-preliminary-animation-2019-10-16"].kind == (
        "video:official_finding"
    )
    assert by_id["csb-pes-final-release-2022-10-11"].kind == "document:official_finding"
    assert by_id["csb-pes-wake-up-call-2022-10-27"].kind == "video:official_finding"


def test_pes_pilot_preserves_both_public_csb_identifiers() -> None:
    manifest = load_manifest()
    aliases = {"CSB-2019-04-I-PA", "CSB-2019-06-I-PA"}

    assert set(manifest.source_case_ids) == aliases
    assert all(set(fragment.case_ids) == aliases for fragment in manifest.fragments)

    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    assert set(review["source_case_aliases"]) == aliases
    assert review["case_id"] == "CSB-2019-04-I-PA"


def test_pes_pilot_review_id_matches_checked_in_review_record() -> None:
    review = json.loads(REVIEW_PATH.read_text(encoding="utf-8"))
    manifest = load_manifest()

    assert review["status"] == "approved_for_link_only_pilot"
    assert review["review_id"] == "review-csb-pes-philadelphia-link-only-v1"
    assert {item.rights_review_id for item in manifest.fragments} == {review["review_id"]}
    assert all(item.locator.startswith("https://www.csb.gov/") for item in manifest.fragments)


def test_pes_pilot_does_not_check_in_report_or_factual_update_pdfs() -> None:
    locators = tuple(item.locator.lower() for item in load_manifest().fragments)

    assert all(not locator.endswith(".pdf") for locator in locators)
    assert all("pes_final_report" not in locator for locator in locators)
    assert all("pes_factual_update" not in locator for locator in locators)


def test_pes_public_exact_times_are_not_promoted_to_private_truth() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)

    assert result.bundle.oracle.ground_truth_claims == ()
    assert result.bundle.oracle.actual_timeline == ()
    assert len(result.bundle.oracle.official_findings) == 1
    assert result.bundle.oracle.official_findings[0].finding_id == (
        "csb-pes-final-institutional-findings-2022"
    )


def test_pes_final_conclusion_stays_out_of_public_bundle() -> None:
    result = fuse_manifest(load_manifest(), CATALOG)
    public_json = result.bundle.public.model_dump_json().lower()

    assert "inherently-safer-design issues" not in public_json


def test_pes_pilot_is_bound_to_gold_10_without_rewriting_source_alias() -> None:
    corpus = load_fusion_corpus(CORPUS_PATH)
    case = next(item for item in corpus.cases if item.case_id == "2019-04-I-PA")
    manifest = load_manifest()
    releases = {item.release_id: item for item in case.evidence_releases}

    assert case.slug == "pes-philadelphia-2019"
    assert "CSB-2019-04-I-PA" in manifest.source_case_ids
    assert "CSB-2019-06-I-PA" in manifest.source_case_ids
    assert {
        "hydrofluoric-acid",
        "corrosion",
        "safeguards",
        "offsite-consequence",
        "inherently-safer-design",
    }.issubset(set(case.capability_tags))
    assert releases["pes-preliminary-animation-2019"].release_date.isoformat() == (
        "2019-10-16"
    )
    assert releases["pes-wake-up-call-2022"].release_date.isoformat() == "2022-10-27"
