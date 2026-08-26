import json

from investigation_world.benchmark.selective_agency import (
    SelectiveAgencyDecision,
    score_selective_agency,
)
from investigation_world.benchmark.selective_agency_runtime import (
    SelectiveAgencyRuntime,
    verify_selective_agency_runtime,
)
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.selective_agency_distribution import (
    SelectiveAgencyDistributionConfig,
    compile_selective_agency_distribution,
    selective_agency_agent_payload,
    selective_agency_foundry_metadata,
    selective_agency_oracle_payload,
    validate_selective_agency_distribution,
    write_selective_agency_distribution,
)


def _bundle(seed: int = 11):
    return compile_selective_agency_distribution(
        SelectiveAgencyDistributionConfig(
            seed=seed,
            train_count=20,
            iid_test_count=20,
            ood_count=20,
            adversarial_count=20,
        )
    )


def test_procedural_distribution_is_deterministic_for_fixed_seed():
    left = _bundle(seed=17)
    right = _bundle(seed=17)
    other = _bundle(seed=18)

    assert left.model_dump(mode="json") == right.model_dump(mode="json")
    assert left.model_dump(mode="json") != other.model_dump(mode="json")


def test_distribution_validation_checks_split_and_ood_invariants():
    bundle = _bundle()
    report = validate_selective_agency_distribution(bundle)

    assert report.passed
    assert report.total_tasks == 80
    assert report.split_counts == {
        "train": 20,
        "iid_test": 20,
        "ood": 20,
        "adversarial": 20,
    }
    assert report.decision_counts["execute"] > 0
    assert report.decision_counts["no_op"] > 0
    assert report.decision_counts["clarify"] > 0
    assert report.decision_counts["reframe"] > 0
    assert report.decision_counts["answer"] > 0


def test_agent_payload_excludes_evaluator_labels_split_seed_pairing_and_oracle_fields():
    bundle = _bundle()
    payload = selective_agency_agent_payload(bundle)
    encoded = json.dumps(payload, sort_keys=True)

    for private_field in (
        "task_class",
        "metadata",
        "surface_profile",
        "preferred_decision",
        "acceptable_decisions",
        "action_consequences",
        "required_actions",
        "contrast_group",
        "scenario_family",
        "variant",
        "generator_seed",
        "split",
        "seed",
    ):
        assert private_field not in encoded

    assert all(
        set(task) == {
            "task_id",
            "prompt",
            "objective",
            "visible_state",
            "available_actions",
        }
        for task in payload["tasks"]
    )

    private = selective_agency_oracle_payload(bundle)
    assert private["generator_seed"] == bundle.generator_seed
    assert private["items"][0]["task_class"]
    assert private["items"][0]["oracle"]["preferred_decision"]


def test_operational_contrast_group_flips_correct_behavior_with_world_state():
    bundle = _bundle()
    train_operational = [
        item
        for item in bundle.items
        if item.split == DistributionSplit.TRAIN
        and item.scenario_family != "question_judgment"
    ]
    group_id = train_operational[0].contrast_group
    group = [item for item in train_operational if item.contrast_group == group_id]

    assert {item.variant for item in group} == {"execute", "no_op", "clarify", "blocked"}
    assert {item.case.oracle.preferred_decision for item in group} == {
        SelectiveAgencyDecision.EXECUTE,
        SelectiveAgencyDecision.NO_OP,
        SelectiveAgencyDecision.CLARIFY,
        SelectiveAgencyDecision.REFRAME,
    }


def test_runtime_executes_warranted_action_and_verifies_state_transition():
    bundle = _bundle()
    item = next(
        item
        for item in bundle.items
        if item.split == DistributionSplit.TRAIN and item.variant == "execute"
    )
    action = item.case.oracle.required_actions[0]
    runtime = SelectiveAgencyRuntime(item.case)

    result = runtime.execute(action)
    attempt = runtime.to_attempt(SelectiveAgencyDecision.EXECUTE)
    signals = verify_selective_agency_runtime(item.case, runtime, attempt)
    score = score_selective_agency(item.case, attempt, signals)

    assert result.world_changed
    assert signals.outcome_correct
    assert not score.unnecessary_action
    assert not score.harmful_action
    assert score.judgment == 1.0
    assert score.total_score > 0.9


def test_runtime_penalizes_blocked_high_consequence_action():
    bundle = _bundle()
    item = next(
        item
        for item in bundle.items
        if item.split == DistributionSplit.ADVERSARIAL and item.variant == "blocked"
    )
    action = item.case.public.available_actions[1]
    runtime = SelectiveAgencyRuntime(item.case)

    result = runtime.execute(action)
    attempt = runtime.to_attempt(SelectiveAgencyDecision.EXECUTE)
    signals = verify_selective_agency_runtime(item.case, runtime, attempt)
    score = score_selective_agency(item.case, attempt, signals)

    assert result.forbidden
    assert result.consequence_severity > 0.0
    assert not signals.outcome_correct
    assert score.unnecessary_action
    assert score.forbidden_action
    assert score.harmful_action
    assert score.consequence_severity > 0.0
    assert score.total_score < 0.3


def test_read_only_inspection_consumes_resources_without_counting_as_world_action():
    bundle = _bundle()
    item = next(
        item
        for item in bundle.items
        if item.split == DistributionSplit.IID_TEST and item.variant == "no_op"
    )
    runtime = SelectiveAgencyRuntime(item.case)

    inspection = runtime.execute("inspect")
    attempt = runtime.to_attempt(SelectiveAgencyDecision.NO_OP)
    signals = verify_selective_agency_runtime(item.case, runtime, attempt)
    score = score_selective_agency(item.case, attempt, signals)

    assert not inspection.world_changed
    assert attempt.tool_calls == 1
    assert attempt.actions == []
    assert signals.outcome_correct
    assert not score.unnecessary_action
    assert score.resource_proportionality < 1.0


def test_foundry_metadata_preserves_private_split_without_oracle_decision():
    bundle = _bundle()
    metadata = selective_agency_foundry_metadata(
        bundle,
        harness_version="test-harness",
        runtime_version="selective-runtime-v1",
    )

    assert len(metadata) == len(bundle.items)
    assert {item.split for item in metadata} == set(DistributionSplit)
    assert all("selective_agency" in item.capability_tags for item in metadata)
    assert all("preferred_decision" not in item.generator_parameters for item in metadata)


def test_distribution_writer_keeps_public_and_private_files_separate(tmp_path):
    bundle = _bundle()
    public_path = tmp_path / "public.json"
    oracle_path = tmp_path / "oracle.json"

    write_selective_agency_distribution(
        bundle,
        public_path=public_path,
        oracle_path=oracle_path,
    )

    public_text = public_path.read_text(encoding="utf-8")
    oracle_text = oracle_path.read_text(encoding="utf-8")
    assert "task_class" not in public_text
    assert "surface_profile" not in public_text
    assert "preferred_decision" not in public_text
    assert "contrast_group" not in public_text
    assert "task_class" in oracle_text
    assert "preferred_decision" in oracle_text
    assert "contrast_group" in oracle_text
