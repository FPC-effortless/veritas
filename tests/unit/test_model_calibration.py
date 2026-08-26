from __future__ import annotations

from investigation_world.calibration import (
    empty_anchors,
    reference_anchors,
    run_full_context_calibration,
)
from investigation_world.calibration.fixtures import dynamic_fixture, sequential_fixture


def test_reference_anchors_are_perfect():
    anchors = reference_anchors()
    assert set(anchors) == {"diagnostic", "interactive", "sequential", "dynamic"}
    assert all(level["min"] == 1.0 for level in anchors.values())


def test_empty_anchors_are_strictly_below_reference():
    empty = empty_anchors()
    assert empty["diagnostic"]["max"] == 0.0
    assert empty["interactive"]["max"] < 0.5
    assert empty["sequential"]["max"] <= 0.25
    assert empty["dynamic"]["max"] < 0.5


def test_invalid_model_output_is_recorded_without_crashing():
    report = run_full_context_calibration(lambda _: "not-json", model_name="invalid-model")
    assert report["model"] == "invalid-model"
    assert report["parse_failures"] == {
        "diagnostic": 3,
        "interactive": 3,
        "sequential": 3,
        "dynamic": 1,
    }
    assert report["model_scores"]["diagnostic"]["max"] == 0.0


def test_calibration_slice_contains_delegated_control_and_dynamic_contention():
    sequential = sequential_fixture()
    assert len(sequential) == 3
    assert any(item.oracle.approval_required for item in sequential)
    scenario = dynamic_fixture()
    assert len(scenario.cases) == 3
    assert len({item.shared_resource for item in scenario.cases}) == 1
    assert scenario.task.shared_resource_capacities[scenario.cases[0].shared_resource] == 1
