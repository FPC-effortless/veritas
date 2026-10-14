from investigation_world.frontier.sre_runner import (
    build_gemini_generate_content_body,
    extract_gemini_text,
    observation_from_sre_report,
    paired_comparison_from_private_sre_reports,
)


def _report(model, correct_flags):
    cases = []
    for idx, ok in enumerate(correct_flags):
        expected = "regression" if idx % 2 == 0 else "capacity"
        prediction = expected if ok else ("transient" if expected == "regression" else "infrastructure")
        cases.append(
            {
                "scenario_id": f"s{idx}",
                "expected": expected,
                "prediction": prediction,
                "correct": ok,
            }
        )
    n = len(cases)
    correct = sum(correct_flags)
    confusion = {}
    for row in cases:
        confusion.setdefault(row["expected"], {})
        confusion[row["expected"]][row["prediction"]] = (
            confusion[row["expected"]].get(row["prediction"], 0) + 1
        )
    return {
        "evaluation": "veritas-sre-private-causal-classification",
        "benchmark_version": "sre-v4",
        "candidate_id": "cand",
        "panel_id": "panel",
        "qualification_report_id": "qr",
        "evidence_manifest_id": "evid",
        "private_release_manifest_id": "rel",
        "model": model,
        "private_cases": n,
        "correct": correct,
        "accuracy": correct / n,
        "parse_failures": 0,
        "confusion": confusion,
        "cases": cases,
    }


def test_gemini_request_and_response_contract():
    body = build_gemini_generate_content_body(
        "prompt",
        system_instruction="system",
        max_output_tokens=64,
        json_output=True,
    )
    assert "temperature" not in body["generationConfig"]
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert extract_gemini_text(
        {"candidates": [{"content": {"parts": [{"text": '{"causal_class":"capacity"}'}]}}]}
    ) == '{"causal_class":"capacity"}'


def test_sre_report_becomes_buyer_safe_observation_with_causal_failure_categories():
    report = _report("m", [True, False, False, True])
    observation = observation_from_sre_report(
        report,
        tier="strong",
        model_snapshot="m-snapshot",
        harness_identity="direct",
    )
    assert observation.sample_size == 4
    assert observation.successes == 2
    assert sum(observation.failure_mode_counts.values()) == 2
    assert "regression->transient" in observation.failure_mode_counts
    assert "capacity->infrastructure" in observation.failure_mode_counts


def test_private_rows_reduce_to_2x2_without_case_ids():
    weak_report = _report("weak", [True, False, False, True, False])
    strong_report = _report("strong", [True, True, False, True, True])
    weak = observation_from_sre_report(
        weak_report,
        tier="weak",
        model_snapshot="weak-snap",
        harness_identity="direct",
    )
    strong = observation_from_sre_report(
        strong_report,
        tier="strong",
        model_snapshot="strong-snap",
        harness_identity="direct",
    )
    paired = paired_comparison_from_private_sre_reports(
        weak_report,
        strong_report,
        weak_observation=weak,
        strong_observation=strong,
    )
    payload = paired.model_dump(mode="json")
    assert payload["both_correct"] == 2
    assert payload["weak_only_correct"] == 0
    assert payload["strong_only_correct"] == 2
    assert payload["both_wrong"] == 1
    assert "cases" not in payload
    assert "scenario_id" not in str(payload)
