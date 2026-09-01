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
