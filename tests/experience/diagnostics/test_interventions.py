"""Public synthetic native runs; controlled contrasts are not general causal proof."""

import copy

import pytest

from investigation_world.experience.counterfactual import execute_counterfactual_experience
from investigation_world.experience.diagnostics.interventions import (
    diagnose_counterfactual,
    intervention_failure_families,
)
from investigation_world.experience_foundry.admission import PublicTrainingRecorder
from investigation_world.operational.models import EpisodeSubmission


def contrast(root, initial="=0", replacement="good"):
    recorder = PublicTrainingRecorder(root / "source")
    records = recorder.runtime.public_payload()["records"]
    audit = next(r for r in records if r["record_type"] == "formula_audit")
    good = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    recorder.act(
        "repair_formula", cell=audit["object_id"], formula=good if initial == "good" else initial
    )
    recorder.act("recalculate_model")
    source = recorder.submit(
        EpisodeSubmission(
            conclusion="Public synthetic protocol",
            evidence_ids=[
                r["record_id"]
                for r in records
                if r["record_type"] in {"formula_audit", "model_check"}
            ],
        )
    )
    receipt = execute_counterfactual_experience(
        source,
        branch_step=0,
        replacement={
            "cell": audit["object_id"],
            "formula": good if replacement == "good" else replacement,
        },
        artifact_root=root / "branches",
    )
    return source, receipt


def test_positive_bound_contrast_and_immutable_source(tmp_path):
    source, receipt = contrast(tmp_path)
    before = copy.deepcopy((source, receipt))
    report = diagnose_counterfactual(receipt, source=source)
    assert (source, receipt) == before
    assert report.evidence_status == "OBSERVED_CONTROLLED_CONTRAST"
    assert report.causal_status == "UNKNOWN"
    assert report.mechanism_status == "HYPOTHESIZED"
    assert report.outcome_direction == "improved"
    assert report.target_shortfall > 0
    assert report.affected_capability == source.capability.capability_id
    assert report.diagnostics.first_divergence_reference
    assert report.diagnostics.successful_recovery_references
    assert report.causal_candidate.record_type == "causal_candidate"
    assert report.causal_candidate.attributes["causal_status"] == "UNKNOWN"
    assert report.unavailable["individual_failed_target"]
    assert report.visibility.value == "evaluator_private"
    public = str(report.public_payload())
    assert str(tmp_path) not in public
    assert receipt.receipt_id not in public
    assert source.experience.experience_id not in public
    assert report == diagnose_counterfactual(receipt, source=source)


@pytest.mark.parametrize(
    "initial,replacement,direction",
    [("=0", "=0", "unchanged"), ("good", "=0", "worsened"), ("good", "good", "unchanged")],
)
def test_negative_no_effect_and_valid_unchanged(tmp_path, initial, replacement, direction):
    source, receipt = contrast(tmp_path, initial, replacement)
    report = diagnose_counterfactual(receipt, source=source)
    assert report.outcome_direction == direction
    assert not report.diagnostics.successful_recovery_references
    assert report.causal_status == "UNKNOWN"
    if initial == replacement:
        assert report.causal_candidate is None
        assert report.diagnostics.first_divergence_reference is None
    if initial == "good":
        assert report.target_shortfall == 0


@pytest.mark.parametrize("field", ["bindings", "outcome_delta", "source_digest"])
def test_tampered_receipt_fails_closed(tmp_path, field):
    source, receipt = contrast(tmp_path)
    bad = receipt.model_copy(update={field: {} if field != "source_digest" else "forged"})
    with pytest.raises(ValueError):
        diagnose_counterfactual(bad, source=source)


def test_missing_artifact_cannot_produce_diagnostic(tmp_path):
    source, receipt = contrast(tmp_path)
    import shutil

    shutil.rmtree(tmp_path / "branches")
    with pytest.raises(ValueError):
        diagnose_counterfactual(receipt, source=source)


def test_family_capability_binding_and_semantic_duplicate_suppression(tmp_path):
    first = contrast(tmp_path / "a")
    same = contrast(tmp_path / "b")
    other = contrast(tmp_path / "c", initial="=1")
    assert intervention_failure_families([(first[1], first[0]), (same[1], same[0])]) == ()
    inputs = [(first[1], first[0]), (other[1], other[0])]
    families = intervention_failure_families(inputs)
    assert len(families) == 1
    family = families[0]
    assert family.family.affected_capability == first[0].capability.capability_id
    assert family.gap.frequency == 2
    assert family.status == "HYPOTHESIZED"
    assert family.gap.prerequisite_candidates == ()
    assert family.gap.likely_abstraction_deficit is None
    assert family.evidence_references
    assert families == intervention_failure_families(list(reversed(inputs)))
    assert family.public_payload() == {"status": "UNKNOWN", "reason": "evaluator_private"}


def test_distinct_source_and_capability_forgery_rejected(tmp_path):
    source, receipt = contrast(tmp_path / "first")
    other, _ = contrast(tmp_path / "other")
    with pytest.raises(ValueError, match="SOURCE_BINDING_MISMATCH"):
        diagnose_counterfactual(receipt, source=other)
    from dataclasses import replace

    forged = replace(
        source, capability=source.capability.model_copy(update={"capability_id": "forged"})
    )
    with pytest.raises(ValueError, match="CAPABILITY_IDENTITY_MISMATCH"):
        diagnose_counterfactual(receipt, source=forged)


def test_residual_violations_not_erased_or_marked_recovered(tmp_path):
    source, receipt = contrast(tmp_path, initial="=1", replacement="=0")
    report = diagnose_counterfactual(receipt, source=source)
    assert report.causal_candidate is not None  # changed action, unsuccessful contrast retained
    assert report.outcome_direction == "unchanged"
    assert report.residual_violations["alternative"]["missing_required_actions"]
    assert not report.diagnostics.successful_recovery_references
    assert report.unavailable["recovery"]
    assert report.capability_mapping == "DECLARED_TASK_ASSOCIATION"


def test_invalid_top_level_private_projection_never_declassifies(tmp_path):
    source, receipt = contrast(tmp_path)
    report = diagnose_counterfactual(receipt, source=source)
    assert report.public_payload() == report.buyer_safe_payload()
    assert all(ref.visibility.value == "evaluator_private" for ref in report.evidence_references)
    assert report.diagnostics.visibility.value == "evaluator_private"
    assert report.causal_candidate.visibility.value == "evaluator_private"


def test_same_source_multiple_receipts_have_stable_family_evidence(tmp_path):
    source, first = contrast(tmp_path / "first")
    replacement = dict(first.bindings["replacement_call"]["kwargs"])
    replacement["formula"] = "=0"
    second = execute_counterfactual_experience(
        source, branch_step=0, replacement=replacement, artifact_root=tmp_path / "second"
    )
    other_source, other = contrast(tmp_path / "other", initial="=1")
    inputs = [(first, source), (second, source), (other, other_source)]
    assert intervention_failure_families(inputs) == intervention_failure_families(inputs[::-1])
