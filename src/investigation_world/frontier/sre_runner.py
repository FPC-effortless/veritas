from __future__ import annotations

import json
from collections import Counter
from typing import Any

from .models import FrontierCalibrationObservation, PairedCapabilityComparison


def build_openai_compatible_body(
    prompt: str,
    *,
    model: str,
    system_instruction: str,
    max_output_tokens: int,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": system_instruction},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": max_output_tokens,
    }


def extract_openai_compatible_text(payload: dict[str, Any]) -> str:
    try:
        return str(payload["choices"][0]["message"]["content"])
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("endpoint is not OpenAI chat-completions compatible") from exc


def build_gemini_generate_content_body(
    prompt: str,
    *,
    system_instruction: str,
    max_output_tokens: int,
    json_output: bool,
) -> dict[str, Any]:
    generation_config: dict[str, Any] = {"maxOutputTokens": max_output_tokens}
    if json_output:
        generation_config["responseMimeType"] = "application/json"
    return {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": generation_config,
    }


def extract_gemini_text(payload: dict[str, Any]) -> str:
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Gemini response does not contain candidate content") from exc
    text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
    if not text:
        raise RuntimeError("Gemini response contains no text")
    return text


def evidence_stage_prompt(original_prompt: str) -> str:
    return (
        "Extract only decision-relevant early incident evidence from the task below. "
        "Do not output a final causal class and do not invent later resolution evidence.\n\n"
        f"{original_prompt}"
    )


def classification_stage_prompt(original_prompt: str, normalized_evidence: str) -> str:
    return (
        f"{original_prompt}\n\n"
        "EVIDENCE NORMALIZATION FROM A SEPARATE FIRST STAGE "
        "(analysis aid only; not ground truth):\n"
        f"{normalized_evidence}"
    )


def failure_mode_counts_from_sre_report(
    report: dict[str, Any],
    *,
    transport_failures: int = 0,
) -> dict[str, int]:
    counts: Counter[str] = Counter()
    confusion = report.get("confusion")
    if isinstance(confusion, dict):
        for expected, predictions in confusion.items():
            if not isinstance(predictions, dict):
                continue
            for predicted, raw_count in predictions.items():
                count = int(raw_count)
                if count <= 0 or predicted == expected:
                    continue
                if predicted == "parse_failure":
                    counts["parser"] += count
                else:
                    counts[f"{expected}->{predicted}"] += count

    if transport_failures:
        parser = counts.get("parser", 0)
        if transport_failures > parser:
            raise ValueError("transport failures cannot exceed parse failures")
        counts["parser"] -= transport_failures
        if counts["parser"] == 0:
            counts.pop("parser", None)
        counts["transport"] += transport_failures
    return dict(sorted(counts.items()))


def observation_from_sre_report(
    report: dict[str, Any],
    *,
    tier: str,
    model_snapshot: str | None,
    harness_identity: str,
    comparison_group_id: str | None = None,
    input_artifact_hash: str | None = None,
    transport_failures: int = 0,
    configuration: dict[str, Any] | None = None,
) -> FrontierCalibrationObservation:
    model = str(report.get("model") or "").strip()
    if not model:
        raise ValueError("SRE report is missing model identity")
    n = int(report["private_cases"])
    correct = int(report["correct"])
    accuracy = float(report["accuracy"])
    if n <= 0 or correct < 0 or correct > n:
        raise ValueError("invalid SRE report counts")
    if abs(accuracy - (correct / n)) > 1e-5:
        raise ValueError("SRE report accuracy disagrees with correct/private_cases")

    runtime = report.get("runtime") if isinstance(report.get("runtime"), dict) else {}
    merged_configuration = {
        "source_evaluation": report.get("evaluation"),
        "runtime_transport": runtime.get("transport"),
        "generation": runtime.get("generation"),
        **(configuration or {}),
    }
    return FrontierCalibrationObservation(
        benchmark_name="SRE",
        benchmark_version=report.get("benchmark_version"),
        candidate_id=report.get("candidate_id"),
        panel_id=report.get("panel_id"),
        qualification_report_id=report.get("qualification_report_id"),
        evidence_manifest_id=report.get("evidence_manifest_id"),
        release_manifest_id=(
            report.get("private_release_manifest_id") or report.get("release_manifest_id")
        ),
        model_identity=model,
        model_snapshot=model_snapshot,
        harness_identity=harness_identity,
        tier=tier,
        metric_name="accuracy",
        score=accuracy,
        sample_size=n,
        successes=correct,
        configuration=merged_configuration,
        comparison_group_id=comparison_group_id,
        failure_mode_counts=failure_mode_counts_from_sre_report(
            report, transport_failures=transport_failures
        ),
        input_artifact_hash=input_artifact_hash,
    )


def paired_comparison_from_private_sre_reports(
    weak_report: dict[str, Any],
    strong_report: dict[str, Any],
    *,
    weak_observation: FrontierCalibrationObservation,
    strong_observation: FrontierCalibrationObservation,
    input_artifact_hashes: dict[str, str] | None = None,
) -> PairedCapabilityComparison:
    weak_rows = weak_report.get("cases")
    strong_rows = strong_report.get("cases")
    if not isinstance(weak_rows, list) or not isinstance(strong_rows, list):
        raise ValueError("paired comparison requires private SRE reports with case rows")

    weak_by_id = {
        str(row["scenario_id"]): row
        for row in weak_rows
        if isinstance(row, dict) and "scenario_id" in row
    }
    strong_by_id = {
        str(row["scenario_id"]): row
        for row in strong_rows
        if isinstance(row, dict) and "scenario_id" in row
    }
    if set(weak_by_id) != set(strong_by_id) or not weak_by_id:
        raise ValueError("weak and strong private reports must contain the same scenario IDs")

    for left, right in (
        (weak_report.get("candidate_id"), strong_report.get("candidate_id")),
        (weak_report.get("panel_id"), strong_report.get("panel_id")),
        (weak_report.get("benchmark_version"), strong_report.get("benchmark_version")),
    ):
        if left is not None and right is not None and left != right:
            raise ValueError("weak and strong reports do not describe the same frozen panel")

    both_correct = weak_only = strong_only = both_wrong = 0
    for scenario_id in sorted(weak_by_id):
        weak = weak_by_id[scenario_id]
        strong = strong_by_id[scenario_id]
        if weak.get("expected") != strong.get("expected"):
            raise ValueError("paired reports disagree on hidden expected label")
        weak_ok = bool(weak.get("correct"))
        strong_ok = bool(strong.get("correct"))
        if weak_ok and strong_ok:
            both_correct += 1
        elif weak_ok:
            weak_only += 1
        elif strong_ok:
            strong_only += 1
        else:
            both_wrong += 1

    return PairedCapabilityComparison(
        benchmark_name=weak_observation.benchmark_name,
        benchmark_version=weak_observation.benchmark_version,
        candidate_id=weak_observation.candidate_id,
        panel_id=weak_observation.panel_id,
        weak_observation_id=weak_observation.observation_id,
        strong_observation_id=strong_observation.observation_id,
        both_correct=both_correct,
        weak_only_correct=weak_only,
        strong_only_correct=strong_only,
        both_wrong=both_wrong,
        input_artifact_hashes=input_artifact_hashes or {},
    )


def load_json_text(raw: bytes) -> dict[str, Any]:
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    return payload
