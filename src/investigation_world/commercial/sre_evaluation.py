from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from typing import Any, Callable

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification import QualificationSplit, SRECausalClass, SREQualificationCase

GenerateFn = Callable[[str], str]

_ALLOWED = tuple(item.value for item in SRECausalClass)


def build_sre_prompt(public_text: str) -> str:
    return (
        "You are evaluating an active service incident from early public evidence only. "
        "Classify the most likely causal class. Do not assume access to later resolution notes.\n\n"
        "Allowed causal_class values: regression, infrastructure, capacity, transient.\n"
        "Return JSON only in the form {\"causal_class\": \"...\"}.\n\n"
        f"EARLY INCIDENT EVIDENCE:\n{public_text}"
    )


def parse_sre_prediction(raw: str) -> SRECausalClass | None:
    text = raw.strip()
    payload: dict[str, Any] | None = None
    try:
        candidate = json.loads(text)
        if isinstance(candidate, dict):
            payload = candidate
    except json.JSONDecodeError:
        left = text.find("{")
        right = text.rfind("}")
        if left >= 0 and right > left:
            try:
                candidate = json.loads(text[left : right + 1])
                if isinstance(candidate, dict):
                    payload = candidate
            except json.JSONDecodeError:
                pass
    value = str(payload.get("causal_class", "")).strip().casefold() if payload else text.casefold()
    normalized = value.strip("\"'` .")
    for label in _ALLOWED:
        if value == label or normalized == label:
            return SRECausalClass(label)
    return None


def _wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1.0 + z * z / total
    center = (p + z * z / (2.0 * total)) / denom
    radius = z * math.sqrt((p * (1.0 - p) / total) + (z * z / (4.0 * total * total))) / denom
    return max(0.0, center - radius), min(1.0, center + radius)


def evaluate_sre_generator(
    cases: list[SREQualificationCase],
    generate: GenerateFn,
    *,
    model_name: str,
    candidate_id: str,
    benchmark_version: str,
) -> dict[str, Any]:
    private_cases = [case for case in cases if case.scenario.split == QualificationSplit.PRIVATE_TEST]
    if not private_cases:
        raise ValueError("SRE model evaluation requires at least one private-test case")

    scenario_ids = sorted(case.scenario.scenario_id for case in private_cases)
    panel_id = "SRE-PANEL-" + stable_hash(scenario_ids)[:24].upper()
    rows: list[dict[str, Any]] = []
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    parse_failures = 0
    correct = 0

    for case in sorted(private_cases, key=lambda item: item.scenario.scenario_id):
        prompt = build_sre_prompt(case.public_text)
        raw = generate(prompt)
        prediction = parse_sre_prediction(raw)
        if prediction is None:
            parse_failures += 1
            passed = False
            predicted_value = "parse_failure"
        else:
            predicted_value = prediction.value
            passed = prediction == case.causal_class
            confusion[case.causal_class.value][predicted_value] += 1
        correct += int(passed)
        rows.append(
            {
                "scenario_id": case.scenario.scenario_id,
                "provider": case.provider,
                "expected": case.causal_class.value,
                "prediction": predicted_value,
                "correct": passed,
            }
        )

    n = len(rows)
    accuracy = correct / n
    ci_low, ci_high = _wilson_interval(correct, n)
    per_class: dict[str, Any] = {}
    for label in _ALLOWED:
        relevant = [row for row in rows if row["expected"] == label]
        class_correct = sum(bool(row["correct"]) for row in relevant)
        low, high = _wilson_interval(class_correct, len(relevant))
        per_class[label] = {
            "n": len(relevant),
            "correct": class_correct,
            "accuracy": round(class_correct / len(relevant), 6) if relevant else None,
            "ci95_low": round(low, 6) if relevant else None,
            "ci95_high": round(high, 6) if relevant else None,
        }

    return {
        "schema_version": "1.0.0",
        "evaluation": "veritas-sre-private-causal-classification",
        "benchmark_version": benchmark_version,
        "candidate_id": candidate_id,
        "panel_id": panel_id,
        "model": model_name,
        "private_cases": n,
        "correct": correct,
        "accuracy": round(accuracy, 6),
        "ci95_low": round(ci_low, 6),
        "ci95_high": round(ci_high, 6),
        "parse_failures": parse_failures,
        "parse_failure_rate": round(parse_failures / n, 6),
        "per_class": per_class,
        "confusion": {expected: dict(predicted) for expected, predicted in sorted(confusion.items())},
        "cases": rows,
        "prompt_contract": {
            "input": "early public incident evidence only",
            "private_resolution_notes_exposed": False,
            "private_causal_label_exposed": False,
            "allowed_labels": list(_ALLOWED),
        },
    }
