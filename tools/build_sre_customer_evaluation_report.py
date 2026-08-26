from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{100.0 * value:.1f}%"


def render_report(evaluation: dict[str, Any], customer_name: str, qualification: dict[str, Any] | None = None) -> str:
    lines = [
        f"# Veritas SRE Evaluation — {customer_name}",
        "",
        "## Evaluation identity",
        "",
        f"- Benchmark version: `{evaluation['benchmark_version']}`",
        f"- Candidate: `{evaluation['candidate_id']}`",
        f"- Private panel: `{evaluation['panel_id']}`",
        f"- Evidence manifest: `{evaluation.get('evidence_manifest_id', 'not-recorded')}`",
        f"- Evaluated model/harness: `{evaluation['model']}`",
        f"- Private cases: **{evaluation['private_cases']}**",
        "",
        "## Result",
        "",
        f"- Accuracy: **{_pct(float(evaluation['accuracy']))}**",
        f"- 95% Wilson interval: **{_pct(float(evaluation['ci95_low']))} – {_pct(float(evaluation['ci95_high']))}**",
        f"- Structured-output parse failures: **{evaluation['parse_failures']} / {evaluation['private_cases']}** ({_pct(float(evaluation['parse_failure_rate']))})",
        "",
        "The evaluated system received early incident evidence only. Later resolution notes and evaluator-only causal labels were not included in model prompts.",
        "",
        "## Capability by causal class",
        "",
        "| Causal class | Cases | Accuracy | 95% interval |",
        "|---|---:|---:|---:|",
    ]
    for label, metrics in evaluation.get("per_class", {}).items():
        if metrics["n"]:
            interval = f"{_pct(metrics['ci95_low'])} – {_pct(metrics['ci95_high'])}"
        else:
            interval = "n/a"
        lines.append(f"| {label} | {metrics['n']} | {_pct(metrics['accuracy'])} | {interval} |")

    if qualification:
        q = qualification.get("qualification", qualification)
        policy_means = q.get("policy_means", {})
        lines.extend([
            "",
            "## Benchmark calibration anchors",
            "",
            "These anchors are benchmark policies, not customer-model claims.",
            "",
            "| Policy | Mean reward |",
            "|---|---:|",
        ])
        for name in ("oracle", "competent_heuristic", "myopic", "random", "exploit"):
            if name in policy_means:
                lines.append(f"| {name} | {_pct(float(policy_means[name]))} |")

    lines.extend([
        "",
        "## Interpretation boundary",
        "",
        "This report measures performance on the identified frozen Veritas SRE panel. It does not establish production reliability for every incident distribution, and it should not be compared with scores from a different candidate or panel ID as though they were the same experiment.",
        "",
        "The private case-level oracle is intentionally omitted from this buyer-facing report. Case-level diagnostic disclosure, when contractually requested, should be treated as benchmark-consuming information and the disclosed cases should be retired from future private scoring.",
        "",
        "## Recommended next decision",
        "",
        "Use this result to choose a model/harness, diagnose a capability gap, or define a controlled re-evaluation after a model, prompt, tool, or training change. Re-evaluations should use either the same undisclosed panel for strict regression testing or a newly qualified private panel if case-level truth has been disclosed.",
        "",
    ])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a buyer-safe Veritas SRE evaluation report")
    parser.add_argument("evaluation", type=Path)
    parser.add_argument("--customer-name", required=True)
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    evaluation = json.loads(args.evaluation.read_text(encoding="utf-8"))
    qualification = json.loads(args.qualification.read_text(encoding="utf-8")) if args.qualification else None
    rendered = render_report(evaluation, args.customer_name, qualification)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
