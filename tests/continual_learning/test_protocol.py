"""CONSTRUCTED multi-step records; no model execution or scientific qualification."""

from datetime import datetime, timedelta, timezone
from hashlib import sha256

import pytest

from investigation_world.capability_science import (
    AcquisitionCurve,
    CaseOutcome,
    EvaluationConditions,
    EvaluationPoint,
    EvaluationPopulation,
    TrainingIntervention,
)
from investigation_world.capability_science.core import CapabilitySpec
from investigation_world.continual_learning import (
    ContinualEvidence,
    ContinualPlan,
    ContinualPolicy,
    ExperimentHistory,
    ExternalLearner,
    PanelPlan,
    Replicate,
    ScheduledStep,
    StepRun,
    assess_continual_learning,
)
from investigation_world.experience import ExperienceReference, ExperienceSequence
from investigation_world.foundry.models import CapabilityContract, DistributionSplit
from investigation_world.foundry.training_product import (
    TrainerKind,
    TrainingBundle,
    TrainingExample,
    TrainingRecipe,
    TrainingRunManifest,
)
from investigation_world.trajectory import canonical_hash

NOW = datetime(2026, 1, 1, tzinfo=timezone.utc)


def digest(value):
    return sha256(value.encode()).hexdigest()


def ref(name):
    return ExperienceReference(reference_id=name, reference_type="CONSTRUCTED", digest=digest(name))


def replace(record, **changes):
    payload = record.model_dump(mode="python")
    payload.update(changes)
    payload["record_id"] = ""
    return type(record).model_validate(payload)


def population(name, split="HELD_OUT"):
    return EvaluationPopulation(
        capability=CapabilitySpec(contract=CapabilityContract(capability_id=name, objective=name)),
        conditions=EvaluationConditions(
            environment_id="world",
            environment_revision="v1",
            verifier_id="verifier",
            verifier_revision="v1",
            metric="criterion_score",
            metric_definition_digest=digest("metric"),
            distribution_id=name,
            structure_id="structure-v1",
            interface_id="interface-v1",
            evidence_references=(ref("conditions"),),
        ),
        split=split,
        members=(ref(f"{split}-{name}-0"), ref(f"{split}-{name}-1")),
        evidence_references=(ref(f"population-{split}-{name}"),),
    )


def step(index, name):
    train = population(name, "TRAIN")
    ids = tuple(f"experience-{name}-{i}" for i in range(2))
    bundle = TrainingBundle(
        bundle_id=f"bundle-{name}",
        capability_contract=train.capability.contract,
        recipe=TrainingRecipe(
            recipe_id=f"recipe-{name}", trainer=TrainerKind.SFT, capability_contract_id=name
        ),
        train_examples=[
            TrainingExample(
                example_id=m.reference_id,
                trajectory_id=f"verified-{name}-{i}",
                task_id=m.reference_id,
                split=DistributionSplit.TRAIN,
                trainer=TrainerKind.SFT,
                trace_ref="CONSTRUCTED",
                verifier_score=1,
            )
            for i, m in enumerate(train.members)
        ],
        metadata={
            "verified_learning_lineage": [
                dict(
                    verified_trajectory_id=f"verified-{name}-{i}",
                    task_id=m.reference_id,
                    source_id=m.reference_id,
                    source_digest=m.digest,
                    fixture_digest=digest("fixture-" + m.reference_id),
                    experience_id=ids[i],
                    trajectory_id=f"original-{name}-{i}",
                )
                for i, m in enumerate(train.members)
            ]
        },
    )
    return ScheduledStep(
        index=index,
        new_experience_ids=ids,
        bundle=bundle,
        training_population=train,
        learner=ExternalLearner(
            backend_id="external",
            backend_revision="v1",
            configuration_digest=canonical_hash({}),
            evidence_references=(ref("backend-metadata"),),
        ),
    )


def plan():
    steps = (step(1, "a"), step(2, "b"))
    return ContinualPlan(
        sequence=ExperienceSequence(
            experience_ids=tuple(x for s in steps for x in s.new_experience_ids)
        ),
        steps=steps,
        model_id="model",
        baseline_revision="base-v1",
        expected_seeds=(1, 2),
        panels=(
            PanelPlan(population=population("a"), reference_step=1),
            PanelPlan(population=population("b"), reference_step=2),
            PanelPlan(population=population("guard"), role="guardrail", reference_step=0),
        ),
        evidence_references=(ref("plan"),),
    )


def point(panel, seed, index, score, *, control=False):
    prefix = "control" if control else "evaluation"
    name = f"{prefix}-{panel.capability.contract.capability_id}-{seed}-{index}"
    return EvaluationPoint(
        population=panel,
        model_id="model",
        model_revision="base-v1" if index == 0 else f"checkpoint-{seed}-{index}",
        sequence_index=index,
        observed_at=NOW + timedelta(hours=3 * index, minutes=-1 if control else 0),
        outcomes=tuple(
            CaseOutcome(
                member_id=m.reference_id,
                member_digest=m.digest,
                value=score,
                evidence_references=(ref(f"{name}-outcome-{i}"),) if score is not None else (),
                unavailable_reason="CONSTRUCTED missing" if score is None else None,
            )
            for i, m in enumerate(panel.members)
        ),
        evidence_references=(ref(name),),
        execution_provenance="CONSTRUCTED",
    )


def evidence(*, scores=None, controls=True, seeds=(1, 2), p=None):
    p = p or plan()
    scores = scores or ((0.2, 0.8, 0.6), (0.1, 0.3, 0.9), (0.8, 0.8, 0.8))
    reps = []
    for seed in seeds:
        runs = tuple(
            StepRun(
                before_checkpoint="base-v1" if s.index == 1 else f"checkpoint-{seed}-{s.index - 1}",
                after_checkpoint=f"checkpoint-{seed}-{s.index}",
                manifest=TrainingRunManifest(
                    run_id=f"run-{seed}-{s.index}",
                    bundle_id=s.bundle.bundle_id,
                    trainer=TrainerKind.SFT,
                    base_model=p.model_id,
                    trainer_version=s.learner.backend_revision,
                    seed=seed,
                ),
            )
            for s in p.steps
        )
        curves = []
        for pp, values in zip(p.panels, scores, strict=True):
            points = tuple(point(pp.population, seed, i, value) for i, value in enumerate(values))
            interventions = tuple(
                TrainingIntervention(
                    before_point_id=points[i].record_id,
                    after_point_id=points[i + 1].record_id,
                    training_population=s.training_population,
                    trainer_id=s.learner.backend_id,
                    trainer_revision=s.learner.backend_revision,
                    training_bundle_digest=canonical_hash(s.bundle),
                    training_configuration_digest=s.learner.configuration_digest,
                    started_at=NOW + timedelta(hours=i * 3 + 1),
                    finished_at=NOW + timedelta(hours=i * 3 + 2),
                    execution_provenance="CONSTRUCTED",
                    evidence_references=(runs[i].declaration_reference,),
                )
                for i, s in enumerate(p.steps)
            )
            curves.append(AcquisitionCurve(points=points, interventions=interventions))
        reps.append(
            Replicate(
                seed=seed,
                curves=tuple(curves),
                runs=runs,
                forward_controls=(point(p.panels[1].population, seed, 0, 0.1, control=True),)
                if controls
                else (),
            )
        )
    return ContinualEvidence(plan=p, replicates=tuple(reps), provenance="CONSTRUCTED")


def test_constructed_metrics_preserve_forgetting_negative_transfer_and_unknown_attestation():
    e = evidence()
    report = assess_continual_learning(e)
    row = next(
        r
        for r in report.measurements
        if r.seed == 1 and r.panel_id == e.plan.panels[0].record_id and r.step == 2
    )
    assert row.recorded_retention == pytest.approx(0.6)
    assert row.recorded_backward_transfer == pytest.approx(-0.2)
    assert row.recorded_forgetting == pytest.approx(0.2)
    future = next(
        r
        for r in report.measurements
        if r.seed == 1 and r.panel_id == e.plan.panels[1].record_id and r.step == 1
    )
    assert future.recorded_forward_transfer == pytest.approx(0.2)
    assert report.status == "UNKNOWN"
    assert report.capability_gain is None
    assert report.demonstrated_continual_learning == "UNKNOWN"
    assert report.e7_promotion is False


def gates(report):
    return {g.name: g.outcome for g in report.gates}


def changed_curve(curve, *, points=None, interventions=None):
    points = points or curve.points
    interventions = interventions or curve.interventions
    return replace(
        curve,
        points=points,
        interventions=tuple(
            replace(s, before_point_id=b.record_id, after_point_id=a.record_id)
            for s, b, a in zip(interventions, points, points[1:], strict=False)
        ),
    )


def with_curve(e, curve, *, panel=0, replicate=0):
    reps = list(e.replicates)
    curves = list(reps[replicate].curves)
    curves[panel] = curve
    reps[replicate] = replace(reps[replicate], curves=tuple(curves))
    return replace(e, replicates=tuple(reps))


@pytest.mark.parametrize(
    "scores, expected",
    [
        (((0.2, 0.8, 0.9), (0.1, 0.3, 0.9), (0.8, 0.8, 0.8)), 0.1),
        (((0.2, 0.8, 0.8), (0.1, 0.3, 0.9), (0.8, 0.8, 0.8)), 0.0),
        (((0.2, 0.8, 0.1), (0.1, 0.0, 0.9), (0.8, 0.8, 0.6)), -0.7),
    ],
)
def test_signed_recorded_transfer_and_catastrophic_guardrail_failures(scores, expected):
    report = assess_continual_learning(evidence(scores=scores))
    assert report.mean_final_recorded_backward_transfer == pytest.approx(expected)
    if expected < -0.5:
        assert report.status == "FAIL"
        assert gates(report)["catastrophic_forgetting"] == "FAIL"
        assert gates(report)["guardrails"] == "FAIL"
        assert any(r.recorded_forward_transfer == pytest.approx(-0.1) for r in report.measurements)
    else:
        assert gates(report)["retention"] == "PASS"
        assert report.status == "UNKNOWN"


def test_missing_control_retains_arithmetic_but_forward_transfer_unknown():
    report = assess_continual_learning(evidence(controls=False))
    assert all(r.recorded_forward_transfer is None for r in report.measurements)
    assert gates(report)["forward_controls"] == "UNKNOWN"
    assert report.mean_final_recorded_backward_transfer == pytest.approx(-0.2)


def test_missing_outcomes_not_dropped_or_success_filtered():
    report = assess_continual_learning(
        evidence(scores=((0.2, 0.8, None), (0.1, 0.3, 0.9), (0.8, 0.8, 0.8)))
    )
    assert len(report.measurements) == 18
    assert gates(report)["complete_outcomes"] == "UNKNOWN"
    assert gates(report)["retention"] == "UNKNOWN"
    assert report.mean_final_recorded_backward_transfer is None
    assert all(
        r.recorded_forgetting is None
        for r in report.measurements
        if r.panel_id == report.evidence.plan.panels[0].record_id and r.step == 2
    )


@pytest.mark.parametrize("seeds", [(), (1,)])
def test_missing_replicates_never_form_complete_aggregate(seeds):
    report = assess_continual_learning(evidence(seeds=seeds))
    assert gates(report)["complete_replicates"] == "UNKNOWN"
    assert gates(report)["replicate_stability"] == "UNKNOWN"
    assert report.mean_final_recorded_backward_transfer is None
    assert report.status == "UNKNOWN"


def test_policy_requires_all_recorded_seeds_including_bad_seed():
    e = evidence()
    bad = evidence(scores=((0.2, 0.8, 0.0), (0.1, 0.3, 0.9), (0.8, 0.8, 0.8))).replicates[1]
    report = assess_continual_learning(replace(e, replicates=(e.replicates[0], bad)))
    assert gates(report)["replicate_stability"] == "FAIL"
    assert gates(report)["catastrophic_forgetting"] == "FAIL"
    assert report.mean_final_recorded_backward_transfer == pytest.approx(-0.5)


@pytest.mark.parametrize(
    "changes",
    [
        {"expected_seeds": (1, 1)},
        {"expected_seeds": (True, 2)},
        {"expected_seeds": (-1, 2)},
        {"expected_seeds": (2**32, 2)},
        {"baseline_revision": "latest"},
        {"model_id": "unknown"},
    ],
)
def test_plan_rejects_bad_seed_and_unpinned_model(changes):
    with pytest.raises(ValueError):
        replace(plan(), **changes)


def test_one_finetuning_run_cannot_satisfy_multistep_protocol():
    p = plan()
    with pytest.raises(ValueError):
        replace(p, steps=p.steps[:1])


def test_schedule_order_and_reference_cannot_be_silently_rewritten():
    p = plan()
    with pytest.raises(ValueError, match="ExperienceSequence"):
        replace(
            p,
            sequence=ExperienceSequence(experience_ids=tuple(reversed(p.sequence.experience_ids))),
        )
    with pytest.raises(ValueError, match="contiguous"):
        replace(p, steps=(p.steps[1], p.steps[0]))
    with pytest.raises(ValueError, match="first scheduled"):
        replace(p, panels=(replace(p.panels[0], reference_step=2), *p.panels[1:]))
    with pytest.raises(ValueError, match="transfer"):
        replace(
            p,
            sequence=ExperienceSequence(
                experience_ids=p.sequence.experience_ids,
                transfer_test_experience_ids=(p.sequence.experience_ids[0],),
            ),
        )


@pytest.mark.parametrize(
    "change", ["missing_panel", "duplicate_panel", "missing_run", "duplicate_seed", "unknown_seed"]
)
def test_complete_matrix_and_run_membership(change):
    e = evidence()
    rep = e.replicates[0]
    with pytest.raises(ValueError):
        if change == "missing_panel":
            replace(e, replicates=(replace(rep, curves=rep.curves[:2]), e.replicates[1]))
        elif change == "duplicate_panel":
            replace(
                e,
                replicates=(
                    replace(rep, curves=(rep.curves[0], rep.curves[0], rep.curves[2])),
                    e.replicates[1],
                ),
            )
        elif change == "missing_run":
            replace(e, replicates=(replace(rep, runs=rep.runs[:1]), e.replicates[1]))
        elif change == "duplicate_seed":
            replace(e, replicates=(rep, rep))
        else:
            replace(e, replicates=(replace(rep, seed=9), e.replicates[1]))


def test_omitted_step_even_valid_shorter_curve_rejected():
    e = evidence()
    curve = e.replicates[0].curves[0]
    short = replace(curve, points=curve.points[:2], interventions=curve.interventions[:1])
    with pytest.raises(ValueError, match="omit"):
        with_curve(e, short)


def test_drifted_population_is_not_intersection_scored():
    e = evidence()
    curve = e.replicates[0].curves[0]
    changed = replace(
        curve.points[1].population,
        conditions=replace(curve.points[1].population.conditions, verifier_revision="v2"),
    )
    points = (curve.points[0], replace(curve.points[1], population=changed), curve.points[2])
    with pytest.raises(ValueError, match="population"):
        changed_curve(curve, points=points)


@pytest.mark.parametrize(
    "change", ["outcome_reference", "renamed_same_digest", "model", "checkpoint"]
)
def test_reused_and_substituted_evaluation_evidence_rejected(change):
    e = evidence()
    curve = e.replicates[0].curves[0]
    after = curve.points[2]
    if change == "point_reference":
        after = replace(after, evidence_references=curve.points[1].evidence_references)
    elif change == "outcome_reference":
        outcome = replace(
            after.outcomes[0], evidence_references=curve.points[1].outcomes[0].evidence_references
        )
        after = replace(after, outcomes=(outcome, after.outcomes[1]))
    elif change == "renamed_same_digest":
        r = curve.points[1].outcomes[0].evidence_references[0]
        r = r.model_copy(update={"reference_id": "renamed"})
        after = replace(
            after,
            outcomes=(replace(after.outcomes[0], evidence_references=(r,)), after.outcomes[1]),
        )
    elif change == "model":
        after = replace(after, model_id="substituted-model")
    else:
        after = replace(after, model_revision="substituted-checkpoint")
    with pytest.raises(ValueError, match="evidence|model|checkpoint"):
        with_curve(e, changed_curve(curve, points=(*curve.points[:2], after)))


@pytest.mark.parametrize(
    "field, value",
    [
        ("seed", 9),
        ("bundle_id", "other"),
        ("base_model", "other"),
        ("trainer_version", "v2"),
        ("parameters", {"changed": True}),
    ],
)
def test_external_run_manifest_must_match_schedule(field, value):
    e = evidence()
    rep = e.replicates[0]
    manifest = rep.runs[0].manifest.model_copy(update={field: value})
    with pytest.raises(ValueError, match="manifest"):
        replace(
            e,
            replicates=(
                replace(rep, runs=(replace(rep.runs[0], manifest=manifest), rep.runs[1])),
                e.replicates[1],
            ),
        )


@pytest.mark.parametrize("change", ["late", "wrong_checkpoint", "reused", "duplicate"])
def test_forward_control_must_be_independent_exact_prelearning_baseline(change):
    e = evidence()
    rep = e.replicates[0]
    control = rep.forward_controls[0]
    if change == "late":
        controls = (replace(control, observed_at=NOW + timedelta(hours=4)),)
    elif change == "wrong_checkpoint":
        controls = (replace(control, model_revision="trained-v1"),)
    elif change == "reused":
        controls = (rep.curves[1].points[0],)
    else:
        controls = (control, control)
    with pytest.raises(ValueError, match="control"):
        replace(e, replicates=(replace(rep, forward_controls=controls), e.replicates[1]))


def test_missing_control_chronology_stays_unknown():
    e = evidence()
    reps = tuple(
        replace(r, forward_controls=(replace(r.forward_controls[0], observed_at=None),))
        for r in e.replicates
    )
    report = assess_continual_learning(replace(e, replicates=reps))
    assert gates(report)["forward_controls"] == "UNKNOWN"


def test_wrong_backend_or_bundle_intervention_rejected():
    e = evidence()
    curve = e.replicates[0].curves[0]
    for field, value in (
        ("trainer_id", "other"),
        ("training_bundle_digest", digest("other")),
        ("training_configuration_digest", digest("config")),
    ):
        step = replace(curve.interventions[0], **{field: value})
        with pytest.raises(ValueError, match="intervention"):
            with_curve(e, changed_curve(curve, interventions=(step, curve.interventions[1])))


def test_report_tampering_and_self_asserted_promotion_fail_closed():
    report = assess_continual_learning(evidence())
    with pytest.raises(ValueError, match="recomputed"):
        replace(report, mean_final_recorded_backward_transfer=100)
    for changes in (
        {"demonstrated_continual_learning": "PASS"},
        {"capability_gain": 0.5},
        {"e7_promotion": True},
        {"status": "PASS"},
    ):
        with pytest.raises(ValueError):
            replace(report, **changes)
    assert report.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    assert report.buyer_safe_payload() == report.public_payload()


def test_nested_mutation_detected_at_consumption():
    e = evidence()
    e.plan.steps[0].bundle.metadata["verified_learning_lineage"][0]["source_digest"] = digest(
        "substitute"
    )
    with pytest.raises(ValueError):
        assess_continual_learning(e)


def test_history_append_preserves_prefix_and_requires_storage_commitment():
    report = assess_continual_learning(evidence())
    original = ExperimentHistory(plan=report.evidence.plan)
    first = original.append(report, expected_previous_commitment=original.record_id)
    second = first.append(report, expected_previous_commitment=first.record_id)
    assert original.revisions == ()
    assert second.revisions[:1] == first.revisions
    assert second.revisions[1].previous_record_id == first.revisions[0].record_id
    with pytest.raises(ValueError, match="commitment"):
        original.append(report, expected_previous_commitment=first.record_id)
    with pytest.raises(ValueError, match="chain"):
        replace(second, revisions=(second.revisions[1], second.revisions[0]))
    with pytest.raises(ValueError, match="chain"):
        replace(second, revisions=second.revisions[1:])
    with pytest.raises(ValueError):
        first.append(report, expected_previous_commitment="")


def test_report_and_history_roundtrip_and_no_public_leak():
    report = assess_continual_learning(evidence())
    assert type(report).model_validate_json(report.model_dump_json()) == report
    history = ExperimentHistory(plan=report.evidence.plan)
    history = history.append(report, expected_previous_commitment=history.record_id)
    assert ExperimentHistory.model_validate_json(history.model_dump_json()) == history
    assert history.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}


def replay_plan():
    from investigation_world.experience_selection.selection import (
        Decision,
        SelectionPolicy,
        SelectionReport,
        SelectionResources,
    )

    p = plan()
    first, second = p.steps
    rows = first.bundle.metadata["verified_learning_lineage"]
    selected = tuple(
        Decision(
            slot_id=f"slot-{i}",
            input_digest=digest(f"input-{i}"),
            experience_id=row["experience_id"],
            reason="selected",
            role="verified_success_candidate",
            protocol_digest=digest(f"protocol-{i}"),
            gap_record_ids=(f"gap-{i}",),
            verification_id=f"verification-{i}",
            source_fixture_digest=row["fixture_digest"],
        )
        for i, row in enumerate(rows)
    )
    policy = SelectionPolicy(
        max_items=2,
        heldout_task_ids=tuple(m.reference_id for pp in p.panels for m in pp.population.members),
        heldout_source_digests=tuple(m.digest for pp in p.panels for m in pp.population.members),
    )
    selection = SelectionReport(
        policy=policy,
        pool_id="CONSTRUCTED-pool",
        gap_input_digest=digest("gap-input"),
        gaps=(),
        eligibility_digest=digest("eligibility"),
        decisions=selected,
        selected_count=2,
        rejected_count=0,
        rejection_counts={},
        resources=SelectionResources(
            pool_entries=2,
            unique_input_snapshots=2,
            unique_validated_recordings=2,
            candidate_validation_attempts=2,
            training_admission_attempts=2,
            gap_input_protocols=2,
            distinct_gap_protocols=2,
            gap_receipt_validation_calls=2,
            gap_family_derivation_calls=2,
            selected_entries=2,
            rejected_entries=0,
            recorded_gap_execution_cost=0,
        ),
    )
    bundle = second.bundle.model_copy(deep=True)
    bundle.train_examples.extend(first.bundle.train_examples)
    bundle.metadata["verified_learning_lineage"].extend(rows)
    updated = replace(
        second,
        bundle=bundle,
        replay_experience_ids=first.new_experience_ids,
        training_population=replace(
            second.training_population,
            members=(*second.training_population.members, *first.training_population.members),
        ),
        replay_selection=selection,
    )
    return replace(p, steps=(first, updated))


def test_replay_selection_retains_exact_earlier_source_and_bundle_lineage():
    p = replay_plan()
    e = evidence(p=p)
    report = assess_continual_learning(e)
    assert report.status == "UNKNOWN"
    assert p.steps[1].replay_selection.selected_count == 2
    assert len(p.steps[1].bundle.train_examples) == 4
    assert p.sequence.experience_ids == plan().sequence.experience_ids
    assert p.record_id != plan().record_id


@pytest.mark.parametrize(
    "change",
    [
        "missing_selection",
        "selected_substitution",
        "source_substitution",
        "future_replay",
        "incomplete_exclusions",
    ],
)
def test_replay_provenance_cannot_be_omitted_or_substituted(change):
    p = replay_plan()
    second = p.steps[1]
    with pytest.raises(ValueError):
        if change == "missing_selection":
            replace(second, replay_selection=None)
        elif change == "selected_substitution":
            sel = second.replay_selection
            d = sel.decisions[0].model_copy(update={"experience_id": "substitute"})
            replace(second, replay_selection=replace(sel, decisions=(d, sel.decisions[1])))
        elif change == "source_substitution":
            sel = second.replay_selection
            d = sel.decisions[0].model_copy(update={"source_fixture_digest": digest("substitute")})
            replace(second, replay_selection=replace(sel, decisions=(d, sel.decisions[1])))
        elif change == "future_replay":
            replace(
                p,
                steps=(replace(second, index=1), replace(p.steps[0], index=2)),
                sequence=ExperienceSequence(
                    experience_ids=(*second.new_experience_ids, *p.steps[0].new_experience_ids)
                ),
            )
        else:
            sel = second.replay_selection
            second = replace(
                second,
                replay_selection=replace(
                    sel, policy=replace(sel.policy, heldout_source_digests=())
                ),
            )
            replace(p, steps=(p.steps[0], second))


def test_replay_training_source_overlap_with_heldout_rejected():
    p = replay_plan()
    guard = p.panels[2]
    shared = p.steps[0].training_population.members
    changed = replace(guard, population=replace(guard.population, members=shared))
    with pytest.raises(ValueError, match="overlap"):
        replace(p, panels=(*p.panels[:2], changed))


def test_replay_same_experience_with_rebuilt_lineage_fails_previous_commitment():
    p = replay_plan()
    s = p.steps[1]
    bundle = s.bundle.model_copy(deep=True)
    row = bundle.metadata["verified_learning_lineage"][-1]
    row["trajectory_id"] = "substituted-original"
    with pytest.raises(ValueError, match="lineage substitution"):
        replace(p, steps=(p.steps[0], replace(s, bundle=bundle)))


def test_stricter_policy_does_not_hide_negative_results():
    report = assess_continual_learning(evidence(), policy=ContinualPolicy(maximum_forgetting=0.1))
    assert gates(report)["retention"] == "FAIL"
    assert report.status == "FAIL"


def test_sealed_inputs_are_not_widened_into_evaluator_private():
    from investigation_world.trajectory import VisibilityClass

    p = plan()
    sealed = p.evidence_references[0].model_copy(update={"visibility": VisibilityClass.SEALED})
    with pytest.raises(ValueError, match="SEALED"):
        replace(p, evidence_references=(sealed,))


def test_known_global_chronology_cannot_hide_reversal_behind_missing_points():
    e = evidence(controls=False)
    rep = e.replicates[0]
    curves = []
    for curve in rep.curves:
        points = tuple(replace(x, observed_at=None) for x in curve.points)
        interventions = (
            replace(curve.interventions[0], finished_at=NOW + timedelta(hours=10)),
            curve.interventions[1],
        )
        curves.append(changed_curve(curve, points=points, interventions=interventions))
    with pytest.raises(ValueError, match="chronology"):
        replace(e, replicates=(replace(rep, curves=tuple(curves)), e.replicates[1]))


def test_manifest_run_identity_cannot_change_without_rebinding_execution_evidence():
    e = evidence()
    rep = e.replicates[0]
    run = replace(
        rep.runs[0], manifest=rep.runs[0].manifest.model_copy(update={"run_id": "other-run"})
    )
    with pytest.raises(ValueError, match="declaration"):
        replace(e, replicates=(replace(rep, runs=(run, rep.runs[1])), e.replicates[1]))


def report_for_step(e, replicate=0, index=0):
    from investigation_world.qualification.maturity import EnvironmentIdentity, VerifierIdentity
    from investigation_world.training_qualification import (
        TrainingEvidence,
        TrainingReplicate,
        assess_training,
    )

    rep = e.replicates[replicate]
    s = e.plan.steps[index]
    cap = s.training_population.capability

    def pair(curve):
        return replace(
            curve,
            points=curve.points[index : index + 2],
            interventions=curve.interventions[index : index + 1],
        )

    heldout = next(c for c in rep.curves if c.points[0].population.capability == cap)
    guard = rep.curves[2]
    training = TrainingEvidence(
        capability=cap,
        environment_identity=EnvironmentIdentity(
            environment_id="world", environment_version="v1", content_sha256=digest("world")
        ),
        verifier_identity=VerifierIdentity(
            verifier_id="verifier", verifier_version="v1", content_sha256=digest("verifier")
        ),
        bundle=s.bundle,
        configuration_digest=s.learner.configuration_digest,
        expected_seeds=(rep.seed,),
        required_guardrail_capabilities=(guard.points[0].population.capability.contract_digest,),
        replicates=(
            TrainingReplicate(
                seed=rep.seed,
                manifest=rep.runs[index].manifest,
                heldout=pair(heldout),
                guardrails=(pair(guard),),
            ),
        ),
        provenance="CONSTRUCTED",
        evidence_references=(ref("training-study"),),
    )
    return assess_training(training)


def test_canonical_training_report_is_consumed_without_overriding_its_unknowns():
    e = evidence()
    reps = tuple(
        replace(
            rep,
            runs=tuple(
                replace(run, training_report=report_for_step(e, j, i))
                for i, run in enumerate(rep.runs)
            ),
        )
        for j, rep in enumerate(e.replicates)
    )
    report = assess_continual_learning(replace(e, replicates=reps))
    assert gates(report)["training_qualification"] == "UNKNOWN"
    assert report.capability_gain is None


def test_training_report_for_another_seed_cannot_be_substituted():
    e = evidence()
    rep = e.replicates[0]
    with pytest.raises(ValueError, match="training report"):
        replace(
            e,
            replicates=(
                replace(
                    rep,
                    runs=(replace(rep.runs[0], training_report=report_for_step(e, 1)), rep.runs[1]),
                ),
                e.replicates[1],
            ),
        )


def test_training_report_for_changed_result_cannot_be_substituted():
    e = evidence()
    other = evidence(scores=((0.2, 0.7, 0.6), (0.1, 0.3, 0.9), (0.8, 0.8, 0.8)))
    rep = e.replicates[0]
    with pytest.raises(ValueError, match="training report evaluation"):
        replace(
            e,
            replicates=(
                replace(
                    rep,
                    runs=(
                        replace(rep.runs[0], training_report=report_for_step(other)),
                        rep.runs[1],
                    ),
                ),
                e.replicates[1],
            ),
        )


def test_shared_protocol_and_paired_report_context_is_not_reused_outcome_evidence():
    # #162 reverified_acquisition_curve deliberately shares these context references.
    e = evidence()
    reps = []
    for rep in e.replicates:
        curves = tuple(
            changed_curve(
                c,
                points=tuple(
                    replace(
                        point,
                        evidence_references=(
                            ref("shared-panel-protocol"),
                            ref("shared-paired-report"),
                        ),
                    )
                    for point in c.points
                ),
            )
            for c in rep.curves
        )
        reps.append(replace(rep, curves=curves))
    report = assess_continual_learning(replace(e, replicates=tuple(reps)))
    assert report.mean_final_recorded_backward_transfer == pytest.approx(-0.2)
    assert report.demonstrated_continual_learning == "UNKNOWN"


def test_native_fixture_and_post_execution_source_hashes_are_distinct_and_bound():
    p = replay_plan()
    row = p.steps[0].bundle.metadata["verified_learning_lineage"][0]
    assert row["fixture_digest"] != row["source_digest"]
    assert p.steps[1].replay_selection.decisions[0].source_fixture_digest == row["fixture_digest"]
    assert assess_continual_learning(evidence(p=p)).status == "UNKNOWN"


def with_train_report(e, *, wrong_checkpoint=False, reuse_outcome=False):
    from investigation_world.training_qualification import assess_training

    report = report_for_step(e)
    rep = report.evidence.replicates[0]
    s = e.plan.steps[0]
    points = tuple(
        point(s.training_population, 1, i, v, control=True) for i, v in enumerate((0.8, 0.2))
    )
    if wrong_checkpoint:
        points = tuple(replace(p, model_revision=f"unrelated-{i}") for i, p in enumerate(points))
    if reuse_outcome:
        source = e.replicates[0].curves[0].points[0].outcomes[0]
        points = (
            replace(
                points[0],
                outcomes=(
                    replace(points[0].outcomes[0], evidence_references=source.evidence_references),
                    points[0].outcomes[1],
                ),
            ),
            points[1],
        )
    intervention = replace(
        rep.heldout.interventions[0],
        before_point_id=points[0].record_id,
        after_point_id=points[1].record_id,
    )
    train = AcquisitionCurve(points=points, interventions=(intervention,))
    train_rep = replace(rep, train=train, heldout=None, guardrails=())
    return assess_training(replace(report.evidence, replicates=(train_rep,)))


def test_negative_train_only_report_keeps_result_when_exact_step_is_bound():
    e = evidence()
    rep = e.replicates[0]
    r = with_train_report(e)
    assert r.status == "FAIL"
    changed = replace(
        e,
        replicates=(
            replace(rep, runs=(replace(rep.runs[0], training_report=r), rep.runs[1])),
            e.replicates[1],
        ),
    )
    assert gates(assess_continual_learning(changed))["training_qualification"] == "FAIL"


@pytest.mark.parametrize(
    "changes, match",
    [({"wrong_checkpoint": True}, "train panel"), ({"reuse_outcome": True}, "reuses")],
)
def test_unrelated_or_reused_training_report_evidence_cannot_contaminate_result(changes, match):
    e = evidence()
    rep = e.replicates[0]
    r = with_train_report(e, **changes)
    with pytest.raises(ValueError, match=match):
        replace(
            e,
            replicates=(
                replace(rep, runs=(replace(rep.runs[0], training_report=r), rep.runs[1])),
                e.replicates[1],
            ),
        )


def test_independent_learnability_control_is_not_active_model_timeline():
    from investigation_world.training_qualification import assess_training

    e = evidence()
    report = report_for_step(e)
    training_rep = report.evidence.replicates[0]
    control = replace(
        point(training_rep.heldout.points[0].population, 1, 0, 1.0, control=True),
        model_revision="independent-expert-checkpoint",
        observed_at=NOW + timedelta(hours=10),
    )
    training_rep = replace(training_rep, learnability=control)
    report = assess_training(replace(report.evidence, replicates=(training_rep,)))
    rep = e.replicates[0]
    changed = replace(
        e,
        replicates=(
            replace(rep, runs=(replace(rep.runs[0], training_report=report), rep.runs[1])),
            e.replicates[1],
        ),
    )
    assert assess_continual_learning(changed).status == "UNKNOWN"
