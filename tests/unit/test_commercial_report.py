import pytest

from investigation_world.commercial import build_customer_report, normalize_capability_score


def _report(model: str, score: float):
    levels = {
        name: {"mean": score, "min": score, "max": score}
        for name in ("diagnostic", "interactive", "sequential", "dynamic")
    }
    empty = {
        "diagnostic": {"mean": 0.0},
        "interactive": {"mean": 0.1},
        "sequential": {"mean": 0.15},
        "dynamic": {"mean": 0.25},
    }
    reference = {name: {"mean": 1.0} for name in levels}
    return {
        "model": model,
        "model_scores": levels,
        "empty_anchors": empty,
        "reference_anchors": reference,
        "parse_failures": {name: 0 for name in levels},
    }


def test_normalize_capability_score_clips_and_anchors():
    assert normalize_capability_score(0.1, 0.1, 1.0) == 0.0
    assert normalize_capability_score(1.0, 0.1, 1.0) == 1.0
    assert normalize_capability_score(2.0, 0.1, 1.0) == 1.0
    assert normalize_capability_score(-1.0, 0.1, 1.0) == 0.0


def test_normalize_capability_score_rejects_invalid_anchors():
    with pytest.raises(ValueError, match="greater than"):
        normalize_capability_score(0.5, 0.5, 0.5)
    with pytest.raises(ValueError, match="finite"):
        normalize_capability_score(float("nan"), 0.0, 1.0)


def test_customer_report_contains_capability_table_and_caveats():
    rendered = build_customer_report([_report("model-a", 0.5)], customer_name="Example Co")
    assert "Example Co" in rendered
    assert "model-a" in rendered
    assert "Investigation" in rendered
    assert "Dynamic Portfolio Control" in rendered
    assert "private stratified evaluation" in rendered
    assert "Raw reward is diagnostic only" in rendered
    assert "| model-a | Operational Action | 0.500 | 0.100 | 1.000 | 0.400 | 0.444 |" in rendered


def test_customer_report_fails_closed_when_an_anchor_is_missing():
    report = _report("model-a", 0.5)
    del report["empty_anchors"]["dynamic"]
    with pytest.raises(ValueError, match="empty_anchors.dynamic.mean"):
        build_customer_report([report])


def test_customer_report_fails_closed_when_anchor_range_is_invalid():
    report = _report("model-a", 0.5)
    report["reference_anchors"]["dynamic"]["mean"] = 1.1
    with pytest.raises(ValueError, match="dynamic anchors"):
        build_customer_report([report])


def test_customer_report_fails_closed_when_anchor_is_non_finite():
    report = _report("model-a", 0.5)
    report["empty_anchors"]["dynamic"]["mean"] = float("nan")
    with pytest.raises(ValueError, match="must be finite"):
        build_customer_report([report])
