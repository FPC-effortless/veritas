from __future__ import annotations

from copy import deepcopy

from investigation_world.investigation_data.gold10_manifest import (
    _report_task_eligible,
    build_gold10_manifest,
    manifest_digest,
)

EXPECTED_CASES = {
    "2005-04-I-TX",
    "2008-03-I-FL",
    "2008-05-I-GA",
    "2010-08-I-WA",
    "2012-03-I-CA",
    "2013-02-I-TX",
    "2013-03-I-LA",
    "2017-08-I-TX",
    "2018-02-I-WI",
    "2019-04-I-PA",
}


def test_gold10_manifest_freezes_exact_case_set_and_split() -> None:
    manifest = build_gold10_manifest()
    cases = manifest["cases"]

    assert len(cases) == 10
    assert {case["case_id"] for case in cases} == EXPECTED_CASES
    assert manifest["split_counts"] == {"train": 6, "dev": 2, "eval": 2}

    by_case = {case["case_id"]: case for case in cases}
    assert by_case["2012-03-I-CA"]["split"] == "dev"
    assert by_case["2012-03-I-CA"]["calibration_required"] is True
    assert sum(bool(case["calibration_required"]) for case in cases) >= 1

    task_paths = [case["task_owner_path"] for case in cases]
    verifier_paths = [case["verifier_owner_path"] for case in cases]
    assert len(task_paths) == len(set(task_paths)) == 10
    assert len(verifier_paths) == len(set(verifier_paths)) == 10


def test_gold10_manifest_retains_truth_rights_and_temporal_boundaries() -> None:
    manifest = build_gold10_manifest()

    assert manifest["controlled_private_truth_available"] is False
    for case in manifest["cases"]:
        assert case["truth_regime"] == "institutional_findings"
        assert case["controlled_private_truth_available"] is False
        assert case["contamination_risk"] == "high_public_historical_nonsealed"
        assert case["public_temporal_cut"]["simulation_start"]
        assert case["public_temporal_cut"]["simulation_as_of"]
        assert case["public_temporal_cut"]["date_only_release_policy"] == "next_day_12z"
        assert case["pilot_review_id"]
        assert len(case["pilot_manifest_sha256"]) == 64
        assert len(case["pilot_review_sha256"]) == 64
        assert set(case["available_modalities_at_cut"]) <= set(case["declared_modalities"])

        rights = case["rights"]
        assert rights["source_id"] == "uscsb"
        assert rights["rights"]["acquisition"] == "approved"
        assert rights["rights"]["redistribution"] == "review_required"
        assert rights["rights"]["ai_use"] == "allowed_with_conditions"
        assert rights["rights"]["attribution_required"] is True
        assert rights["contains_personal_data"] is True
        assert rights["requires_redaction_review"] is True
        assert rights["truth"]["official_findings_are_ground_truth"] is False


def test_report_review_status_is_never_an_authority_token() -> None:
    assert _report_task_eligible("pending_artifact_level_review") is False
    assert _report_task_eligible("approved_for_task_use") is False
    assert _report_task_eligible("arbitrary-caller-value") is False


def test_pending_report_review_never_becomes_task_authority() -> None:
    manifest = build_gold10_manifest()

    for case in manifest["cases"]:
        report = case["report"]
        assert report["verification_status"] == "verified"
        assert report["artifact_review_status"] == "pending_artifact_level_review"
        assert report["eligible_for_task_evidence"] is False
        assert "never derives task-use authority" in report["authority_note"]
        assert report["artifact_id"]
        assert report["canonical_source_url"]
        assert report["acquisition_url"]
        assert isinstance(report["byte_count"], int) and report["byte_count"] > 0
        assert len(report["sha256"]) == 64
        assert len(report["receipt_sha256"]) == 64
        assert len(report["catalog_sha256"]) == 64


def test_gold10_manifest_is_deterministic_and_content_bound() -> None:
    first = build_gold10_manifest()
    second = build_gold10_manifest()

    assert first == second
    assert first["manifest_sha256"] == manifest_digest(first)
    assert all(len(value) == 64 for value in first["selection_inputs"].values())

    baseline = manifest_digest(first)
    mutations = []

    changed_split = deepcopy(first)
    changed_split["cases"][0]["split"] = "eval"
    mutations.append(changed_split)

    changed_receipt = deepcopy(first)
    changed_receipt["cases"][0]["report"]["receipt_sha256"] = "0" * 64
    mutations.append(changed_receipt)

    changed_temporal_cut = deepcopy(first)
    changed_temporal_cut["cases"][0]["public_temporal_cut"]["simulation_as_of"] = (
        "2099-01-01T00:00:00Z"
    )
    mutations.append(changed_temporal_cut)

    changed_rights = deepcopy(first)
    changed_rights["cases"][0]["rights"]["rights"]["ai_use"] = "allowed"
    mutations.append(changed_rights)

    changed_pilot = deepcopy(first)
    changed_pilot["cases"][0]["pilot_manifest_sha256"] = "f" * 64
    mutations.append(changed_pilot)

    for mutated in mutations:
        assert manifest_digest(mutated) != baseline


def test_gold10_modalities_respect_the_frozen_public_cut() -> None:
    manifest = build_gold10_manifest()
    by_case = {case["case_id"]: case for case in manifest["cases"]}
    texas_city = by_case["2005-04-I-TX"]

    assert "document" in texas_city["declared_modalities"]
    assert "video" in texas_city["declared_modalities"]
    assert texas_city["available_modalities_at_cut"] == ["document"]

    declared = {
        modality
        for case in manifest["cases"]
        for modality in case["declared_modalities"]
    }
    assert "document" in declared
    assert "video" in declared
