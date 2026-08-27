from tools.aggregate_training_value_v3 import aggregate_reports
from tools.run_training_value_v3 import _paired_summary, _panel_hash


def _score(ids, values):
    return {
        "episodes": [
            {"episode_id": episode_id, "score": value, "parsed": True}
            for episode_id, value in zip(ids, values, strict=True)
        ]
    }


def test_paired_summary_freezes_panel_and_reports_proportion_improved():
    ids = ["E-1", "E-2", "E-3", "E-4"]
    result = _paired_summary(_score(ids, [0, 0, 0.5, 0.5]), _score(ids, [0.5, 0, 0.5, 0.25]))

    assert result["panel_id"] == _panel_hash(ids)
    assert result["improved"] == 1
    assert result["unchanged"] == 2
    assert result["regressed"] == 1
    assert result["proportion_improved"] == 0.25


def _report(seed: int, deltas: list[float]):
    ids = [f"E-{index}" for index in range(len(deltas))]
    before = _score(ids, [0.0] * len(ids))
    after = _score(ids, deltas)
    paired = _paired_summary(before, after)
    return {
        "model": "Qwen/Qwen2.5-1.5B-Instruct",
        "training_seed": seed,
        "train_panel_id": "PANEL-TRAIN",
        "heldout_panel_id": paired["panel_id"],
        "paired_heldout": paired,
        "train_absolute_improvement": 0.1,
        "heldout_absolute_improvement": paired["mean_delta"],
    }


def test_seed_aggregate_requires_fixed_panels_and_reports_seed_variance():
    aggregate = aggregate_reports([
        _report(7, [0.1, 0.0, 0.2]),
        _report(17, [0.0, 0.1, 0.2]),
        _report(29, [0.1, 0.1, 0.0]),
    ])

    assert aggregate["training_seeds"] == [7, 17, 29]
    assert aggregate["model"] == "Qwen/Qwen2.5-1.5B-Instruct"
    assert aggregate["heldout_examples"] == 3
    assert aggregate["seed_level_mean_delta"]["n"] == 3
    assert aggregate["seed_variance_of_mean_delta"] >= 0
    assert len(aggregate["per_episode"]) == 3
