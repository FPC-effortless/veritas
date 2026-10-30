"""Real public TRAIN native execution, not hypothetical counterfactual summaries."""

import copy

import pytest

from investigation_world.experience.counterfactual import (
    execute_counterfactual_experience,
    validate_counterfactual_receipt,
)
from investigation_world.experience_foundry.admission import PublicTrainingRecorder
from investigation_world.operational.models import EpisodeSubmission
from investigation_world.trajectory import canonical_hash


def recorded(root, formula="=0"):
    recorder = PublicTrainingRecorder(root)
    records = recorder.runtime.public_payload()["records"]
    audit = next(r for r in records if r["record_type"] == "formula_audit")
    good = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    recorder.act(
        "repair_formula", cell=audit["object_id"], formula=good if formula == "good" else formula
    )
    recorder.act("recalculate_model")
    submission = EpisodeSubmission(
        conclusion="Public synthetic protocol",
        evidence_ids=[
            r["record_id"] for r in records if r["record_type"] in {"formula_audit", "model_check"}
        ],
    )
    return recorder.submit(submission), {"cell": audit["object_id"], "formula": good}


def test_real_positive_baseline_repeat_and_immutable_source(tmp_path):
    source, replacement = recorded(tmp_path / "source")
    original = copy.deepcopy(source)
    receipt = execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    assert source == original
    assert receipt.source.semantic_fingerprint == receipt.baseline.semantic_fingerprint
    assert receipt.alternative.semantic_fingerprint == receipt.repeated.semantic_fingerprint
    assert receipt.baseline.breakdown["outcome"] < receipt.alternative.breakdown["outcome"]
    assert receipt.alternative.breakdown["outcome"] == 1
    assert receipt.recovery_status == "success"
    assert receipt.causal_status == "UNKNOWN"
    assert receipt.alternative.experience.maturity.value == "E0_TRACEABLE"
    assert receipt.alternative.experience.trajectory.runtime.version is None
    assert (
        receipt.alternative.experience.trajectory.trajectory_id
        != receipt.repeated.experience.trajectory.trajectory_id
    )
    assert validate_counterfactual_receipt(receipt, source=source) == receipt
    assert receipt.derived_experience(source=source).visibility.value == "evaluator_private"
    with pytest.raises(ValueError):
        receipt.derived_experience(source=source).public_payload()
    public = str(receipt.public_payload())
    assert str(tmp_path) not in public
    assert source.experience.experience_id not in public
    assert receipt.source_digest == canonical_hash(source.experience.model_dump(mode="json"))


@pytest.mark.parametrize(
    "initial,formula,preference",
    [("=0", "=0", "NONE"), ("good", "=0", "BASELINE"), ("good", "good", "NONE")],
)
def test_no_effect_negative_and_failed_alternatives(tmp_path, initial, formula, preference):
    source, replacement = recorded(tmp_path / "source", initial)
    if formula != "good":
        replacement["formula"] = formula
    receipt = execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    assert receipt.preference["preferred"] == preference
    assert validate_counterfactual_receipt(receipt, source=source) == receipt
    if formula == "=0":
        assert receipt.alternative.breakdown["outcome"] < 1
        assert receipt.recovery_status == "failure"
        assert receipt.alternative.companion.events[0].payload["success"] is False
        assert receipt.alternative.breakdown["missing_required_actions"]
    assert receipt.alternative.experience.maturity.value == "E0_TRACEABLE"


@pytest.mark.parametrize("where", ["prefix", "suffix"])
def test_failed_untouched_calls_are_not_silently_skipped(tmp_path, where):
    recorder = PublicTrainingRecorder(tmp_path / "source")
    records = recorder.runtime.public_payload()["records"]
    audit = next(r for r in records if r["record_type"] == "formula_audit")
    good = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    kwargs = {"cell": audit["object_id"], "formula": good}
    recorder.act("repair_formula", cell=audit["object_id"], formula="=0")
    recorder.act("repair_formula", cell=audit["object_id"], formula="=0")
    recorder.act("recalculate_model")
    source = recorder.submit(EpisodeSubmission(conclusion="fixture"))
    with pytest.raises(ValueError, match="FAILED_UNTOUCHED"):
        execute_counterfactual_experience(
            source,
            branch_step=1 if where == "prefix" else 0,
            replacement=kwargs,
            artifact_root=tmp_path / "branches",
        )
    assert not (tmp_path / "branches").exists()


@pytest.mark.parametrize(
    "replacement",
    [
        {"cell": "future-private-cell", "formula": "=0"},
        {"cell": "unused", "formula": "=PRIVATE_FUTURE_TRUTH"},
        {"cell": "unused", "formula": "=0", "oracle": "secret"},
    ],
)
def test_rejects_nonpublic_or_unstructured_interventions(tmp_path, replacement):
    source, _ = recorded(tmp_path / "source")
    with pytest.raises(ValueError, match="PUBLIC_INTERVENTION"):
        execute_counterfactual_experience(
            source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
        )
    assert not (tmp_path / "branches").exists()


@pytest.fixture
def executed(tmp_path):
    source, replacement = recorded(tmp_path / "source")
    receipt = execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    return source, receipt


@pytest.mark.parametrize(
    "field,value",
    [
        ("receipt_id", "forged"),
        ("runtime_source_digest", "forged"),
        ("source_digest", "forged"),
        ("causal_status", "PASS"),
        ("execution_status", "PASS"),
        ("visibility", "public"),
        ("state_delta", {}),
        ("outcome_delta", {}),
        ("recovery_status", "failure"),
        ("public_at_cut", {"record": "future-private-sentinel"}),
        ("preference", {"preferred": "ALTERNATIVE", "rationale": "caller PASS"}),
    ],
)
def test_revalidates_all_receipt_fields(executed, field, value):
    source, receipt = executed
    forged = receipt.model_copy(update={field: value}, deep=True)
    with pytest.raises(ValueError):
        validate_counterfactual_receipt(forged, source=source)


@pytest.mark.parametrize(
    "field",
    [
        "prefix",
        "suffix",
        "submission",
        "initial_state_digest",
        "native_receipt_ids",
        "capability",
        "portable_contract_id",
    ],
)
def test_exact_bindings_cannot_be_replaced(executed, field):
    source, receipt = executed
    forged = receipt.model_copy(deep=True)
    forged.bindings[field] = "forged"
    with pytest.raises(ValueError):
        validate_counterfactual_receipt(forged, source=source)


@pytest.mark.parametrize("field", ["breakdown", "semantic_fingerprint", "content_digest"])
def test_nested_summary_is_never_authority(executed, field):
    source, receipt = executed
    alternative = receipt.alternative.model_copy(
        update={field: {} if field == "breakdown" else "forged"}, deep=True
    )
    forged = receipt.model_copy(update={"alternative": alternative})
    with pytest.raises(ValueError):
        validate_counterfactual_receipt(forged, source=source)


def test_repeated_is_independent_not_alias(executed):
    source, receipt = executed
    forged = receipt.model_copy(update={"repeated": receipt.alternative})
    with pytest.raises(ValueError, match="INDEPENDENT_NATIVE"):
        validate_counterfactual_receipt(forged, source=source)


def test_retained_artifact_tamper_rejected(executed):
    from pathlib import Path

    from investigation_world.trajectory.reverify import REPLAY_EVIDENCE_PRIVATE_KEY

    source, receipt = executed
    raw = receipt.alternative.experience.trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    path = Path(raw["native_submission"]["artifact_path"])
    path.write_bytes(b"not the retained native workbook")
    with pytest.raises(ValueError, match="REVERIFICATION"):
        validate_counterfactual_receipt(receipt, source=source)


def test_source_mismatch_is_rejected(executed, tmp_path):
    source, receipt = executed
    other, _ = recorded(tmp_path / "other", "good")
    with pytest.raises(ValueError, match="SOURCE_BINDING"):
        validate_counterfactual_receipt(receipt, source=other)


def test_capability_and_companion_mutations_rejected(tmp_path):
    from dataclasses import replace

    source, replacement = recorded(tmp_path / "source")
    capability = source.capability.model_copy(update={"objective": "forged"})
    with pytest.raises(ValueError, match="CAPABILITY"):
        execute_counterfactual_experience(
            replace(source, capability=capability),
            branch_step=0,
            replacement=replacement,
            artifact_root=tmp_path / "branches",
        )
    companion = source.companion.model_copy(update={"runtime_version": "forged"})
    with pytest.raises(ValueError, match="COMPANION"):
        execute_counterfactual_experience(
            replace(source, companion=companion),
            branch_step=0,
            replacement=replacement,
            artifact_root=tmp_path / "branches",
        )


def test_stale_private_verification_is_not_authority(executed):
    from dataclasses import replace

    from investigation_world.experience import MachineExperience
    from investigation_world.trajectory import TrajectoryV2

    source, receipt = executed
    record = receipt.source.verification.model_copy(deep=True)
    record.private_metadata["verification_breakdown"]["outcome"] = 1
    trajectory = TrajectoryV2.model_validate(
        {
            **source.experience.trajectory.model_dump(mode="python"),
            "reverifications": [record.model_dump(mode="python")],
        }
    )
    experience = MachineExperience.model_validate(
        {**source.experience.model_dump(mode="python"), "trajectory": trajectory}
    )
    from investigation_world.experience.counterfactual.execution import _snapshot

    fresh = _snapshot(replace(source, experience=experience))
    assert fresh.breakdown["outcome"] < 1
    assert fresh.breakdown == receipt.source.breakdown


def test_public_at_cut_record_binding(executed):
    from investigation_world.experience_foundry.admission import public_training_fixture

    _, receipt = executed
    case, _ = public_training_fixture()
    public = case.episode.public_payload()
    assert receipt.public_at_cut["public_payload_digest"] == canonical_hash(public)
    assert receipt.public_at_cut["record"] in public["records"]
    assert receipt.public_at_cut["available_at_step"] == 0
    assert receipt.public_at_cut["record_digest"] == canonical_hash(receipt.public_at_cut["record"])


def test_successful_nonempty_prefix_is_preserved(tmp_path):
    recorder = PublicTrainingRecorder(tmp_path / "source")
    audit = next(
        r
        for r in recorder.runtime.public_payload()["records"]
        if r["record_type"] == "formula_audit"
    )
    good = {
        "cell": audit["object_id"],
        "formula": f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})",
    }
    recorder.act("repair_formula", **good)
    recorder.act("repair_formula", **good)
    recorder.act("recalculate_model")
    source = recorder.submit(EpisodeSubmission(conclusion="public prefix test"))
    receipt = execute_counterfactual_experience(
        source,
        branch_step=1,
        replacement={**good, "formula": "=0"},
        artifact_root=tmp_path / "branches",
    )
    assert len(receipt.bindings["prefix"]) == 1
    assert receipt.public_at_cut["available_at_step"] == 1
    assert receipt.alternative.companion.events[0] == source.companion.events[0]
    assert validate_counterfactual_receipt(receipt, source=source) == receipt


def test_actual_cut_visibility_checked_before_intervention(tmp_path, monkeypatch):
    source, replacement = recorded(tmp_path / "source")
    from investigation_world.operational import NativeOperationalRuntime

    original = NativeOperationalRuntime.public_payload

    def changed(self):
        value = original(self)
        value["records"] = []
        return value

    monkeypatch.setattr(NativeOperationalRuntime, "public_payload", changed)
    with pytest.raises(ValueError, match="ACTUAL_PUBLIC_CUT_MISMATCH"):
        execute_counterfactual_experience(
            source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("runtime_version", "wrong"),
        ("task_seed", 0),
        ("split", "iid_test"),
        ("split", "ood"),
        ("split", "adversarial"),
        ("harness_version", "wrong"),
        ("initial_state_hash", "wrong"),
    ],
)
def test_unsupported_companions_reject(tmp_path, field, value):
    from dataclasses import replace

    source, replacement = recorded(tmp_path / "source")
    bad = replace(source, companion=source.companion.model_copy(update={field: value}))
    with pytest.raises(ValueError):
        execute_counterfactual_experience(
            bad, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
        )


@pytest.mark.parametrize("field", ["runtime", "world", "verifier", "initial_state"])
def test_reidentified_canonical_identity_rejects(tmp_path, field):
    from dataclasses import replace

    from investigation_world.experience import machine_experience_from_trajectory
    from investigation_world.trajectory import TrajectoryV2

    source, replacement = recorded(tmp_path / "source")
    payload = source.experience.trajectory.model_dump(mode="python")
    key = {
        "runtime": "version",
        "world": "world_version",
        "verifier": "version",
        "initial_state": "digest",
    }[field]
    payload[field][key] = "different"
    payload["trajectory_id"] = ""
    with pytest.raises(ValueError):
        bad = replace(
            source,
            experience=machine_experience_from_trajectory(TrajectoryV2.model_validate(payload)),
        )
        execute_counterfactual_experience(
            bad, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
        )


def test_private_source_cannot_be_widened(tmp_path):
    from dataclasses import replace

    source, replacement = recorded(tmp_path / "source")
    bad = replace(source, experience=source.experience.model_copy(update={"visibility": "sealed"}))
    with pytest.raises(ValueError):
        execute_counterfactual_experience(
            bad, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
        )


def test_supported_projections_and_raw_serialization_boundary(executed, tmp_path):
    source, receipt = executed
    derivative = receipt.derived_experience(source=source)
    for projection in (derivative.public_payload, derivative.buyer_safe_payload):
        with pytest.raises(ValueError, match="EVALUATOR_PRIVATE"):
            projection()
    assert str(tmp_path) not in str(receipt.public_payload())
    # Raw model serialization is deliberately evaluator-only, not an export API.
    assert str(tmp_path) in receipt.model_dump_json()
    # Base coercion is NOT a supported projection and cannot preserve subclass guards.
    from investigation_world.experience import MachineExperience

    coerced = MachineExperience.model_validate(derivative.model_dump(mode="python"))
    assert coerced.visibility == derivative.visibility


def test_source_retained_bytes_unchanged(tmp_path):
    import hashlib
    from pathlib import Path

    from investigation_world.trajectory.reverify import REPLAY_EVIDENCE_PRIVATE_KEY

    source, replacement = recorded(tmp_path / "source")
    raw = source.experience.trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    path = Path(raw["native_submission"]["artifact_path"])
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_residual_violations_survive_a_repair(tmp_path):
    recorder = PublicTrainingRecorder(tmp_path / "source")
    audit = next(
        r
        for r in recorder.runtime.public_payload()["records"]
        if r["record_type"] == "formula_audit"
    )
    recorder.act("repair_formula", cell=audit["object_id"], formula="=0")
    recorder.act("overwrite_values", range=audit["object_id"])
    recorder.act("recalculate_model")
    source = recorder.submit(EpisodeSubmission(conclusion="public residual violation fixture"))
    receipt = execute_counterfactual_experience(
        source,
        branch_step=0,
        replacement={
            "cell": audit["object_id"],
            "formula": f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})",
        },
        artifact_root=tmp_path / "branches",
    )
    assert receipt.alternative.breakdown["invariant_violations"]
    assert receipt.alternative.breakdown["forbidden_actions_taken"]
    assert receipt.recovery_status == "failure"
    assert receipt.preference["preferred"] == "NONE"
    assert validate_counterfactual_receipt(receipt, source=source) == receipt


def test_caller_private_annotations_not_public_profile_authority(tmp_path):
    from dataclasses import replace

    source, replacement = recorded(tmp_path / "source")
    bad = replace(
        source,
        experience=source.experience.model_copy(
            update={"private_metadata": {"future_secret": "PRIVATE_SENTINEL"}}
        ),
    )
    with pytest.raises(ValueError, match="RECORDER_EXPERIENCE_PROFILE"):
        execute_counterfactual_experience(
            bad, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
        )
