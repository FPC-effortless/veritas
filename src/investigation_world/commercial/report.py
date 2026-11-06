from __future__ import annotations

from collections.abc import Iterable
from math import isfinite
from statistics import mean
from typing import Any

LEVELS = ("diagnostic", "interactive", "sequential", "dynamic")
LEVEL_LABELS = {
    "diagnostic": "Investigation",
    "interactive": "Operational Action",
    "sequential": "Sequential Control",
    "dynamic": "Dynamic Portfolio Control",
}


def normalize_capability_score(score: float, empty: float, reference: float) -> float:
    if not all(isfinite(value) for value in (score, empty, reference)):
        raise ValueError("score and calibration anchors must be finite numbers")
    if reference <= empty:
        raise ValueError("reference anchor must be greater than the empty anchor")
    return max(0.0, min(1.0, (score - empty) / (reference - empty)))


def _band(score: float) -> str:
    if score < 0.10:
        return "Floor"
    if score < 0.35:
        return "Emerging"
    if score < 0.65:
        return "Developing"
    if score < 0.85:
        return "Strong"
    return "Near-reference"


def _mean_value(report: dict[str, Any], section: str, level: str) -> float:
    try:
        value = float(report[section][level]["mean"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"missing or invalid {section}.{level}.mean") from exc
    if not isfinite(value):
        raise ValueError(f"{section}.{level}.mean must be finite")
    return value


def _calibrated_levels(report: dict[str, Any]) -> dict[str, dict[str, float]]:
    values: dict[str, dict[str, float]] = {}
    for level in LEVELS:
        raw = _mean_value(report, "model_scores", level)
        empty = _mean_value(report, "empty_anchors", level)
        reference = _mean_value(report, "reference_anchors", level)
        if not 0.0 <= empty < reference <= 1.0:
            raise ValueError(
                f"{level} anchors must satisfy 0 <= empty < reference <= 1"
            )
        if not 0.0 <= raw <= 1.0:
            raise ValueError(f"model_scores.{level}.mean must be between 0 and 1")
        values[level] = {
            "raw_reward": raw,
            "empty_anchor_mean": empty,
            "reference_anchor_mean": reference,
            "net_reward": raw - empty,
            "normalized_reward": normalize_capability_score(raw, empty, reference),
        }
    return values


def build_customer_report(
    reports: Iterable[dict[str, Any]],
    *,
    title: str = "Veritas Enterprise Agent Evaluation",
    customer_name: str | None = None,
    benchmark_version: str = "CompanyWorld",
) -> str:
    rows = list(reports)
    if not rows:
        raise ValueError("at least one calibration report is required")

    heading = title if not customer_name else f"{title} — {customer_name}"
    lines = [
        f"# {heading}",
        "",
        f"Benchmark: **{benchmark_version}**",
        "",
        "## Executive summary",
        "",
        "Veritas measures evidence-grounded investigation, authorized action, "
        "long-horizon control, "
        "and concurrent enterprise operations. Buyer comparisons use reward above each level's "
        "measured no-work baseline, normalized to the public-reference policy. Raw reward is "
        "diagnostic only and must not be compared across levels.",
        "",
        "| Model | Investigation | Action | Sequential | Dynamic | Overall | Band | Parse fails |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]

    summaries: list[tuple[str, dict[str, dict[str, float]], float, int]] = []
    for report in rows:
        model = str(report.get("model", "unknown-model"))
        calibrated = _calibrated_levels(report)
        normalized = {level: values["normalized_reward"] for level, values in calibrated.items()}
        overall = mean(normalized.values())
        parse_failures = sum(int(value or 0) for value in report.get("parse_failures", {}).values())
        summaries.append((model, calibrated, overall, parse_failures))
        lines.append(
            "| "
            + " | ".join(
                [
                    model,
                    f"{normalized['diagnostic']:.3f}",
                    f"{normalized['interactive']:.3f}",
                    f"{normalized['sequential']:.3f}",
                    f"{normalized['dynamic']:.3f}",
                    f"{overall:.3f}",
                    _band(overall),
                    str(parse_failures),
                ]
            )
            + " |"
        )

    best_model, best_calibrated, best_overall, _ = max(summaries, key=lambda item: item[2])
    best_levels = {level: values["normalized_reward"] for level, values in best_calibrated.items()}
    strongest_level = max(best_levels, key=best_levels.get)
    weakest_level = min(best_levels, key=best_levels.get)

    lines.extend(
        [
            "",
            "## Findings",
            "",
            f"- Highest overall result: **{best_model}** at "
            f"**{best_overall:.3f}** normalized capability.",
            f"- Strongest measured capability: **{LEVEL_LABELS[strongest_level]}** "
            f"({best_levels[strongest_level]:.3f}).",
            f"- Weakest measured capability: **{LEVEL_LABELS[weakest_level]}** "
            f"({best_levels[weakest_level]:.3f}).",
            "- Normalized 0 means no gain over that level's no-work behavior; 1 approaches the "
            "independently validated public-reference policy.",
            "- Net reward = `model_mean - empty_anchor_mean`. Normalized reward = "
            "`net_reward / (reference_anchor_mean - empty_anchor_mean)`, clipped to [0, 1].",
            "- Raw reward is diagnostic only. Do not compare levels by raw reward; verifier "
            "components and intentional no-work offsets differ.",
            "",
            "## Per-level calibration",
            "",
            "| Model | Level | Raw diagnostic | Empty | Reference | Net | Normalized |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            *[
                f"| {model} | {LEVEL_LABELS[level]} | {values['raw_reward']:.3f} | "
                f"{values['empty_anchor_mean']:.3f} | {values['reference_anchor_mean']:.3f} | "
                f"{values['net_reward']:.3f} | {values['normalized_reward']:.3f} |"
                for model, calibrated_levels, _, _ in summaries
                for level, values in calibrated_levels.items()
            ],
            "",
            "## Capability interpretation",
            "",
            "| Level | What is measured |",
            "| --- | --- |",
            "| Investigation | Evidence synthesis, factual reconstruction, citation discipline. |",
            "| Operational Action | Action selection, authority compliance, state transition. |",
            "| Sequential Control | Prerequisites, approvals, delays, reconciliation, closure. |",
            "| Dynamic | Concurrent work, contention, deadlines, failures, handoffs. |",
            "",
            "## Methodology and caveats",
            "",
            "- The Veritas verifier scores customer/model outputs independently.",
            "- Public-reference and no-work anchors use the evaluated model's benchmark build.",
            "- Full-context calibration is a planning baseline; it does not measure a production "
            "tool-using harness unless the supplied system is evaluated through that harness.",
            "- Small calibration slices are directional. Procurement decisions should use a "
            "larger private stratified evaluation with repeated attempts and confidence intervals.",
            "",
            "## Recommended next evaluation",
            "",
            "Run a private stratified evaluation across CompanyWorld task families with the "
            "customer's actual harness, fixed tool/token budgets, repeated attempts, "
            "and trajectory "
            "capture. Report capability by family, cost, evidence quality, authority compliance, "
            "recovery behavior, and failure mode.",
        ]
    )
    return "\n".join(lines) + "\n"
