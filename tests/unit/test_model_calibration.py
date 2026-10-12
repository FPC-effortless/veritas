from __future__ import annotations

from pathlib import Path

from investigation_world.calibration import (
    empty_anchors,
    reference_anchors,
    run_full_context_calibration,
)
from investigation_world.calibration.fixtures import dynamic_fixture, sequential_fixture
from investigation_world.calibration.full_context import render_calibration_anchor_report


def test_reference_anchors_are_perfect():
    anchors = reference_anchors()
    assert set(anchors) == {"diagnostic", "interactive", "sequential", "dynamic"}
    assert anchors == {
        level: {"mean": 1.0, "min": 1.0, "max": 1.0}
        for level in ("diagnostic", "interactive", "sequential", "dynamic")
    }


def test_empty_anchors_are_strictly_below_reference():
    empty = empty_anchors()
    assert empty == {
        "diagnostic": {"mean": 0.0, "min": 0.0, "max": 0.0},
        "interactive": {"mean": 0.1, "min": 0.1, "max": 0.1},
        "sequential": {"mean": 0.15, "min": 0.15, "max": 0.15},
        "dynamic": {"mean": 0.25, "min": 0.25, "max": 0.25},
    }


def test_committed_anchor_report_is_regenerable_from_fixtures():
    report_path = Path(__file__).parents[2] / "results/companyworld-v0.1/REPORT.md"
    assert report_path.read_text(encoding="utf-8") == render_calibration_anchor_report()


def test_invalid_model_output_is_recorded_without_crashing():
    report = run_full_context_calibration(lambda _: "not-json", model_name="invalid-model")
    assert report["schema_version"] == "0.2.0"
    assert report["model"] == "invalid-model"
    assert report["parse_failures"] == {
        "diagnostic": 3,
        "interactive": 3,
        "sequential": 3,
        "dynamic": 1,
    }
    assert report["model_scores"]["diagnostic"]["max"] == 0.0
    assert set(report["calibration_metrics"]) == {
        "diagnostic",
        "interactive",
        "sequential",
        "dynamic",
    }
    for level, metrics in report["calibration_metrics"].items():
        model_mean = report["model_scores"][level]["mean"]
        empty_mean = report["empty_anchors"][level]["mean"]
        reference_mean = report["reference_anchors"][level]["mean"]
        assert metrics["empty_anchor_mean"] == empty_mean
        assert metrics["reference_anchor_mean"] == reference_mean
        assert metrics["net_reward"] == model_mean - empty_mean
        assert metrics["normalized_reward"] == max(
            0.0,
            min(1.0, (model_mean - empty_mean) / (reference_mean - empty_mean)),
        )


def test_calibration_slice_contains_delegated_control_and_dynamic_contention():
    sequential = sequential_fixture()
    assert len(sequential) == 3
    assert any(item.oracle.approval_required for item in sequential)
    scenario = dynamic_fixture()
    assert len(scenario.cases) == 3
    assert len({item.shared_resource for item in scenario.cases}) == 1
    assert scenario.task.shared_resource_capacities[scenario.cases[0].shared_resource] == 1
