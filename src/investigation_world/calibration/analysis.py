from __future__ import annotations

from collections.abc import Mapping
from typing import Any


LEVELS = ("diagnostic", "interactive", "sequential", "dynamic")


def baseline_adjusted_model_scores(
    report: Mapping[str, Any],
    *,
    empty: Mapping[str, Mapping[str, float]] | None = None,
    reference: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, dict[str, float | None]]:
    """Return level-wise model reward relative to no-work and reference anchors.

    Raw rewards from different CompanyWorld runtime levels are not directly
    comparable because the no-work policy can receive different partial-credit
    baselines. This helper preserves the raw score while exposing two derived
    quantities:

    ``net_reward``
        model mean minus the level-specific no-work mean.

    ``normalized_reward``
        position between no-work (0.0) and deterministic public reference (1.0).
        Values may be negative when the model does worse than no work and may
        exceed 1.0 if a future scoring surface allows it.
    """
    if empty is None or reference is None:
        # Local import avoids an import cycle through calibration.__init__.
        from investigation_world.calibration.full_context import empty_anchors, reference_anchors

        empty = empty or empty_anchors()
        reference = reference or reference_anchors()

    model_scores = report.get("model_scores")
    if not isinstance(model_scores, Mapping):
        raise ValueError("calibration report is missing model_scores")

    adjusted: dict[str, dict[str, float | None]] = {}
    for level in LEVELS:
        level_scores = model_scores.get(level)
        if not isinstance(level_scores, Mapping) or "mean" not in level_scores:
            raise ValueError(f"calibration report is missing model_scores.{level}.mean")
        if level not in empty or level not in reference:
            raise ValueError(f"missing anchors for calibration level {level!r}")

        raw = float(level_scores["mean"])
        empty_mean = float(empty[level]["mean"])
        reference_mean = float(reference[level]["mean"])
        net = raw - empty_mean
        denominator = reference_mean - empty_mean
        normalized = None if denominator == 0 else net / denominator

        adjusted[level] = {
            "raw_mean": round(raw, 6),
            "empty_anchor_mean": round(empty_mean, 6),
            "reference_anchor_mean": round(reference_mean, 6),
            "net_reward": round(net, 6),
            "normalized_reward": None if normalized is None else round(normalized, 6),
        }
    return adjusted


def attach_baseline_adjusted_scores(report: dict[str, Any]) -> dict[str, Any]:
    """Attach baseline-adjusted scores in place and return ``report``."""
    report["baseline_adjusted_scores"] = baseline_adjusted_model_scores(report)
    return report
