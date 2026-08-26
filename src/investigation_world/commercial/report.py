from __future__ import annotations

from collections.abc import Iterable
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
    if reference <= empty:
        return 0.0
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
        return float(report[section][level]["mean"])
    except (KeyError, TypeError, ValueError):
        return 0.0


def _normalized_levels(report: dict[str, Any]) -> dict[str, float]:
    values: dict[str, float] = {}
    for level in LEVELS:
        values[level] = normalize_capability_score(
            _mean_value(report, "model_scores", level),
            _mean_value(report, "empty_anchors", level),
            _mean_value(report, "reference_anchors", level),
        )
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
        "Veritas measures whether an agent can move from evidence-grounded investigation to authorized action, long-horizon control, and concurrent enterprise operations. Scores below are normalized between the no-work baseline (0.0) and the benchmark public-reference policy (1.0) for each capability level.",
        "",
        "| Model | Investigation | Action | Sequential | Dynamic | Overall | Band | Parse failures |",
        "| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: |",
    ]

    summaries: list[tuple[str, dict[str, float], float, int]] = []
    for report in rows:
        model = str(report.get("model", "unknown-model"))
        normalized = _normalized_levels(report)
        overall = mean(normalized.values())
        parse_failures = sum(int(value or 0) for value in report.get("parse_failures", {}).values())
        summaries.append((model, normalized, overall, parse_failures))
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

    best_model, best_levels, best_overall, _ = max(summaries, key=lambda item: item[2])
    strongest_level = max(best_levels, key=best_levels.get)
    weakest_level = min(best_levels, key=best_levels.get)

    lines.extend(
        [
            "",
            "## Findings",
            "",
            f"- Highest overall result: **{best_model}** at **{best_overall:.3f}** normalized capability.",
            f"- Strongest measured capability for that system: **{LEVEL_LABELS[strongest_level]}** ({best_levels[strongest_level]:.3f}).",
            f"- Weakest measured capability: **{LEVEL_LABELS[weakest_level]}** ({best_levels[weakest_level]:.3f}).",
            "- A score near 0 means behavior is close to the no-work baseline; a score near 1 means behavior approaches the benchmark's independently validated public-reference policy.",
            "",
            "## Capability interpretation",
            "",
            "| Level | What is measured |",
            "| --- | --- |",
            "| Investigation | Evidence synthesis, factual reconstruction, citation discipline and calibration. |",
            "| Operational Action | Correct action selection, authority compliance and resulting state transition. |",
            "| Sequential Control | Prerequisites, approvals, delayed effects, reconciliation, verification and closure. |",
            "| Dynamic Portfolio Control | Concurrent cases, stochastic outcomes, resource contention, deadlines, failures and handoffs. |",
            "",
            "## Methodology and caveats",
            "",
            "- Customer/model outputs are scored by the Veritas verifier, not by the model that produced the answer.",
            "- Public-reference and no-work anchors are generated from the same benchmark build used for the evaluated model.",
            "- Full-context calibration is a planning baseline. It does not by itself measure a production tool-using agent harness unless the supplied system is evaluated through that harness.",
            "- Small calibration slices are directional; procurement decisions should use a larger private stratified evaluation with repeated attempts and confidence intervals.",
            "",
            "## Recommended next evaluation",
            "",
            "Run a private stratified evaluation across all CompanyWorld task families with the customer's actual agent harness, fixed tool/token budgets, repeated attempts, and trajectory capture. Report capability by family, cost, evidence quality, authority compliance, recovery behavior and failure mode.",
        ]
    )
    return "\n".join(lines) + "\n"
