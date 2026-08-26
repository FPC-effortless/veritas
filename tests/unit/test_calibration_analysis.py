from investigation_world.calibration.analysis import baseline_adjusted_model_scores


def test_baseline_adjusted_scores_preserve_raw_and_subtract_no_work():
    report = {
        "model_scores": {
            "diagnostic": {"mean": 0.0},
            "interactive": {"mean": 0.2},
            "sequential": {"mean": 0.1},
            "dynamic": {"mean": 0.25},
        }
    }
    empty = {
        "diagnostic": {"mean": 0.0},
        "interactive": {"mean": 0.1},
        "sequential": {"mean": 0.15},
        "dynamic": {"mean": 0.25},
    }
    reference = {level: {"mean": 1.0} for level in empty}

    scores = baseline_adjusted_model_scores(report, empty=empty, reference=reference)

    assert scores["interactive"] == {
        "raw_mean": 0.2,
        "empty_anchor_mean": 0.1,
        "reference_anchor_mean": 1.0,
        "net_reward": 0.1,
        "normalized_reward": 0.111111,
    }
    assert scores["sequential"]["net_reward"] == -0.05
    assert scores["sequential"]["normalized_reward"] == -0.058824
    assert scores["dynamic"]["net_reward"] == 0.0
    assert scores["diagnostic"]["normalized_reward"] == 0.0


def test_baseline_adjusted_scores_reject_missing_levels():
    try:
        baseline_adjusted_model_scores(
            {"model_scores": {"diagnostic": {"mean": 0.0}}},
            empty={"diagnostic": {"mean": 0.0}},
            reference={"diagnostic": {"mean": 1.0}},
        )
    except ValueError as exc:
        assert "interactive" in str(exc)
    else:
        raise AssertionError("expected a missing-level validation error")
