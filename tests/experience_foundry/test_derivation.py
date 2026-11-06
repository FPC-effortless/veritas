"""Actual public recorder inputs; candidate compilation is never training admission."""

import copy
from dataclasses import replace
from pathlib import Path

import pytest

from investigation_world.experience.counterfactual import execute_counterfactual_experience
from investigation_world.experience_foundry.admission import (
    PublicTrainingRecorder,
    admit_experience,
    authorized_registry,
)
from investigation_world.experience_foundry.derivation import (
    CandidateLearningAsset,
    TransformPolicy,
    TransformRule,
    compile_learning_assets,
    validate_compilation,
)
from investigation_world.operational import EpisodeSubmission
from investigation_world.trajectory import canonical_hash


def record(root, formula="=0", alternative=True):
    recorder = PublicTrainingRecorder(root / "source")
    rows = recorder.runtime.public_payload()["records"]
    audit = next(r for r in rows if r["record_type"] == "formula_audit")
    good = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    recorder.act(
        "repair_formula", cell=audit["object_id"], formula=good if formula == "good" else formula
    )
    recorder.act("recalculate_model")
    source = recorder.submit(
        EpisodeSubmission(
            conclusion="Constructed public TRAIN protocol",
            evidence_ids=[
                r["record_id"] for r in rows if r["record_type"] in {"formula_audit", "model_check"}
            ],
        )
    )
    receipt = execute_counterfactual_experience(
        source,
        branch_step=0,
        replacement={"cell": audit["object_id"], "formula": good if alternative else formula},
        artifact_root=root / "branches",
    )
    return source, receipt


@pytest.fixture
def execution(tmp_path):
    return record(tmp_path)


def test_one_failed_source_produces_real_independent_private_candidates(execution):
    source, receipt = execution
    before = copy.deepcopy((source, receipt))
    result = compile_learning_assets([source], receipts=[receipt])
    by_kind = {asset.transform.kind: asset for asset in result.assets}
    assert set(by_kind) == {
        "negative",
        "verifier_feedback",
        "evidence_selection",
        "next_state",
        "alternative_action",
        "counterfactual",
        "recovery",
        "preference",
        "structured_repair",
    }
    assert by_kind["negative"].material["feedback"]["outcome"] < 1
    assert by_kind["preference"].material["preference"]["preferred"] == "ALTERNATIVE"
    assert by_kind["recovery"].material["recovery_kind"] == "counterfactual_outcome_restoration"
    assert len({a.record_id for a in result.assets}) == 9
    for asset in result.assets:
        assert asset.lineage.source.reference_id == source.experience.experience_id
        assert asset.lineage.source.digest == canonical_hash(source.experience)
        assert asset.lineage.trajectory.reference_id == source.experience.trajectory.trajectory_id
        assert asset.lineage.verifier.digest
        assert asset.lineage.portable_contract.digest
        assert asset.lineage.canonical_split is None
        assert not asset.training_qualified
        assert asset.training_usefulness == "UNKNOWN"
        assert asset.visibility.value == "evaluator_private"
    assert source.experience.maturity.value == "E0_TRACEABLE"
    assert (source, receipt) == before
    assert compile_learning_assets([source], receipts=[receipt]) == result
    assert validate_compilation(result, sources=[source], receipts=[receipt]) == result
    with pytest.raises(ValueError, match="VERIFIER_"):
        admit_experience(source, registry=authorized_registry())


def test_transform_policy_revision_only_changes_its_derivatives(execution):
    source, receipt = execution
    policy = TransformPolicy()
    revised = TransformPolicy(
        rules=tuple(
            TransformRule(kind=r.kind, revision="2", enabled=r.enabled)
            if r.kind == "negative"
            else r
            for r in policy.rules
        )
    )
    a = compile_learning_assets([source], receipts=[receipt], policy=policy)
    b = compile_learning_assets([source], receipts=[receipt], policy=revised)
    aa = {x.transform.kind: x.record_id for x in a.assets}
    bb = {x.transform.kind: x.record_id for x in b.assets}
    assert {kind for kind in aa if aa[kind] != bb[kind]} == {"negative"}
    assert a.record_id != b.record_id


def test_no_private_candidate_or_qualification_can_be_exported(execution, tmp_path):
    source, receipt = execution
    result = compile_learning_assets([source], receipts=[receipt])
    for obj in (result, *result.assets):
        assert obj.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
        assert obj.buyer_safe_payload() == obj.public_payload()
        assert str(tmp_path) not in str(obj.public_payload())
    asset = result.assets[0]
    with pytest.raises(ValueError, match="CANDIDATE_NOT_TRAINING_ADMITTED"):
        asset.trainer_payload()
    for update in (
        {"visibility": "public"},
        {"training_qualified": True},
        {"training_usefulness": "PASS"},
    ):
        with pytest.raises(ValueError):
            CandidateLearningAsset.model_validate({**asset.model_dump(), **update, "record_id": ""})
    changed = asset.model_copy(deep=True)
    changed.material["private-sentinel"] = "HIDDEN_TRUTH"
    with pytest.raises(ValueError, match="identity"):
        changed.public_payload()


def test_missing_evidence_and_feature_gates_are_explicit(execution):
    source, _ = execution
    result = compile_learning_assets([source])
    assert {a.transform.kind for a in result.assets} == {
        "negative",
        "verifier_feedback",
        "evidence_selection",
        "next_state",
    }
    assert {r.reason for r in result.rejections} >= {
        "COUNTERFACTUAL_EVIDENCE_REQUIRED",
        "FAMILY_GAP_EVIDENCE_REQUIRED",
        "FEATURE_DISABLED",
    }
    policy = TransformPolicy(
        rules=(TransformRule(kind="procedure"), TransformRule(kind="abstraction"))
    )
    result = compile_learning_assets([source], policy=policy)
    assert result.assets == ()
    assert {r.reason for r in result.rejections} == {"PROVIDER_UNAVAILABLE"}


def test_noop_counterfactual_is_trivial_not_preference_or_recovery(tmp_path):
    source, receipt = record(tmp_path, alternative=False)
    result = compile_learning_assets([source], receipts=[receipt])
    assert not {a.transform.kind for a in result.assets} & {
        "alternative_action",
        "counterfactual",
        "recovery",
        "preference",
        "structured_repair",
    }
    assert result.counts["trivial"] == 5
    assert all(r.evidence for r in result.rejections if r.reason == "TRIVIAL_IDENTICAL_ACTION")


def test_duplicate_inputs_and_semantic_material_accounted_without_order_bias(tmp_path):
    a, ar = record(tmp_path / "a")
    b, br = record(tmp_path / "b")
    left = compile_learning_assets([a, b, a], receipts=[ar, br, ar])
    right = compile_learning_assets([b, a, a], receipts=[br, ar, ar])
    assert left == right
    assert left.counts["duplicate_sources"] == 1
    assert left.counts["duplicate_receipts"] == 1
    assert left.counts["duplicate"] > 0
    assert len({a.material_digest for a in left.assets}) == len(left.assets)
    assert all(r.candidate is not None for r in left.rejections if r.reason == "DUPLICATE_MATERIAL")


def test_recomputed_gap_lineage_and_quota_not_empirical_saturation(tmp_path):
    a, ar = record(tmp_path / "a")
    b, br = record(tmp_path / "b", formula="=1")
    policy = TransformPolicy(per_family_transform_quota=1)
    result = compile_learning_assets([a, b], receipts=[ar, br], policy=policy)
    assert len(result.family_evidence) == 1
    gap = result.family_evidence[0]
    assert gap.candidate.gap.frequency == 2
    for asset in result.assets:
        assert asset.lineage.family_ids == (gap.candidate.family.family_id,)
        assert asset.lineage.gap_ids == (gap.candidate.gap.gap_id,)
        assert asset.lineage.family_evidence[0].digest == canonical_hash(gap)
    assert result.counts["quota"] > 0
    assert result.counts["saturated"] is None
    assert result.saturation_status == "UNKNOWN"
    assert result.causal_qualification == "UNKNOWN"


def test_required_saturation_evidence_fails_closed_not_zero(execution):
    source, receipt = execution
    result = compile_learning_assets(
        [source], receipts=[receipt], policy=TransformPolicy(require_saturation_evidence=True)
    )
    assert result.assets == ()
    assert result.counts["saturated"] is None
    assert result.counts["saturation_unknown"] == 9
    assert result.saturation_status == "UNKNOWN"


@pytest.mark.parametrize(
    "field,value",
    [
        ("split", "iid_test"),
        ("split", "ood"),
        ("split", "adversarial"),
        ("task_seed", 0),
        ("runtime_version", "forged"),
    ],
)
def test_stale_or_heldout_source_rejected(execution, field, value):
    source, receipt = execution
    source = replace(source, companion=source.companion.model_copy(update={field: value}))
    with pytest.raises(ValueError):
        compile_learning_assets([source], receipts=[receipt])


@pytest.mark.parametrize(
    "field,value",
    [
        ("receipt_id", "forged"),
        ("state_delta", {}),
        ("preference", {"preferred": "BASELINE"}),
        ("visibility", "public"),
    ],
)
def test_receipt_mutation_rejected(execution, field, value):
    source, receipt = execution
    with pytest.raises(ValueError):
        compile_learning_assets([source], receipts=[receipt.model_copy(update={field: value})])


def test_actual_artifact_mutation_invalidates_a_previously_compiled_result(execution):
    source, receipt = execution
    result = compile_learning_assets([source], receipts=[receipt])
    raw = receipt.alternative.experience.trajectory.private_metadata[
        "operational_reverification_evidence"
    ]
    Path(raw["native_submission"]["artifact_path"]).write_bytes(b"changed retained source")
    with pytest.raises(ValueError, match="REVERIFICATION"):
        validate_compilation(result, sources=[source], receipts=[receipt])


def test_frozen_panel_overlap_rejected(execution):
    source, receipt = execution
    for kwargs in (
        {"frozen_panel_task_ids": (source.companion.task_id,)},
        {"frozen_panel_source_digests": (canonical_hash(source.experience),)},
        {"frozen_panel_source_digests": (source.companion.metadata["source_digest"],)},
    ):
        with pytest.raises(ValueError, match="FROZEN_PANEL"):
            compile_learning_assets([source], receipts=[receipt], **kwargs)


def test_recompilation_rejects_reidentified_material_not_just_stale_hash(execution):
    source, receipt = execution
    result = compile_learning_assets([source], receipts=[receipt])
    data = result.model_dump(mode="python")
    data["record_id"] = ""
    data["assets"][0]["record_id"] = ""
    data["assets"][0]["material"] = {"invented": "LLM output is not verification"}
    forged = type(result).model_validate(data)
    with pytest.raises(ValueError, match="COMPILATION_MISMATCH"):
        validate_compilation(forged, sources=[source], receipts=[receipt])


def saturation_curve(source, *, reference_visibility="internal", root_visibility="internal"):
    """Constructed measurement declarations, NOT actual model/training execution."""
    from investigation_world.capability_science import (
        AcquisitionCurve,
        CapabilitySpec,
        CaseOutcome,
        EvaluationConditions,
        EvaluationPoint,
        EvaluationPopulation,
        TrainingIntervention,
    )
    from investigation_world.experience import ExperienceReference

    def ref(key):
        return ExperienceReference(
            reference_id=key,
            reference_type="constructed",
            digest=canonical_hash(key),
            visibility=reference_visibility,
        )

    conditions = EvaluationConditions(
        environment_id="constructed",
        environment_revision="1",
        verifier_id="constructed",
        verifier_revision="1",
        metric="success_fraction",
        metric_definition_digest="1" * 64,
        distribution_id="constructed",
        structure_id="one",
        interface_id="one",
        evidence_references=(ref("conditions"),),
    )
    population = EvaluationPopulation(
        capability=CapabilitySpec(contract=source.capability),
        conditions=conditions,
        split="HELD_OUT",
        members=(ref("heldout"),),
        evidence_references=(ref("panel"),),
    )
    training = EvaluationPopulation(
        capability=population.capability,
        conditions=conditions,
        split="TRAIN",
        members=(ref("train"),),
        evidence_references=(ref("training-panel"),),
    )
    points = tuple(
        EvaluationPoint(
            population=population,
            model_id="constructed",
            model_revision=f"revision-{i}",
            sequence_index=i,
            outcomes=(
                CaseOutcome(
                    member_id="heldout",
                    member_digest=canonical_hash("heldout"),
                    value=1,
                    evidence_references=(ref(f"outcome-{i}"),),
                ),
            ),
            evidence_references=(ref(f"point-{i}"),),
            execution_provenance="CONSTRUCTED",
        )
        for i in range(2)
    )
    intervention = TrainingIntervention(
        before_point_id=points[0].record_id,
        after_point_id=points[1].record_id,
        training_population=training,
        trainer_id="constructed",
        trainer_revision="1",
        training_bundle_digest="2" * 64,
        training_configuration_digest="3" * 64,
        evidence_references=(ref("intervention"),),
        execution_provenance="CONSTRUCTED",
    )
    return AcquisitionCurve(
        points=points, interventions=(intervention,), visibility=root_visibility
    )


def test_supplied_flat_curve_is_not_attested_saturation(execution):
    source, _ = execution
    curve = saturation_curve(source)
    assert curve.recorded_metric_deltas == (0.0,)
    result = compile_learning_assets(
        [source],
        saturation_evidence=[curve],
        policy=TransformPolicy(require_saturation_evidence=True),
    )
    assert result.assets == ()
    assert result.saturation_evidence == (curve,)
    assert result.counts["saturated"] is None
    assert result.saturation_status == "UNKNOWN"
    assert result.counts["saturation_unknown"] == 4
    mismatched = replace(
        source,
        capability=type(source.capability).model_validate(
            {**source.capability.model_dump(), "objective": "other", "content_digest": ""}
        ),
    )
    with pytest.raises(ValueError, match="SATURATION_CAPABILITY_BINDING"):
        compile_learning_assets([source], saturation_evidence=[saturation_curve(mismatched)])


def test_private_root_and_modified_wrapper_cannot_gain_eligibility(execution):
    from investigation_world.experience import MachineExperience

    source, _ = execution
    for changes in ({"visibility": "sealed"}, {"private_metadata": {"readiness": "PASS"}}):
        data = source.experience.model_dump(mode="python")
        data.update(changes)
        changed = replace(source, experience=MachineExperience.model_validate(data))
        with pytest.raises(ValueError):
            compile_learning_assets([changed])


def test_cached_verifier_pass_does_not_replace_fresh_failure(execution):
    from investigation_world.experience import machine_experience_from_trajectory
    from investigation_world.trajectory import TrajectoryV2

    source, receipt = execution
    old = receipt.source.verification.model_copy(deep=True)
    old.private_metadata["verification_breakdown"]["outcome"] = 1
    data = source.experience.trajectory.model_dump(mode="python")
    data["reverifications"] = (old,)
    source = replace(
        source, experience=machine_experience_from_trajectory(TrajectoryV2.model_validate(data))
    )
    result = compile_learning_assets([source])
    negative = next(a for a in result.assets if a.transform.kind == "negative")
    assert negative.material["feedback"]["outcome"] < 1


def test_success_is_not_a_negative_and_empty_pool_is_explicit(tmp_path):
    source, _ = record(tmp_path, formula="good")
    result = compile_learning_assets([source])
    assert not any(a.transform.kind == "negative" for a in result.assets)
    assert any(r.reason == "OBSERVED_FAILURE_REQUIRED" for r in result.rejections)
    admit_experience(source, registry=authorized_registry())
    empty = compile_learning_assets([])
    assert empty.assets == empty.sources == empty.receipts == ()
    assert empty.counts["selected"] == 0
    assert empty.counts["saturated"] is None


def test_reidentified_count_tampering_rejects(execution):
    source, _ = execution
    result = compile_learning_assets([source])
    data = result.model_dump(mode="python")
    data["record_id"] = ""
    data["counts"]["selected"] = 100
    with pytest.raises(ValueError, match="COUNT_MISMATCH"):
        type(result).model_validate(data)


def test_exclusion_inputs_and_duplicate_multiplicity_are_bound(tmp_path):
    a, _ = record(tmp_path / "a")
    b, _ = record(tmp_path / "b", formula="=1")
    first = compile_learning_assets(
        [a, a, b], frozen_panel_task_ids=("excluded-task",), frozen_panel_source_digests=("a" * 64,)
    )
    second = compile_learning_assets(
        [a, b, b], frozen_panel_task_ids=("excluded-task",), frozen_panel_source_digests=("a" * 64,)
    )
    assert first.counts == second.counts
    assert first.record_id != second.record_id
    assert first.source_occurrences[a.experience.experience_id] == 2
    assert first.frozen_panel_task_ids == ("excluded-task",)
    assert first.frozen_panel_source_digests == ("a" * 64,)
    with pytest.raises(ValueError, match="COMPILATION_MISMATCH"):
        validate_compilation(first, sources=[a, a, b])
    assert (
        validate_compilation(
            first,
            sources=[b, a, a],
            frozen_panel_task_ids=("excluded-task",),
            frozen_panel_source_digests=("a" * 64,),
        )
        == first
    )


def test_material_dedup_prefers_actual_family_member_not_unbound_alias(tmp_path):
    a, ar = record(tmp_path / "a")
    b, br = record(tmp_path / "b")
    c, cr = record(tmp_path / "c", formula="=1")
    policy = TransformPolicy(rules=(TransformRule(kind="negative"),), per_family_transform_quota=1)
    result = compile_learning_assets([a, b, c], receipts=[ar, br, cr], policy=policy)
    assert result.family_evidence[0].candidate.gap.frequency == 2
    assert len(result.assets) == 1
    assert len(result.assets[0].lineage.family_ids) == 1
    assert result.counts["semantic_alias"] == 1
    assert result.counts["quota"] == 1
    assert result == compile_learning_assets([c, b, a], receipts=[cr, br, ar], policy=policy)


@pytest.mark.parametrize("execution_name", ["baseline", "alternative", "repeated"])
def test_frozen_branch_execution_digest_excludes_derivative_material(execution, execution_name):
    source, receipt = execution
    branch = getattr(receipt, execution_name)
    with pytest.raises(ValueError, match="FROZEN_PANEL"):
        compile_learning_assets(
            [source],
            receipts=[receipt],
            frozen_panel_source_digests=(canonical_hash(branch.experience),),
        )


def test_unbound_semantic_alias_cannot_export_distinct_contrast_material(tmp_path):
    from investigation_world.experience_foundry.admission import public_training_fixture

    a, ar = record(tmp_path / "a")
    b, br = record(tmp_path / "b")
    c, cr = record(tmp_path / "c", formula="=1")
    case, _ = public_training_fixture()
    audit = next(
        r for r in case.episode.public_payload()["records"] if r["record_type"] == "formula_audit"
    )
    receipts = [ar, br, cr]
    for label, source in (("a", a), ("b", b)):
        receipts.append(
            execute_counterfactual_experience(
                source,
                branch_step=0,
                replacement={"cell": audit["object_id"], "formula": audit["fields"]["formula"]},
                artifact_root=tmp_path / f"extra-{label}",
            )
        )
    result = compile_learning_assets(
        [a, b, c], receipts=receipts, policy=TransformPolicy(per_family_transform_quota=1)
    )
    members = set(result.family_evidence[0].source_digests)
    assert all(asset.lineage.source.reference_id in members for asset in result.assets)
    aliases = [r for r in result.rejections if r.reason == "SEMANTIC_SOURCE_ALIAS"]
    assert aliases
    assert all(
        r.source_id not in members and r.evidence["representative_source_id"] in members
        for r in aliases
    )
    assert all(
        r.evidence["alias_receipt"]["digest"] and r.evidence["representative_receipt"]["digest"]
        for r in aliases
    )


def test_exclusion_normalization_precedes_overlap_check(execution):
    source, receipt = execution
    with pytest.raises(ValueError, match="FROZEN_PANEL"):
        compile_learning_assets(
            [source], receipts=[receipt], frozen_panel_task_ids=(source.companion.task_id + " ",)
        )
    with pytest.raises(ValueError):
        compile_learning_assets([source], frozen_panel_task_ids=("   ",))


@pytest.mark.parametrize("classification", ["root", "nested"])
def test_sealed_measurements_cannot_be_reclassified_evaluator_private(execution, classification):
    source, _ = execution
    curve = saturation_curve(
        source,
        **{("root_visibility" if classification == "root" else "reference_visibility"): "sealed"},
    )
    with pytest.raises(ValueError, match="SEALED_SATURATION_EVIDENCE_UNSUPPORTED"):
        compile_learning_assets([source], saturation_evidence=[curve])


def test_private_record_contract_rejects_nested_sealed_policy(execution):
    source, _ = execution
    policy = TransformPolicy(rules=(TransformRule(kind="negative", visibility="sealed"),))
    with pytest.raises(ValueError, match="SEALED_INPUT_REQUIRES_STRICTER_BOUNDARY"):
        compile_learning_assets([source], policy=policy)


def test_nested_sealed_source_annotations_cannot_become_private_identity_references(execution):
    from investigation_world.experience import machine_experience_from_trajectory

    source, _ = execution
    trajectory = source.experience.trajectory.model_copy(deep=True)
    trajectory.private_metadata["constructed_annotation"] = {
        "visibility": "sealed",
        "value": "constructed-only",
    }
    source = replace(source, experience=machine_experience_from_trajectory(trajectory))
    with pytest.raises(ValueError, match="SEALED_SOURCE_EVIDENCE_UNSUPPORTED"):
        compile_learning_assets([source])


def test_nested_sealed_receipt_annotations_reject_before_deriving_hashes(execution):
    source, receipt = execution
    receipt = receipt.model_copy(deep=True)
    receipt.alternative.experience.trajectory.private_metadata["constructed_annotation"] = {
        "visibility": "sealed",
        "value": "constructed-only",
    }
    with pytest.raises(ValueError, match="SEALED_RECEIPT_EVIDENCE_UNSUPPORTED"):
        compile_learning_assets([source], receipts=[receipt])
