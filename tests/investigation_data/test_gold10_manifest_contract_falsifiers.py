from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest

import investigation_world.investigation_data.gold10_manifest as gold10_manifest
from investigation_world.investigation_data.gold10_manifest import (
    EXPECTED_CONTAMINATION_POLICY,
    EXPECTED_DATE_ONLY_RELEASE_POLICY,
    EXPECTED_TRUTH_POLICY,
    Gold10ManifestError,
    build_gold10_manifest,
)


def _with_corruption(monkeypatch, predicate, mutate) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        if predicate(path):
            value = deepcopy(value)
            mutate(value)
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("truth_policy", None),
        ("truth_policy", "other_truth_policy"),
        ("contamination_policy", None),
        ("contamination_policy", "sealed_private"),
    ],
)
def test_declared_freeze_policies_fail_closed(monkeypatch, field: str, bad_value) -> None:
    _with_corruption(
        monkeypatch,
        lambda path: path.name == "case_selection_v1.json",
        lambda value: value.__setitem__(field, bad_value),
    )
    with pytest.raises(Gold10ManifestError, match=field):
        build_gold10_manifest()


@pytest.mark.parametrize("bad_value", [None, "", "same_day", "next_day_00z"])
def test_date_only_release_policy_fails_closed(monkeypatch, bad_value) -> None:
    _with_corruption(
        monkeypatch,
        lambda path: path.name == "index.json",
        lambda value: value.__setitem__("date_only_availability_policy", bad_value),
    )
    with pytest.raises(Gold10ManifestError, match="date_only_availability_policy"):
        build_gold10_manifest()


@pytest.mark.parametrize("bad_value", [None, "false", 0, 1, {}, []])
def test_calibration_flag_requires_json_boolean(monkeypatch, bad_value) -> None:
    def mutate(value):
        value["cases"][0]["calibration_required"] = bad_value

    _with_corruption(
        monkeypatch,
        lambda path: path.name == "case_selection_v1.json",
        mutate,
    )
    with pytest.raises(Gold10ManifestError, match="calibration_required"):
        build_gold10_manifest()


@pytest.mark.parametrize(
    "bad_slug",
    [
        "../escape",
        "safe/escape",
        "safe\\escape",
        "..",
        ".",
        " leading",
        "trailing ",
        "slug.py",
        "slug:alt",
    ],
)
def test_slug_cannot_escape_frozen_owner_roots(monkeypatch, bad_slug: str) -> None:
    def mutate(value):
        value["cases"][0]["slug"] = bad_slug

    _with_corruption(monkeypatch, lambda path: path.name == "index.json", mutate)
    with pytest.raises(Gold10ManifestError, match="canonical slug"):
        build_gold10_manifest()


@pytest.mark.parametrize(
    "bad_start",
    [
        None,
        "",
        "not-a-timestamp",
        "2005-03-23T12:00:00",
        "2099-01-01T00:00:00Z",
    ],
)
def test_simulation_start_is_validated_and_ordered(monkeypatch, bad_start) -> None:
    def mutate(value):
        value["simulation_start"] = bad_start

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError, match="simulation_start"):
        build_gold10_manifest()


@pytest.mark.parametrize(
    "bad_pilot_dir",
    [None, "", "../escape", "safe/escape", "safe\\escape", ".", "..", " pilot"],
)
def test_pilot_directory_cannot_escape_canonical_pilot_root(
    monkeypatch,
    bad_pilot_dir,
) -> None:
    def mutate(value):
        value["pilots"][0]["pilot_dir"] = bad_pilot_dir

    _with_corruption(
        monkeypatch,
        lambda path: path.name == "pilot_coverage.json",
        mutate,
    )
    with pytest.raises(Gold10ManifestError, match="pilot_dir"):
        build_gold10_manifest()


@pytest.mark.parametrize(
    "bad_case_ids",
    [
        None,
        [],
        ["CSB-2005-04-I-TX", "CSB-2012-03-I-CA"],
        ["CSB-2012-03-I-CA"],
    ],
)
def test_pilot_source_case_identity_is_exact_and_case_disjoint(
    monkeypatch,
    bad_case_ids,
) -> None:
    def mutate(value):
        value["source_case_ids"] = bad_case_ids

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError, match="source_case_ids"):
        build_gold10_manifest()


@pytest.mark.parametrize("bad_truth", [None, {}, ["private-claim"]])
def test_private_truth_absence_must_be_explicit(monkeypatch, bad_truth) -> None:
    def mutate(value):
        value["ground_truth_claims"] = bad_truth

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError, match="zero private ground-truth"):
        build_gold10_manifest()


@pytest.mark.parametrize("bad_review_id", [None, "", " review-id"])
def test_pilot_review_id_must_be_explicit(monkeypatch, bad_review_id) -> None:
    def mutate(value):
        value["review_id"] = bad_review_id

    _with_corruption(
        monkeypatch,
        lambda path: path.name == "review_record.json",
        mutate,
    )
    with pytest.raises(Gold10ManifestError, match="review_id"):
        build_gold10_manifest()


def test_public_fragment_must_match_selected_source(monkeypatch) -> None:
    def mutate(value):
        value["fragments"][0]["source_id"] = "foreign-source"

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError, match="source mismatch"):
        build_gold10_manifest()


@pytest.mark.parametrize(
    "bad_case_ids",
    [
        [],
        ["CSB-2005-04-I-TX", "CSB-2012-03-I-CA"],
        ["CSB-2012-03-I-CA"],
    ],
)
def test_public_fragment_cannot_cross_case_boundary(monkeypatch, bad_case_ids) -> None:
    def mutate(value):
        value["fragments"][0]["case_ids"] = bad_case_ids

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError, match="case_ids"):
        build_gold10_manifest()


@pytest.mark.parametrize("field", ["rights_review_id", "locator", "content_ref"])
def test_public_fragment_must_be_bound_to_exact_link_only_review(
    monkeypatch,
    field: str,
) -> None:
    def mutate(value):
        value["fragments"][0][field] = None

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError):
        build_gold10_manifest()


def test_unreviewed_foreign_public_fragment_cannot_expand_modalities(monkeypatch) -> None:
    def mutate(value):
        expected_case = value["source_case_ids"][0]
        value["fragments"].append(
            {
                "fragment_id": "foreign-unreviewed-audio",
                "source_id": "foreign-source",
                "case_ids": [expected_case],
                "modality": "audio",
                "sensitivity": "public",
                "locator": "https://example.invalid/audio",
                "content_ref": "external-page://foreign/audio",
                "timeless": True,
                "rights_review_id": "unrelated-review",
            }
        )

    _with_corruption(monkeypatch, lambda path: path.name == "manifest.json", mutate)
    with pytest.raises(Gold10ManifestError, match="source mismatch"):
        build_gold10_manifest()


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("contains_personal_data", None),
        ("contains_personal_data", "false"),
        ("requires_redaction_review", None),
        ("requires_redaction_review", "true"),
    ],
)
def test_source_privacy_and_redaction_flags_require_json_booleans(
    monkeypatch,
    field: str,
    bad_value,
) -> None:
    def mutate(value):
        source = next(item for item in value["sources"] if item["source_id"] == "uscsb")
        source[field] = bad_value

    _with_corruption(
        monkeypatch,
        lambda path: path.name == "source_catalog.json",
        mutate,
    )
    with pytest.raises(Gold10ManifestError, match=field):
        build_gold10_manifest()


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("official_findings_are_ground_truth", True),
        ("official_findings_are_ground_truth", "false"),
        ("verifier_use", None),
        ("verifier_use", "private_truth"),
    ],
)
def test_source_truth_boundary_fails_closed(monkeypatch, field: str, bad_value) -> None:
    def mutate(value):
        source = next(item for item in value["sources"] if item["source_id"] == "uscsb")
        source["truth"][field] = bad_value

    _with_corruption(
        monkeypatch,
        lambda path: path.name == "source_catalog.json",
        mutate,
    )
    with pytest.raises(Gold10ManifestError, match="truth"):
        build_gold10_manifest()


@pytest.mark.parametrize("field", ["acquisition", "redistribution", "ai_use"])
def test_missing_policy_field_cannot_pass_by_null_equality(monkeypatch, field: str) -> None:
    original_read_json = gold10_manifest._read_json

    def corrupted_read_json(path):
        value, digest = original_read_json(path)
        value = deepcopy(value)
        if path.name == "source_catalog.json":
            source = next(
                item for item in value["sources"] if item["source_id"] == "uscsb"
            )
            source["rights"][field] = None
        elif path.name == "report_acquisition.json":
            value["policy"][field] = None
        return value, digest

    monkeypatch.setattr(gold10_manifest, "_read_json", corrupted_read_json)
    with pytest.raises(Gold10ManifestError, match=field):
        build_gold10_manifest()


def test_frozen_policies_and_temporal_order_are_emitted_from_validated_inputs() -> None:
    manifest = build_gold10_manifest()
    assert manifest["truth_policy"] == EXPECTED_TRUTH_POLICY
    assert manifest["contamination_policy"] == EXPECTED_CONTAMINATION_POLICY

    for case in manifest["cases"]:
        cut = case["public_temporal_cut"]
        assert cut["date_only_release_policy"] == EXPECTED_DATE_ONLY_RELEASE_POLICY
        start = datetime.fromisoformat(cut["simulation_start"].replace("Z", "+00:00"))
        as_of = datetime.fromisoformat(cut["simulation_as_of"].replace("Z", "+00:00"))
        assert start <= as_of
        assert isinstance(case["calibration_required"], bool)
        assert "/" not in case["slug"]
        assert "\\" not in case["slug"]
        assert case["pilot_review_id"]
        assert case["rights"]["contains_personal_data"] is True
        assert case["rights"]["requires_redaction_review"] is True
        assert case["rights"]["truth"]["official_findings_are_ground_truth"] is False
