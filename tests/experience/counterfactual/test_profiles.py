"""Versioned structural-profile replay executes failures; no model evidence is invented."""

import copy
from pathlib import Path

import pytest

from investigation_world.experience.counterfactual import (
    execute_counterfactual_experience,
    validate_counterfactual_receipt,
)
from investigation_world.experience_foundry.admission import (
    PublicTrainingRecorder,
    admit_experience,
    authorized_registry,
)
from investigation_world.operational import EpisodeSubmission
from investigation_world.trajectory.reverify import REPLAY_EVIDENCE_PRIVATE_KEY


def record_profile(root, *, prefix=False, profile_id="financial-ordered-v2"):
    recorder = PublicTrainingRecorder(root, profile_id=profile_id)
    rows = recorder.runtime.public_payload()["records"]
    audit = next(row for row in rows if row["record_type"] == "formula_audit")
    replacement = {
        "cell": audit["object_id"],
        "formula": f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})",
    }
    if prefix:
        recorder.act("recalculate_model")
    recorder.act("repair_formula", cell=audit["object_id"], formula="=0")
    recorder.act("recalculate_model")
    source = recorder.submit(
        EpisodeSubmission(
            conclusion="Constructed public structural protocol",
            evidence_ids=[
                row["record_id"]
                for row in rows
                if row["record_type"] in {"formula_audit", "model_check"}
            ],
        )
    )
    return source, replacement


def test_v2_failed_suffix_is_executed_and_freshly_verified(tmp_path):
    source, replacement = record_profile(tmp_path / "source")
    original = copy.deepcopy(source)
    receipt = execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    assert receipt.schema_version == "veritas.counterfactual-experience.v2"
    assert [e.payload["success"] for e in receipt.baseline.companion.events[:2]] == [False, False]
    assert [e.payload["success"] for e in receipt.alternative.companion.events[:2]] == [True, True]
    assert receipt.baseline.companion.total_cost == source.companion.total_cost == 4
    assert receipt.source.semantic_fingerprint == receipt.baseline.semantic_fingerprint
    assert receipt.alternative.semantic_fingerprint == receipt.repeated.semantic_fingerprint
    assert receipt.recovery_status == "success"
    assert validate_counterfactual_receipt(receipt, source=source) == receipt
    assert source == original
    assert receipt.causal_status == receipt.training_usefulness == "UNKNOWN"
    derivative = receipt.derived_experience(source=source)
    assert derivative.derivation_references[-1].reference_type == receipt.schema_version
    assert derivative.maturity.value == "E0_TRACEABLE"
    with pytest.raises(ValueError):
        derivative.public_payload()


def test_v2_failed_prefix_stays_in_evidence_and_blocks_success_admission(tmp_path):
    source, replacement = record_profile(tmp_path / "source", prefix=True)
    receipt = execute_counterfactual_experience(
        source, branch_step=1, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    assert [e.payload["success"] for e in receipt.alternative.companion.events[:3]] == [
        False, True, True,
    ]
    assert receipt.alternative.companion.total_cost == 6
    assert receipt.alternative.breakdown["outcome"] == 1
    assert "blocked_required:recalculate_model" in (
        receipt.alternative.breakdown["process_violations"]
    )
    assert receipt.recovery_status == "failure"
    assert receipt.preference["preferred"] == "NONE"
    with pytest.raises(ValueError, match="VERIFIER_FAILURE_PROCESS"):
        admit_experience(receipt.alternative.recorded(), registry=authorized_registry())


def test_v1_failed_untouched_replay_is_still_refused(tmp_path):
    source, replacement = record_profile(tmp_path / "source", prefix=True, profile_id=None)
    # Recalculation alone succeeds in v1; the failed repair is an untouched suffix here.
    with pytest.raises(ValueError, match="FAILED_UNTOUCHED"):
        execute_counterfactual_experience(
            source, branch_step=2, replacement=replacement, artifact_root=tmp_path / "branches"
        )
    assert not (tmp_path / "branches").exists()


@pytest.fixture
def contrast(tmp_path):
    source, replacement = record_profile(tmp_path / "source")
    receipt = execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "branches"
    )
    return source, receipt


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "veritas.counterfactual-experience.v1"),
        ("recorder_version", "veritas.public-financial-training-recorder.v1"),
        ("recovery_status", "failure"),
        ("source_digest", "0" * 64),
    ],
)
def test_v2_receipt_cannot_be_relabelled_or_replaced(contrast, field, value):
    source, receipt = contrast
    with pytest.raises(ValueError):
        validate_counterfactual_receipt(receipt.model_copy(update={field: value}), source=source)


def test_v2_retained_native_artifact_is_freshly_inspected(contrast):
    source, receipt = contrast
    evidence = receipt.alternative.experience.trajectory.private_metadata[
        REPLAY_EVIDENCE_PRIVATE_KEY
    ]
    Path(evidence["native_submission"]["artifact_path"]).write_bytes(b"changed native artifact")
    with pytest.raises(ValueError, match="REVERIFICATION"):
        validate_counterfactual_receipt(receipt, source=source)


def test_distinct_profile_structures_are_not_semantic_aliases(tmp_path):
    receipts = []
    for index, profile in enumerate(("financial-ordered-v2", "financial-ordered-context-v2")):
        source, replacement = record_profile(tmp_path / str(index) / "source", profile_id=profile)
        receipts.append(execute_counterfactual_experience(
            source, branch_step=0, replacement=replacement,
            artifact_root=tmp_path / str(index) / "branches",
        ))
    assert receipts[0].source.breakdown == receipts[1].source.breakdown
    assert receipts[0].source.semantic_fingerprint != receipts[1].source.semantic_fingerprint
    assert (
        receipts[0].alternative.semantic_fingerprint != receipts[1].alternative.semantic_fingerprint
    )
