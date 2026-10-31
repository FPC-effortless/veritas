"""CONSTRUCTED records test contracts, never empirical capability qualification."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from investigation_world.capability_science.core import CapabilitySpec
from investigation_world.capability_science.measurements import (
    AcquisitionCurve,
    CaseOutcome,
    CompositionTest,
    EvaluationConditions,
    EvaluationPoint,
    EvaluationPopulation,
    RetentionLink,
    TrainingIntervention,
    TransferEvidence,
)
from investigation_world.experience import ExperienceReference
from investigation_world.foundry.models import CapabilityContract
from investigation_world.trajectory import VisibilityClass

PUBLIC = VisibilityClass.PUBLIC
START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def ref(name, digest=None, visibility=PUBLIC):
    return ExperienceReference(
        reference_id=name,
        reference_type="CONSTRUCTED",
        digest=digest * 64 if digest else sha256(name.encode()).hexdigest(),
        visibility=visibility,
    )


def spec(name="repair"):
    return CapabilitySpec(
        contract=CapabilityContract(
            capability_id=name, objective=f"Constructed {name}", success_conditions=["criterion"]
        ),
        visibility=PUBLIC,
    )


def conditions(**changes):
    values = dict(
        environment_id="world",
        environment_revision="world-v1",
        verifier_id="verifier",
        verifier_revision="verifier-v1",
        metric="criterion_score",
        metric_definition_digest="a" * 64,
        distribution_id="distribution-v1",
        structure_id="structure-v1",
        interface_id="interface-v1",
        evidence_references=(ref("conditions"),),
        visibility=PUBLIC,
    )
    values.update(changes)
    return EvaluationConditions(**values)


def population(split="HELD_OUT", capability=None, **changes):
    values = dict(
        capability=capability or spec(),
        conditions=conditions(),
        split=split,
        members=(ref("case-a", "b"), ref("case-b", "c")),
        evidence_references=(ref("frozen-population"),),
        visibility=PUBLIC,
    )
    if split == "TRAIN":
        values["members"] = (ref("train-a", "d"), ref("train-b", "e"))
    values.update(changes)
    return EvaluationPopulation(**values)


def point(index=0, scores=(0.25, 0.75), panel=None, **changes):
    panel = panel or population()
    outcomes = tuple(
        CaseOutcome(
            member_id=member.reference_id,
            member_digest=member.digest,
            value=value,
            evidence_references=(
                ref(f"result-{panel.capability.record_id}-{index}-{member.reference_id}"),
            )
            if value is not None
            else (),
            unavailable_reason="not recorded" if value is None else None,
            visibility=PUBLIC,
        )
        for member, value in zip(panel.members, scores, strict=True)
    )
    values = dict(
        population=panel,
        model_id="model",
        model_revision=f"checkpoint-{index}",
        sequence_index=index,
        observed_at=START + timedelta(hours=3 * index),
        outcomes=outcomes,
        execution_provenance="CONSTRUCTED",
        evidence_references=(ref(f"evaluation-{panel.capability.record_id}-{index}"),),
        visibility=PUBLIC,
    )
    values.update(changes)
    return EvaluationPoint(**values)


def intervention(before, after, **changes):
    values = dict(
        before_point_id=before.record_id,
        after_point_id=after.record_id,
        training_population=population("TRAIN"),
        trainer_id="external-trainer",
        trainer_revision="trainer-v1",
        training_bundle_digest="f" * 64,
        training_configuration_digest="a" * 64,
        started_at=before.observed_at + timedelta(hours=1) if before.observed_at else None,
        finished_at=before.observed_at + timedelta(hours=2) if before.observed_at else None,
        execution_provenance="CONSTRUCTED",
        evidence_references=(ref("intervention"),),
        visibility=PUBLIC,
    )
    values.update(changes)
    return TrainingIntervention(**values)


def curve(scores=(0.75, 0.75), **changes):
    before, after = point(), point(1, scores)
    values = dict(
        points=(before, after), interventions=(intervention(before, after),), visibility=PUBLIC
    )
    values.update(changes)
    return AcquisitionCurve(**values)


def test_complete_fixed_population_retains_positive_zero_negative_and_unknown_results():
    positive = curve()
    assert positive.recorded_metric_deltas == (0.25,)
    assert curve((0.25, 0.75)).recorded_metric_deltas == (0.0,)
    assert curve((0.0, 0.0)).recorded_metric_deltas == (-0.5,)
    missing = curve((None, 0.75))
    assert missing.recorded_metric_deltas == (None,)
    assert len(missing.points[1].outcomes) == 2
    assert positive.capability_gain is None
    assert positive.model_execution_attestation == "UNKNOWN"
    assert positive.chronology_attestation == "UNKNOWN"
    assert positive == AcquisitionCurve.model_validate(positive.model_dump(mode="python"))


@pytest.mark.parametrize("change", ["missing", "duplicate", "substituted"])
def test_population_completeness_never_uses_success_filtered_intersections(change):
    base = point()
    rows = base.outcomes
    if change == "missing":
        rows = rows[:1]
    elif change == "duplicate":
        rows = (rows[0], rows[0])
    else:
        rows = (rows[0], rows[1].model_copy(update={"member_id": "replacement", "record_id": ""}))
    with pytest.raises(ValueError, match="population|member"):
        point(outcomes=rows)


@pytest.mark.parametrize(
    "changes",
    [
        {"members": (ref("x", "b"), ref("x", "c"))},
        {"members": (ref("x", "b"), ref("y", "b"))},
        {"members": ()},
    ],
)
def test_duplicate_and_empty_population_rejected(changes):
    with pytest.raises(ValueError):
        population(**changes)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -0.01, 1.01])
def test_nonfinite_or_out_of_range_scores_rejected(value):
    with pytest.raises(ValueError):
        point(scores=(value, 1.0))


def test_unknown_outcome_needs_reason_and_known_outcome_needs_evidence():
    with pytest.raises(ValueError):
        CaseOutcome(member_id="x", value=None)
    with pytest.raises(ValueError):
        CaseOutcome(member_id="x", value=0.2)
    with pytest.raises(ValueError):
        CaseOutcome(
            member_id="x",
            value=0.2,
            evidence_references=(ref("x"),),
            unavailable_reason="contradiction",
        )


def test_outcome_digest_must_bind_exact_population_source_not_just_name():
    base = point()
    bad = base.outcomes[0].model_copy(update={"record_id": "", "member_digest": "f" * 64})
    with pytest.raises(ValueError, match="source"):
        point(outcomes=(bad, base.outcomes[1]))


@pytest.mark.parametrize("revision", ["unknown", "unspecified", "latest", "main", "HEAD"])
def test_model_revision_is_not_an_unpinned_placeholder(revision):
    with pytest.raises(ValueError, match="revision"):
        point(model_revision=revision)


@pytest.mark.parametrize(
    "field", ["environment_id", "verifier_id", "distribution_id", "structure_id", "interface_id"]
)
def test_unknown_conditions_cannot_be_declared_as_known_transfer_scope(field):
    with pytest.raises(ValueError, match="identity"):
        conditions(**{field: "unknown"})


def test_unknown_model_and_trainer_identities_are_not_pinned_by_a_nonblank_revision():
    with pytest.raises(ValueError, match="identity"):
        point(model_id="unknown")
    before, after = point(), point(1)
    with pytest.raises(ValueError, match="identity"):
        intervention(before, after, trainer_id="unknown")


@pytest.mark.parametrize(
    "changes",
    [
        {"conditions": conditions(verifier_revision="different")},
        {"conditions": conditions(metric_definition_digest="e" * 64)},
        {"members": (ref("replacement", "f"), ref("case-b", "c"))},
        {"capability": spec("unrelated")},
    ],
)
def test_curves_reject_population_metric_verifier_or_capability_drift(changes):
    before, after = point(), point(1, panel=population(**changes))
    with pytest.raises(ValueError, match="population"):
        curve(points=(before, after), interventions=(intervention(before, after),))


def test_intervention_and_sequence_binding_reject_forgery_and_skips():
    before, after = point(), point(2)
    with pytest.raises(ValueError, match="sequence"):
        curve(points=(before, after), interventions=(intervention(before, after),))
    before, after = point(), point(1)
    bad = intervention(before, after, before_point_id="foreign")
    with pytest.raises(ValueError, match="binding"):
        curve(points=(before, after), interventions=(bad,))
    with pytest.raises(ValueError):
        curve(interventions=())


@pytest.mark.parametrize("which", ["before", "after", "reversed", "naive"])
def test_known_chronology_contradictions_fail_closed(which):
    before, after = point(), point(1)
    changes = {
        "before": {"started_at": START - timedelta(hours=1)},
        "after": {"finished_at": after.observed_at + timedelta(hours=1)},
        "reversed": {
            "started_at": START + timedelta(hours=2),
            "finished_at": START + timedelta(hours=1),
        },
        "naive": {"started_at": START.replace(tzinfo=None)},
    }[which]
    with pytest.raises(ValueError, match="chronology|timezone"):
        step = intervention(before, after, **changes)
        curve(points=(before, after), interventions=(step,))


def test_missing_chronology_and_unattested_execution_do_not_get_promoted():
    before, after = (
        point(observed_at=None),
        point(1, observed_at=None, execution_provenance="UNKNOWN"),
    )
    result = curve(points=(before, after), interventions=(intervention(before, after),))
    assert result.recorded_metric_deltas == (0.0,)
    assert result.chronology_attestation == "UNKNOWN"
    assert result.model_execution_attestation == "UNKNOWN"
    assert result.capability_gain is None


@pytest.mark.parametrize(
    "changes",
    [
        {"model_execution_attestation": "PASS"},
        {"chronology_attestation": "PASS"},
        {"capability_gain": 0.25},
    ],
)
def test_recorded_arithmetic_cannot_be_self_promoted_to_attested_capability(changes):
    with pytest.raises(ValueError):
        curve(**changes)


def test_raw_task_count_and_training_loss_are_not_capability_metrics():
    for metric in ("task_count", "training_loss"):
        with pytest.raises(ValueError):
            conditions(metric=metric)
    with pytest.raises(ValueError, match="binary"):
        point(panel=population(conditions=conditions(metric="success_fraction")))


def test_frozen_curve_cannot_silently_omit_intermediate_interventions():
    a, b, c = point(), point(1), point(2)
    result = curve(points=(a, b, c), interventions=(intervention(a, b), intervention(b, c)))
    assert result.recorded_metric_deltas == (0.0, 0.0)
    with pytest.raises(ValueError, match="exactly one"):
        curve(points=(a, b, c), interventions=(intervention(a, c),))


def test_retention_zero_baseline_is_only_retained_recorded_performance():
    link = RetentionLink(
        acquired=point(scores=(0.0, 0.0)),
        later=point(2, (0.0, 0.0)),
        intervention_references=(ref("intervening-step"),),
    )
    assert link.recorded_relation == "RETAINED"
    assert link.capability_gain is None


def test_record_identity_binds_intervention_configuration_and_all_outcomes():
    original = curve()
    step = original.interventions[0]
    changed = TrainingIntervention.model_validate(
        {
            **step.model_dump(mode="python"),
            "record_id": "",
            "training_configuration_digest": "e" * 64,
        }
    )
    altered = curve(interventions=(changed,))
    assert altered.record_id != original.record_id
    assert curve((0.5, 1.0)).record_id != original.record_id
    with pytest.raises(ValueError):
        original.model_copy(update={"points": (point(), point(1, (0.0, 0.0)))}).checked()


def test_retention_links_use_same_panel_keep_negative_and_unknown():
    prior = point(scores=(1.0, 1.0))
    later = point(2, (0.25, 0.75))
    link = RetentionLink(
        acquired=prior,
        later=later,
        intervention_references=(ref("intervening-step"),),
        visibility=PUBLIC,
    )
    assert link.recorded_metric_delta == -0.5
    assert link.recorded_relation == "REGRESSION"
    unknown = RetentionLink(
        acquired=prior,
        later=point(2, (None, 1.0)),
        intervention_references=(ref("intervening-step"),),
    )
    assert unknown.recorded_relation == "UNKNOWN"
    with pytest.raises(ValueError, match="population"):
        RetentionLink(
            acquired=prior,
            later=point(2, panel=population(capability=spec("other"))),
            intervention_references=(ref("intervening-step"),),
        )
    with pytest.raises(ValueError, match="sequence"):
        RetentionLink(
            acquired=later, later=prior, intervention_references=(ref("intervening-step"),)
        )


def composition(composed_scores=(1.0, 1.0), **changes):
    a, b, target = spec("identify"), spec("repair"), spec("identify-and-repair")
    values = dict(
        target=target,
        required_components=(a, b),
        component_evaluations=(
            point(scores=(1.0, 1.0), panel=population(capability=a)),
            point(scores=(1.0, 1.0), panel=population(capability=b)),
        ),
        composed_evaluation=point(scores=composed_scores, panel=population(capability=target)),
        criterion_digest="f" * 64,
        minimum_score=1.0,
        evidence_references=(ref("composition-protocol"),),
        visibility=PUBLIC,
    )
    values.update(changes)
    return CompositionTest(**values)


def test_composition_needs_actual_composed_result_not_successful_components():
    assert composition().recorded_result == "PASS"
    assert composition((0.0, 1.0)).recorded_result == "FAIL"
    assert composition((None, 1.0)).recorded_result == "UNKNOWN"
    with pytest.raises(ValueError):
        composition(component_evaluations=())
    with pytest.raises(ValueError, match="component"):
        composition(required_components=(spec("absent"), spec("repair")))
    with pytest.raises(ValueError, match="target"):
        composition(composed_evaluation=point())


def test_composition_rejects_relabeling_component_evidence_as_composed_evidence():
    result = composition()
    component = result.component_evaluations[0]
    payload = result.composed_evaluation.model_dump(mode="python")
    payload["record_id"] = ""
    payload["evidence_references"] = component.evidence_references
    with pytest.raises(ValueError, match="distinct"):
        composition(composed_evaluation=EvaluationPoint.model_validate(payload))


def test_composition_cannot_mix_model_checkpoints_or_verifier_semantics():
    result = composition()
    a, b = result.required_components
    with pytest.raises(ValueError, match="checkpoint"):
        composition(
            component_evaluations=(
                point(scores=(1.0, 1.0), panel=population(capability=a), model_revision="other"),
                point(scores=(1.0, 1.0), panel=population(capability=b)),
            )
        )
    with pytest.raises(ValueError, match="semantics"):
        composition(
            component_evaluations=(
                point(
                    scores=(1.0, 1.0),
                    panel=population(
                        capability=a, conditions=conditions(verifier_revision="different")
                    ),
                ),
                point(scores=(1.0, 1.0), panel=population(capability=b)),
            )
        )


def transfer(source_changes=None, target_changes=None, source_model="model"):
    train = population("TRAIN", conditions=conditions(**(source_changes or {})))
    panel = population(conditions=conditions(**(target_changes or {})))
    before, after = point(panel=panel), point(1, (0.0, 0.0), panel=panel)
    target = curve(
        points=(before, after),
        interventions=(intervention(before, after, training_population=train),),
    )
    return TransferEvidence(
        source=point(panel=train, model_id=source_model),
        target=target,
        evidence_references=(ref("transfer-protocol"),),
        visibility=PUBLIC,
    )


@pytest.mark.parametrize(
    "target_changes,source_model,expected",
    [
        ({}, "model", ("IID",)),
        ({"structure_id": "new-structure"}, "model", ("STRUCTURAL_OOD",)),
        ({"distribution_id": "new-distribution"}, "model", ("STRUCTURAL_OOD",)),
        ({"environment_revision": "world-v2"}, "model", ("STRUCTURAL_OOD",)),
        ({"interface_id": "new-interface"}, "model", ("INTERFACE_TOOL",)),
        ({}, "source-model", ("CROSS_MODEL",)),
        (
            {"structure_id": "new", "interface_id": "new"},
            "source-model",
            ("STRUCTURAL_OOD", "INTERFACE_TOOL", "CROSS_MODEL"),
        ),
    ],
)
def test_transfer_classifies_evidenced_scope_and_retains_negative_results(
    target_changes, source_model, expected
):
    result = transfer(target_changes=target_changes, source_model=source_model)
    assert result.classifications == expected
    assert result.recorded_metric_delta == -0.5
    assert result.capability_gain is None


def test_training_set_scores_cannot_masquerade_as_heldout_transfer():
    train = population("TRAIN")
    before, after = point(panel=train), point(1, panel=train)
    target = curve(points=(before, after), interventions=(intervention(before, after),))
    with pytest.raises(ValueError, match="held.out"):
        TransferEvidence(source=before, target=target, evidence_references=(ref("protocol"),))


@pytest.mark.parametrize("collision", ["id", "digest"])
def test_transfer_rejects_training_target_overlap_by_id_or_content(collision):
    train = population("TRAIN")
    member = ref(
        "train-a" if collision == "id" else "unrelated", "d" if collision == "digest" else "b"
    )
    panel = population(members=(member, ref("case-b", "c")))
    before, after = point(panel=panel), point(1, panel=panel)
    with pytest.raises(ValueError, match="overlap"):
        target = curve(points=(before, after), interventions=(intervention(before, after),))
        TransferEvidence(
            source=point(panel=train), target=target, evidence_references=(ref("protocol"),)
        )


@pytest.mark.parametrize(
    "change",
    [
        {"verifier_revision": "other"},
        {"metric_definition_digest": "f" * 64},
    ],
)
def test_transfer_does_not_call_different_measurement_semantics_iid(change):
    with pytest.raises(ValueError, match="semantics"):
        transfer(target_changes=change)


def test_private_evidence_suppresses_whole_projection_and_private_identity():
    private = ref("SECRET-PANEL", visibility=VisibilityClass.EVALUATOR_PRIVATE)
    panel = population(evidence_references=(private,))
    item = point(panel=panel)
    for rendered in (item.public_payload(), item.buyer_safe_payload()):
        assert rendered["status"] == "UNKNOWN"
        assert "SECRET" not in str(rendered)
        assert item.record_id not in str(rendered)


def test_material_roundtrip_and_public_constructed_projection():
    result = transfer()
    assert result == TransferEvidence.model_validate_json(result.model_dump_json())
    projected = result.public_payload()
    assert projected["record_id"] == result.record_id
    assert projected["source"]["execution_provenance"] == "CONSTRUCTED"
