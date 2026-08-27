from investigation_world.commercial.sre_evaluation import (
    build_sre_prompt,
    evaluate_sre_generator,
    parse_sre_prediction,
    sanitize_sre_evaluation,
)
from investigation_world.qualification import (
    QualificationScenario,
    QualificationSplit,
    SRECausalClass,
    SREQualificationCase,
)


def _case(index: int, label: SRECausalClass) -> SREQualificationCase:
    scenario = QualificationScenario(
        scenario_id=f"SRE-TEST-{index}",
        source_group_id=f"provider:incident-{index}",
        split=QualificationSplit.PRIVATE_TEST,
        normalized_text=f"incident {index}",
        public_digest=f"public-{index}",
        private_digest=f"private-{index}",
    )
    return SREQualificationCase(
        scenario=scenario,
        public_text=f"Service errors observed in region {index}.",
        causal_class=label,
        provider="provider",
    )


def test_prediction_parser_accepts_strict_and_wrapped_json() -> None:
    assert parse_sre_prediction('{"causal_class":"capacity"}') == SRECausalClass.CAPACITY
    assert parse_sre_prediction('Result: {"causal_class":"regression"}') == SRECausalClass.REGRESSION
    assert parse_sre_prediction("infrastructure") == SRECausalClass.INFRASTRUCTURE
    assert parse_sre_prediction("unknown") is None


def test_prompt_exposes_only_early_evidence_contract() -> None:
    prompt = build_sre_prompt("early evidence marker")
    assert "early evidence marker" in prompt
    assert "later resolution" in prompt.casefold()
    assert "Do not assume access" in prompt


def test_private_panel_evaluation_reports_imbalance_aware_metrics_and_parse_failures() -> None:
    cases = [
        _case(1, SRECausalClass.CAPACITY),
        _case(2, SRECausalClass.REGRESSION),
        _case(3, SRECausalClass.TRANSIENT),
        _case(4, SRECausalClass.TRANSIENT),
        _case(5, SRECausalClass.INFRASTRUCTURE),
    ]
    outputs = iter([
        '{"causal_class":"capacity"}',
        '{"causal_class":"transient"}',
        '{"causal_class":"transient"}',
        '{"causal_class":"transient"}',
        "not-json-and-not-a-label",
    ])

    report = evaluate_sre_generator(
        cases,
        lambda _: next(outputs),
        model_name="test-model",
        candidate_id="SRE-CAND-TEST",
        benchmark_version="sre-test-v1",
    )

    assert report["private_cases"] == 5
    assert report["correct"] == 3
    assert report["accuracy"] == 0.6
    assert report["majority_class"] == "transient"
    assert report["majority_baseline_accuracy"] == 0.4
    assert report["accuracy_lift_over_majority"] == 0.2
    assert report["balanced_accuracy"] == 0.5
    assert 0.0 < report["macro_f1"] < report["accuracy"]
    assert report["parse_failures"] == 1
    assert report["ci95_low"] < report["accuracy"] < report["ci95_high"]
    assert report["prompt_contract"]["private_resolution_notes_exposed"] is False
    assert report["prompt_contract"]["private_causal_label_exposed"] is False


def test_public_sanitizer_removes_private_case_rows() -> None:
    cases = [
        _case(1, SRECausalClass.CAPACITY),
        _case(2, SRECausalClass.REGRESSION),
        _case(3, SRECausalClass.TRANSIENT),
        _case(4, SRECausalClass.INFRASTRUCTURE),
    ]
    report = evaluate_sre_generator(
        cases,
        lambda _: '{"causal_class":"capacity"}',
        model_name="test-model",
        candidate_id="SRE-CAND-TEST",
        benchmark_version="sre-test-v1",
    )

    public = sanitize_sre_evaluation(report)

    assert "cases" not in public
    assert public["private_case_details_included"] is False
    assert public["artifact_contract"]["scenario_ids_included"] is False
    assert public["artifact_contract"]["per_case_expected_labels_included"] is False
    assert public["candidate_id"] == report["candidate_id"]
    assert public["panel_id"] == report["panel_id"]
    assert public["balanced_accuracy"] == report["balanced_accuracy"]


def test_evaluation_ignores_non_private_cases() -> None:
    private = _case(1, SRECausalClass.CAPACITY)
    train_scenario = private.scenario.model_copy(update={"scenario_id": "SRE-TRAIN", "split": QualificationSplit.TRAIN})
    train = private.model_copy(update={"scenario": train_scenario})

    report = evaluate_sre_generator(
        [train, private],
        lambda _: '{"causal_class":"capacity"}',
        model_name="test-model",
        candidate_id="SRE-CAND-TEST",
        benchmark_version="sre-test-v1",
    )
    assert report["private_cases"] == 1
    assert report["accuracy"] == 1.0
    assert report["balanced_accuracy"] == 1.0
    assert report["macro_f1"] == 1.0
