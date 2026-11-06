from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import mean, median, stdev
from typing import Any


def _estimate(values: list[float]) -> dict[str, float | int]:
    from investigation_world.observatory.aggregation import critical_95

    n = len(values)
    center = mean(values) if values else 0.0
    deviation = stdev(values) if n > 1 else 0.0
    error = deviation / math.sqrt(n) if n > 1 else 0.0
    margin = critical_95(n) * error
    return {
        "n": n,
        "mean": round(center, 6),
        "median": round(median(values), 6) if values else 0.0,
        "stddev": round(deviation, 6),
        "standard_error": round(error, 6),
        "ci95_low": round(center - margin, 6),
        "ci95_high": round(center + margin, 6),
    }


def aggregate_reports(reports: list[dict[str, Any]]) -> dict[str, Any]:
    if len(reports) < 3:
        raise ValueError("Training Value v3 aggregate requires at least three independent training seeds")
    models = {str(item["model"]) for item in reports}
    train_panels = {str(item["train_panel_id"]) for item in reports}
    heldout_panels = {str(item["heldout_panel_id"]) for item in reports}
    seeds = [int(item["training_seed"]) for item in reports]
    if len(models) != 1:
        raise ValueError("aggregate reports must use one model")
    if len(train_panels) != 1 or len(heldout_panels) != 1:
        raise ValueError("aggregate reports must use fixed train and held-out panels")
    if len(seeds) != len(set(seeds)):
        raise ValueError("training seeds must be unique")

    mean_deltas = [float(item["paired_heldout"]["mean_delta"]) for item in reports]
    medians = [float(item["paired_heldout"]["median_delta"]) for item in reports]
    proportions = [float(item["paired_heldout"]["proportion_improved"]) for item in reports]
    train_gains = [float(item["train_absolute_improvement"]) for item in reports]
    heldout_gains = [float(item["heldout_absolute_improvement"]) for item in reports]

    episode_ids = [str(item["episode_id"]) for item in reports[0]["paired_heldout"]["episode_deltas"]]
    per_seed_delta = {
        int(report["training_seed"]): {
            str(item["episode_id"]): float(item["delta"])
            for item in report["paired_heldout"]["episode_deltas"]
        }
        for report in reports
    }
    if any(set(values) != set(episode_ids) for values in per_seed_delta.values()):
        raise ValueError("per-episode held-out panels differ across training seeds")
    per_episode = []
    for episode_id in episode_ids:
        values = [per_seed_delta[seed][episode_id] for seed in sorted(per_seed_delta)]
        per_episode.append({
            "episode_id": episode_id,
            "delta_by_training_seed": {seed: per_seed_delta[seed][episode_id] for seed in sorted(per_seed_delta)},
            "mean_delta": round(mean(values), 6),
            "median_delta": round(median(values), 6),
            "improved_seed_fraction": round(sum(value > 0 for value in values) / len(values), 6),
        })

    return {
        "schema_version": "0.3.1",
        "experiment": "diagnostic_lora_sft_hardened_replicated_transfer",
        "model": next(iter(models)),
        "training_seeds": sorted(seeds),
        "train_panel_id": next(iter(train_panels)),
        "heldout_panel_id": next(iter(heldout_panels)),
        "heldout_examples": len(episode_ids),
        "seed_level_mean_delta": _estimate(mean_deltas),
        "seed_level_median_delta": _estimate(medians),
        "seed_level_proportion_improved": _estimate(proportions),
        "seed_level_train_gain": _estimate(train_gains),
        "seed_level_heldout_gain": _estimate(heldout_gains),
        "seed_variance_of_mean_delta": round(stdev(mean_deltas) ** 2, 8) if len(mean_deltas) > 1 else 0.0,
        "per_episode": per_episode,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate independent Training Value v3 seed reports")
    parser.add_argument("--input", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in args.input]
    aggregate = aggregate_reports(reports)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(aggregate, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(aggregate, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
