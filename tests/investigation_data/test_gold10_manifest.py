from __future__ import annotations

from copy import deepcopy

import pytest

import investigation_world.investigation_data.gold10_manifest as gold10_manifest
from investigation_world.investigation_data.gold10_manifest import (
    EXPECTED_TASK_OWNER_ROOT,
    EXPECTED_TASK_USE_DECISION,
    EXPECTED_TASK_USE_RESTRICTIONS,
    EXPECTED_VERIFIER_OWNER_ROOT,
    Gold10ManifestError,
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
    assert all(path.startswith(f"{EXPECTED_TASK_OWNER_ROOT}/") for path in task_paths)
    assert all(path.startswith(f"{EXPECTED_VERIFIER_OWNER_ROOT}/") for path in verifier_paths)
    assert all(path.endswith(".py") for path in task_paths + verifier_paths)
    assert all(case["capability_targets"] for case in cases)
    assert all(
        all(isinstance(target, str) and target for target in case["capability_targets"])
        for case in cases
    )


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


@pytest.mark.parametrize(
    "field",
    ["attribution_required", "contains_personal_data", "requires_redaction_review"],
)
def test_source_policy_true_boundaries_fail_closed_on_false(
    monkeypatch,
    field: str,
) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if path.name == "source_catalog.json":
            value = deepcopy(value)
            source = next(
                item for item in value["sources"] if item["source_id"] == "uscsb"
            )
            if field == "attribution_required":
                source["rights"][field] = False
            else:
                source[field] = False
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    with pytest.raises(Gold10ManifestError, match=field):
        build_gold10_manifest()


def test_report_review_status_is_never_an_authority_token() -> None:
    assert _report_task_eligible("pending_artifact_level_review") is False
    assert _report_task_eligible("approved_for_task_use") is False
    assert _report_task_eligible("arbitrary-caller-value") is False


def test_exact_content_bound_authority_controls_report_task_eligibility() -> None:
    manifest = build_gold10_manifest()

    for case in manifest["cases"]:
        report = case["report"]
        assert report["verification_status"] == "verified"
        assert report["artifact_review_status"] == "pending_artifact_level_review"
        assert report["eligible_for_task_evidence"] is True
        assert "artifact_review_status remains non-authoritative" in report["authority_note"]
        authority = report["task_use_authority"]
        assert authority["decision"] == EXPECTED_TASK_USE_DECISION
        assert set(authority["restrictions"]) == EXPECTED_TASK_USE_RESTRICTIONS
        assert authority["authority_id"] == "gold10-report-task-use-v1"
        assert authority["review_scope"] == "internal_task_and_verifier_evidence_only"
        assert report["artifact_id"]
        assert report["canonical_source_url"]
        assert report["acquisition_url"]
        assert isinstance(report["byte_count"], int) and report["byte_count"] > 0
        assert len(report["sha256"]) == 64
        assert len(report["receipt_sha256"]) == 64
        assert len(report["catalog_sha256"]) == 64


def test_mutable_report_review_status_cannot_grant_or_revoke_authority(monkeypatch) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if path.name == "report_acquisition.json":
            value = deepcopy(value)
            for artifact in value["artifacts"]:
                artifact["artifact_review_status"] = "arbitrary_mutable_status"
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    manifest = build_gold10_manifest()
    assert all(
        case["report"]["artifact_review_status"] == "arbitrary_mutable_status"
        and case["report"]["eligible_for_task_evidence"] is True
        for case in manifest["cases"]
    )


@pytest.mark.parametrize(
    "field",
    [
        "artifact_id",
        "source_url",
        "resolved_url",
        "byte_count",
        "sha256",
        "receipt_sha256",
        "catalog_sha256",
    ],
)
def test_missing_required_report_authority_field_fails_closed(monkeypatch, field: str) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if path.name == "report_acquisition.json":
            value = deepcopy(value)
            value["artifacts"][0][field] = None
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    with pytest.raises(Gold10ManifestError):
        build_gold10_manifest()


@pytest.mark.parametrize(
    ("field", "bad_value", "message"),
    [
        ("artifact_id", "", "artifact_id"),
        ("source_url", "", "canonical source URL"),
        ("resolved_url", "", "acquisition URL"),
        ("byte_count", 0, "positive integer"),
        ("byte_count", True, "positive integer"),
        ("sha256", "g" * 64, "64-hex SHA-256"),
        ("receipt_sha256", "0" * 63, "64-hex SHA-256"),
        ("catalog_sha256", "A" * 64, "64-hex SHA-256"),
    ],
)
def test_malformed_required_report_authority_field_fails_closed(
    monkeypatch,
    field: str,
    bad_value,
    message: str,
) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if path.name == "report_acquisition.json":
            value = deepcopy(value)
            value["artifacts"][0][field] = bad_value
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    with pytest.raises(Gold10ManifestError, match=message):
        build_gold10_manifest()


@pytest.mark.parametrize("field", ["task_owner_root", "verifier_owner_root"])
@pytest.mark.parametrize(
    "bad_value",
    [
        None,
        "",
        True,
        7,
        "/absolute/owner",
        "../owner",
        "src/investigation_world/gold10/tasks/../verifiers",
        "src\\investigation_world\\gold10\\tasks",
        " src/investigation_world/gold10/tasks",
        "src/investigation_world/gold10/other",
    ],
)
def test_malformed_owner_root_fails_closed(monkeypatch, field: str, bad_value) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if path.name == "case_selection_v1.json":
            value = deepcopy(value)
            value[field] = bad_value
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    with pytest.raises(Gold10ManifestError, match=field):
        build_gold10_manifest()


@pytest.mark.parametrize(
    "bad_value",
    [
        None,
        "causal-reconstruction",
        [],
        ["causal-reconstruction", ""],
        ["causal-reconstruction", 7],
        ["causal-reconstruction", " causal-reconstruction"],
        ["causal-reconstruction", "causal-reconstruction"],
    ],
)
def test_malformed_capability_targets_fail_closed(monkeypatch, bad_value) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if path.name == "index.json":
            value = deepcopy(value)
            value["cases"][0]["capability_tags"] = bad_value
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    with pytest.raises(Gold10ManifestError, match="capability targets"):
        build_gold10_manifest()


def test_gold10_manifest_is_deterministic_and_content_bound() -> None:
    first = build_gold10_manifest()
    second = build_gold10_manifest()

    assert first == second
    assert first["manifest_sha256"] == manifest_digest(first)
    assert all(len(value) == 64 for value in first["selection_inputs"].values())
    assert "task_use_authority_sha256" in first["selection_inputs"]

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

    changed_authority = deepcopy(first)
    changed_authority["cases"][0]["report"]["task_use_authority"]["decision"] = "denied"
    mutations.append(changed_authority)

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
