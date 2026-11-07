"""Constructed decision-engine fixtures, NOT model execution or learned performance."""

from hashlib import sha256

import pytest

from investigation_world.capability_science import (
    AcquisitionCurve,
    CapabilitySpec,
    CaseOutcome,
    EvaluationConditions,
    EvaluationPoint,
    EvaluationPopulation,
    PrerequisiteClaim,
    PrerequisiteGraph,
    TrainingIntervention,
)
from investigation_world.curriculum import (
    CurriculumHistory,
    CurriculumPolicy,
    FixedPanels,
    FrontierObservation,
    advance_stage,
    build_curriculum,
    stage_readiness,
    validate_curriculum,
    validate_history,
)
from investigation_world.curriculum.active import CurriculumCandidate, CurriculumPlan, _make_plan
from investigation_world.experience import ExperienceReference
from investigation_world.experience.counterfactual import execute_counterfactual_experience
from investigation_world.experience_foundry.admission import PublicTrainingRecorder
from investigation_world.experience_selection import SelectionPolicy
from investigation_world.foundry.models import CapabilityContract
from investigation_world.operational import EpisodeSubmission
from investigation_world.trajectory import VisibilityClass


def ref(name):
    return ExperienceReference(
        reference_id=name,
        reference_type="CONSTRUCTED",
        digest=sha256(name.encode()).hexdigest(),
        visibility=VisibilityClass.PUBLIC,
    )


def spec(name):
    return CapabilitySpec(contract=CapabilityContract(capability_id=name, objective=name))


def population(capability, split="HELD_OUT", name="validation", members=None):
    return EvaluationPopulation(
        capability=capability,
        conditions=EvaluationConditions(
            environment_id="constructed-world",
            environment_revision="v1",
            verifier_id="constructed-verifier",
            verifier_revision="v1",
            metric="success_fraction",
            metric_definition_digest="a" * 64,
            distribution_id="constructed-distribution",
            structure_id=name,
            interface_id="constructed-interface",
            evidence_references=(ref(name + "-conditions"),),
        ),
        split=split,
        members=members or (ref(name + "-1"), ref(name + "-2")),
        evidence_references=(ref(name + "-commitment"),),
    )


def point(panel, values, index=0, revision="checkpoint-0"):
    return EvaluationPoint(
        population=panel,
        model_id="constructed-model",
        model_revision=revision,
        sequence_index=index,
        execution_provenance="CONSTRUCTED",
        outcomes=tuple(
            CaseOutcome(
                member_id=member.reference_id,
                member_digest=member.digest,
                value=value,
                evidence_references=(ref(f"{panel.record_id}-{index}-{member.reference_id}"),)
                if value is not None
                else (),
                unavailable_reason="not observed" if value is None else None,
            )
            for member, value in zip(panel.members, values, strict=True)
        ),
        evidence_references=(ref(f"point-{panel.record_id}-{index}"),),
    )


def engine_plan(*, policy=None, observations=None, two=False):
    """Internal scheduling seam only; real-source authority is tested separately."""
    first, second = spec("base"), spec("composed")
    specs = (first, second) if two else (first,)
    graph = PrerequisiteGraph(
        specs=specs,
        claims=(
            PrerequisiteClaim(
                prerequisite=first.record_id,
                dependent=second.record_id,
                evidence_references=(ref("declared-prerequisite"),),
            ),
        )
        if two
        else (),
    )
    candidates = tuple(
        CurriculumCandidate(
            slot_id=f"slot-{i}-{j}",
            experience_id=f"source-{i}-{j}",
            input_digest=ref(f"input-{i}-{j}").digest,
            capability_spec_id=s.record_id,
            task=ref(f"train-{i}-{j}"),
            asset_ids=(f"constructed-asset-{i}-{j}",),
        )
        for i, s in enumerate(specs)
        for j in range(3)
    )
    panels = FixedPanels(
        validation=tuple(population(s, name=f"validation-{i}") for i, s in enumerate(specs)),
        final_test=tuple(population(s, name=f"final-{i}") for i, s in enumerate(specs)),
    )
    if observations is None:
        observed = []
        for i, s in enumerate(specs):
            train = population(
                s,
                "TRAIN",
                f"training-{i}",
                tuple(c.task for c in candidates if c.capability_spec_id == s.record_id),
            )
            observed.extend(
                point(train, values, index=k)
                for k, values in enumerate(((0, 1, 0), (1, 1, 0), (0, 1, 0), (1, 1, 0)))
            )
        observations = FrontierObservation(points=tuple(observed))
    return _make_plan(
        graph=graph,
        panels=panels,
        observation=observations,
        policy=policy or CurriculumPolicy(max_items_per_stage=1),
        model_id="constructed-model",
        model_revision="checkpoint-0",
        selection_id="constructed-selection",
        compilation_id="constructed-compilation",
        candidates=candidates,
    )


def acquisition(
    plan,
    stage_index=0,
    values=(1, 1),
    before_revision="checkpoint-0",
    after_revision="checkpoint-1",
    before_values=(0, 0),
    index=0,
):
    stage = plan.stages[stage_index]
    panel = next(p for p in plan.panels.validation if p.record_id == stage.validation_population_id)
    before = point(panel, before_values, index=index, revision=before_revision)
    after = point(panel, values, index=index + 1, revision=after_revision)
    training = population(panel.capability, "TRAIN", "selected-training", stage.training_members)
    step = TrainingIntervention(
        before_point_id=before.record_id,
        after_point_id=after.record_id,
        training_population=training,
        trainer_id="constructed-external-trainer",
        trainer_revision="v1",
        training_bundle_digest="b" * 64,
        training_configuration_digest="c" * 64,
        execution_provenance="CONSTRUCTED",
        evidence_references=(ref("external-intervention"),),
    )
    return AcquisitionCurve(points=(before, after), interventions=(step,))


def test_measured_frontier_not_static_difficulty_and_order_is_fixed():
    plan = engine_plan(two=True)
    first = plan.stages[0]
    assert first.choices[0].task_id == "train-0-0"
    assert first.choices[0].reason == "measured_frontier"
    assert first.choices[0].success_rate == 0.5
    assert plan.stages[1].prerequisites == (first.capability_spec_id,)
    assert plan.observation.record_id
    assert plan.qualification == "UNKNOWN"


def test_heldout_recorded_criterion_can_advance_but_not_training_reward():
    plan = engine_plan(two=True)
    history = CurriculumHistory(plan_id=plan.record_id)
    held = advance_stage(plan, history)
    assert held.events[-1].decision == "HOLD"
    assert held.events[-1].reason == "missing_acquisition_evidence"
    gained = advance_stage(plan, held, acquisition=acquisition(plan))
    assert gained.events[-1].decision == "ADVANCE_RECORDED_CRITERION"
    assert gained.events[-1].execution_attestation == "UNKNOWN"
    assert history.events == ()
    assert gained.events[:1] == held.events


def test_prerequisite_failure_or_missing_evidence_blocks_dependent():
    plan = engine_plan(two=True)
    history = advance_stage(
        plan, CurriculumHistory(plan_id=plan.record_id), acquisition=acquisition(plan)
    )
    next_curve = acquisition(plan, 1, before_revision="checkpoint-1", after_revision="checkpoint-2")
    blocked = advance_stage(plan, history, acquisition=next_curve)
    assert blocked.events[-1].reason == "prerequisite_evidence_missing"
    prior_panel = plan.panels.validation[0]
    failed = point(prior_panel, (0, 0), index=2, revision="checkpoint-2")
    blocked = advance_stage(
        plan, history, acquisition=next_curve, prerequisite_evaluations=(failed,)
    )
    assert blocked.events[-1].reason == "prerequisite_criterion_failed"
    passed = point(prior_panel, (1, 1), index=2, revision="checkpoint-2")
    complete = advance_stage(
        plan, history, acquisition=next_curve, prerequisite_evaluations=(passed,)
    )
    assert complete.events[-1].decision == "ADVANCE_RECORDED_CRITERION"


@pytest.mark.parametrize(
    "scores,reason",
    [
        ((0, 0), "validation_criterion_failed"),
        ((None, 1), "validation_outcomes_unknown"),
    ],
)
def test_negative_and_unknown_outcomes_hold(scores, reason):
    plan = engine_plan()
    result = advance_stage(
        plan,
        CurriculumHistory(plan_id=plan.record_id),
        acquisition=acquisition(plan, values=scores),
    )
    assert result.events[-1].decision == "HOLD"
    assert result.events[-1].reason == reason


def test_no_frontier_is_seeded_fallback_not_mastery():
    plan = engine_plan(observations=FrontierObservation(points=()))
    assert plan.stages[0].choices[0].reason == "fallback_no_observation"
    assert plan.stages[0].choices[0].success_rate is None
    assert plan.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}


def test_no_test_set_scores_or_training_panel_can_advance():
    plan = engine_plan()
    for panel in (plan.panels.final_test[0], population(spec("base"), "TRAIN")):
        curve = acquisition(plan)
        before = point(panel, (0, 0))
        after = point(panel, (1, 1), 1, "checkpoint-1")
        step = curve.interventions[0].model_dump(exclude={"record_id"})
        step.update(before_point_id=before.record_id, after_point_id=after.record_id)
        wrong = AcquisitionCurve(
            points=(before, after), interventions=(TrainingIntervention(**step),)
        )
        with pytest.raises(ValueError, match="validation population"):
            advance_stage(plan, CurriculumHistory(plan_id=plan.record_id), acquisition=wrong)


def test_validation_and_final_panels_must_be_disjoint():
    plan = engine_plan()
    with pytest.raises(ValueError, match="overlap"):
        FixedPanels(validation=plan.panels.validation, final_test=plan.panels.validation)


def rebuild(value, **changes):
    data = value.model_dump(mode="python", exclude={"record_id"})
    data.update(changes)
    return type(value)(**data)


def test_control_is_seeded_over_identical_pool_budgets_and_stage_order():
    targeted = engine_plan(two=True)
    controls = [
        engine_plan(
            two=True,
            policy=CurriculumPolicy(
                max_items_per_stage=1,
                mode="random_control",
                seed=seed,
            ),
        )
        for seed in range(6)
    ]
    assert all(c.candidates == targeted.candidates for c in controls)
    assert all(c.panels == targeted.panels for c in controls)
    assert all(
        [s.capability_spec_id for s in c.stages] == [s.capability_spec_id for s in targeted.stages]
        for c in controls
    )
    assert all(sum(t.selected for t in s.choices) == 1 for c in controls for s in c.stages)
    assert len({c.stages[0].training_members[0].reference_id for c in controls}) > 1
    assert controls[0] == engine_plan(
        two=True,
        policy=CurriculumPolicy(
            max_items_per_stage=1,
            mode="random_control",
            seed=0,
        ),
    )


def test_ceiling_and_floor_are_fallbacks_not_mastery_or_capability_coverage():
    plan = engine_plan(policy=CurriculumPolicy(max_items_per_stage=3))
    reasons = {c.task_id: c.reason for c in plan.stages[0].choices}
    assert reasons == {
        "train-0-0": "measured_frontier",
        "train-0-1": "fallback_above_band",
        "train-0-2": "fallback_below_band",
    }
    assert plan.qualification == "UNKNOWN"
    assert all(c.training_qualified is False for c in plan.candidates)


def test_sparse_and_missing_outcomes_are_explicit_fallbacks():
    original = engine_plan()
    only = original.observation.points[0]
    sparse = engine_plan(observations=FrontierObservation(points=(only,)))
    assert sparse.stages[0].choices[0].reason == "fallback_sparse_observation"
    unknown = point(only.population, (None, None, None))
    missing = engine_plan(observations=FrontierObservation(points=(unknown,)))
    assert missing.stages[0].choices[0].reason == "fallback_unknown_outcomes"
    assert missing.stages[0].choices[0].success_rate is None


def test_flat_high_validation_is_not_acquisition_and_complete_history_cannot_extend():
    plan = engine_plan()
    history = CurriculumHistory(plan_id=plan.record_id)
    held = advance_stage(plan, history, acquisition=acquisition(plan, before_values=(1, 1)))
    assert held.events[-1].reason == "validation_delta_insufficient"
    complete = advance_stage(plan, history, acquisition=acquisition(plan))
    assert validate_history(complete, plan) == complete
    with pytest.raises(ValueError, match="already completed"):
        advance_stage(plan, complete)


def test_rehashing_cannot_forge_stage_order_or_history_decisions():
    plan = engine_plan(two=True)
    with pytest.raises(ValueError, match="precommitted scheduling"):
        rebuild(plan, stages=tuple(reversed(plan.stages)))
    held = advance_stage(plan, CurriculumHistory(plan_id=plan.record_id))
    event = rebuild(
        held.events[0],
        decision="ADVANCE_RECORDED_CRITERION",
        reason="heldout_validation_criterion_met",
    )
    forged = rebuild(held, events=(event,))
    with pytest.raises(ValueError, match="rewritten or forged"):
        validate_history(forged, plan)
    with pytest.raises(ValueError, match="different precommitted plan"):
        validate_history(held, engine_plan(two=True, policy=CurriculumPolicy(seed=6)))


def test_tampered_nested_mutable_inputs_fail_revalidation():
    plan = engine_plan()
    plan.graph.specs[0].contract.success_conditions.append("tamper")
    with pytest.raises(ValueError, match="content_digest|identity"):
        advance_stage(plan, CurriculumHistory(plan_id=plan.record_id))


def test_checkpoint_and_exact_stage_training_population_are_required():
    plan = engine_plan()
    history = CurriculumHistory(plan_id=plan.record_id)
    wrong = acquisition(plan, before_revision="another-checkpoint")
    with pytest.raises(ValueError, match="checkpoint mismatch"):
        advance_stage(plan, history, acquisition=wrong)
    curve = acquisition(plan)
    step = rebuild(curve.interventions[0], training_population=population(spec("base"), "TRAIN"))
    wrong = rebuild(curve, interventions=(step,))
    with pytest.raises(ValueError, match="differs from selected stage"):
        advance_stage(plan, history, acquisition=wrong)


@pytest.mark.parametrize(
    "field,value",
    [
        ("low", 0.8),
        ("minimum_attempts", 0),
        ("seed", True),
        ("minimum_validation_score", float("nan")),
        ("version", "2"),
    ],
)
def test_policy_bounds_and_version_fail_closed(field, value):
    with pytest.raises(ValueError):
        CurriculumPolicy(**{field: value})


def test_observation_rejects_test_scores_duplicate_attempts_and_sealed_inputs():
    plan = engine_plan()
    with pytest.raises(ValueError, match="TRAIN"):
        FrontierObservation(points=(point(plan.panels.final_test[0], (1, 1)),))
    first = plan.observation.points[0]
    with pytest.raises(ValueError, match="duplicate"):
        FrontierObservation(points=(first, first))
    with pytest.raises(ValueError, match="SEALED"):
        FrontierObservation(points=(rebuild(first, visibility=VisibilityClass.SEALED),))
    with pytest.raises(ValueError):
        rebuild(plan.policy, visibility=VisibilityClass.PUBLIC)


def test_final_panel_digest_overlap_even_with_distinct_member_ids_rejects():
    plan = engine_plan()
    original = plan.panels.validation[0]
    renamed = tuple(
        r.model_copy(update={"reference_id": "renamed-" + r.reference_id}) for r in original.members
    )
    final = rebuild(plan.panels.final_test[0], members=renamed)
    with pytest.raises(ValueError, match="overlap"):
        FixedPanels(validation=(original,), final_test=(final,))


def _record(root, wrong=None):
    recorder = PublicTrainingRecorder(root)
    records = recorder.runtime.public_payload()["records"]
    audit = next(r for r in records if r["record_type"] == "formula_audit")
    correct = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    recorder.act("repair_formula", cell=audit["object_id"], formula=wrong or correct)
    recorder.act("recalculate_model")
    source = recorder.submit(
        EpisodeSubmission(
            conclusion="Constructed public runtime fixture, no model execution",
            evidence_ids=[
                r["record_id"]
                for r in records
                if r["record_type"] in {"formula_audit", "model_check"}
            ],
        )
    )
    return source, {"cell": audit["object_id"], "formula": correct}


@pytest.fixture(scope="module")
def actual_inputs(tmp_path_factory):
    root = tmp_path_factory.mktemp("curriculum")
    success, _ = _record(root / "success")
    gaps = []
    for i in range(2):
        source, replacement = _record(root / f"failed-{i}", wrong=f"={i}")
        receipt = execute_counterfactual_experience(
            source,
            branch_step=0,
            replacement=replacement,
            artifact_root=root / f"branch-{i}",
        )
        gaps.append((receipt, source))
    capability = CapabilitySpec(contract=success.capability)
    panel = population(
        capability,
        "TRAIN",
        "actual-training",
        (
            ExperienceReference(
                reference_id=success.companion.task_id,
                reference_type="TRAIN_source_fixture",
                digest=success.companion.metadata["source_digest"],
            ),
        ),
    )
    observation = FrontierObservation(
        points=tuple(point(panel, (value,), i) for i, value in enumerate((0, 1, 0, 1)))
    )
    kwargs = dict(
        graph=PrerequisiteGraph(specs=(capability,)),
        panels=FixedPanels(
            validation=(population(capability, name="actual-validation"),),
            final_test=(population(capability, name="actual-final"),),
        ),
        observation=observation,
        model_id="constructed-model",
        model_revision="checkpoint-0",
        policy=CurriculumPolicy(selection=SelectionPolicy(max_per_stratum=2)),
        gap_sources=tuple(gaps),
    )
    return (success,), kwargs


def test_actual_provider_selection_and_derivation_lineage_are_revalidated(actual_inputs):
    sources, kwargs = actual_inputs
    plan = build_curriculum(sources, **kwargs)
    assert len(plan.candidates) == 1
    assert plan.selection_report.selected_count == 1
    assert (
        plan.compilation.assets[0].lineage.source.reference_id
        == sources[0].experience.experience_id
    )
    assert plan.candidates[0].asset_ids == (plan.compilation.assets[0].record_id,)
    assert plan.stages[0].choices[0].reason == "measured_frontier"
    assert validate_curriculum(plan, sources, **kwargs) == plan
    assert CurriculumPlan.model_validate_json(plan.model_dump_json()) == plan
    assert (
        plan.public_payload()
        == plan.buyer_safe_payload()
        == {
            "status": "UNKNOWN",
            "reason": "evidence_not_visible",
        }
    )
    with pytest.raises(ValueError, match="CANDIDATE_NOT_TRAINING_ADMITTED"):
        plan.compilation.assets[0].trainer_payload()


def test_actual_input_order_and_expected_policy_binding(actual_inputs):
    sources, kwargs = actual_inputs
    plan = build_curriculum(sources, **kwargs)
    reordered = {
        **kwargs,
        "gap_sources": tuple(reversed(kwargs["gap_sources"])),
        "observation": FrontierObservation(points=tuple(reversed(kwargs["observation"].points))),
    }
    assert build_curriculum(reversed(sources), **reordered) == plan
    changed = {**kwargs, "policy": CurriculumPolicy(seed=92)}
    with pytest.raises(ValueError, match="freshly validated"):
        validate_curriculum(plan, sources, **changed)


def test_missing_gap_evidence_is_empty_not_fabricated_capability_coverage(actual_inputs):
    sources, kwargs = actual_inputs
    plan = build_curriculum(sources, **{**kwargs, "gap_sources": ()})
    assert plan.candidates == ()
    assert plan.stages[0].training_members == ()
    assert plan.selection_report.rejection_counts == {"no_useful_gap": 1}
    assert (
        advance_stage(plan, CurriculumHistory(plan_id=plan.record_id)).events[-1].decision == "HOLD"
    )


def test_fixed_panel_observation_preflight_precedes_provider_access(actual_inputs, monkeypatch):
    import investigation_world.curriculum.active as module

    sources, kwargs = actual_inputs
    final = kwargs["panels"].final_test[0]
    train_label = rebuild(final, split="TRAIN")
    bad = FrontierObservation(points=(point(train_label, (1, 1)),))

    def forbidden(*args, **kw):
        raise AssertionError("protected evidence reached source provider")

    monkeypatch.setattr(module, "select_experiences", forbidden)
    with pytest.raises(ValueError, match="overlap"):
        build_curriculum(sources, **{**kwargs, "observation": bad})


def test_actual_source_tampering_cannot_use_saved_plan_as_authority(actual_inputs):
    from dataclasses import replace

    sources, kwargs = actual_inputs
    plan = build_curriculum(sources, **kwargs)
    bad = replace(
        sources[0], companion=sources[0].companion.model_copy(update={"total_cost": 99999})
    )
    with pytest.raises(ValueError):
        validate_curriculum(plan, (bad,), **kwargs)


def test_bounded_generators_reject_without_consuming_unbounded_input(actual_inputs):
    sources, kwargs = actual_inputs
    consumed = []

    def inputs():
        while True:
            consumed.append(1)
            yield sources[0]

    with pytest.raises(ValueError, match="input bound"):
        build_curriculum(inputs(), **kwargs)
    assert len(consumed) == 257


def test_dependent_task_release_is_blocked_by_current_prerequisite_regression():
    plan = engine_plan(two=True)
    initial = CurriculumHistory(plan_id=plan.record_id)
    ready = stage_readiness(plan, initial)
    assert ready.stage_id == plan.stages[0].record_id
    assert ready.status == "READY_CONDITIONAL"
    progressed = advance_stage(plan, initial, acquisition=acquisition(plan))
    ready = stage_readiness(plan, progressed)
    assert ready.stage_id == plan.stages[1].record_id
    assert ready.status == "READY_CONDITIONAL"
    regressed = point(plan.panels.validation[0], (0, 0), index=2, revision="checkpoint-1")
    blocked = stage_readiness(plan, progressed, prerequisite_evaluations=(regressed,))
    assert blocked.status == "BLOCKED"
    assert blocked.candidate_ids == ()
    assert blocked.reason == "prerequisite_criterion_failed"


def test_stale_actual_retained_artifact_invalidates_curriculum(actual_inputs):
    from pathlib import Path

    sources, kwargs = actual_inputs
    plan = build_curriculum(sources, **kwargs)
    raw = sources[0].experience.trajectory.private_metadata["operational_reverification_evidence"]
    path = Path(raw["native_submission"]["artifact_path"])
    original = path.read_bytes()
    try:
        path.write_bytes(b"mutated public synthetic fixture")
        with pytest.raises(ValueError):
            validate_curriculum(plan, sources, **kwargs)
    finally:
        path.write_bytes(original)


def test_prerequisite_sequence_cannot_rewind_or_rewrite_prior_evidence():
    plan = engine_plan(two=True)
    history = advance_stage(
        plan, CurriculumHistory(plan_id=plan.record_id), acquisition=acquisition(plan)
    )
    next_curve = acquisition(plan, 1, before_revision="checkpoint-1", after_revision="checkpoint-2")
    for index in (0, 1):
        wrong = point(plan.panels.validation[0], (1, 1), index=index, revision="checkpoint-2")
        with pytest.raises(ValueError, match="backwards|rewrote"):
            advance_stage(plan, history, acquisition=next_curve, prerequisite_evaluations=(wrong,))
    failed = point(plan.panels.validation[0], (0, 0), index=2, revision="checkpoint-2")
    held = advance_stage(plan, history, acquisition=next_curve, prerequisite_evaluations=(failed,))
    retry = acquisition(
        plan, 1, before_revision="checkpoint-2", after_revision="checkpoint-3", index=2
    )
    rewritten = point(plan.panels.validation[0], (1, 1), index=2, revision="checkpoint-3")
    with pytest.raises(ValueError, match="rewrote"):
        advance_stage(plan, held, acquisition=retry, prerequisite_evaluations=(rewritten,))


def test_readiness_cannot_replace_latest_prerequisite_with_an_older_result():
    plan = engine_plan(two=True)
    history = advance_stage(
        plan, CurriculumHistory(plan_id=plan.record_id), acquisition=acquisition(plan)
    )
    stale = point(plan.panels.validation[0], (1, 1), index=0, revision="checkpoint-1")
    with pytest.raises(ValueError, match="backwards|rewrote"):
        stage_readiness(plan, history, prerequisite_evaluations=(stale,))


def test_readiness_refuses_sealed_evidence_instead_of_reclassifying_derived_ids():
    plan = engine_plan(two=True)
    history = advance_stage(
        plan, CurriculumHistory(plan_id=plan.record_id), acquisition=acquisition(plan)
    )
    sealed = rebuild(
        point(plan.panels.validation[0], (1, 1), index=2, revision="checkpoint-1"),
        visibility=VisibilityClass.SEALED,
    )
    with pytest.raises(ValueError, match="SEALED"):
        stage_readiness(plan, history, prerequisite_evaluations=(sealed,))


@pytest.mark.parametrize("location", ["source", "gap_source", "receipt"])
def test_sealed_source_or_gap_rejects_before_provider_access(actual_inputs, monkeypatch, location):
    from dataclasses import replace

    import investigation_world.curriculum.active as module

    sources, kwargs = actual_inputs
    kwargs = dict(kwargs)
    if location == "source":
        sources = (
            replace(
                sources[0],
                experience=sources[0].experience.model_copy(
                    update={"visibility": VisibilityClass.SEALED}
                ),
            ),
        )
    else:
        gaps = list(kwargs["gap_sources"])
        receipt, source = gaps[0]
        if location == "gap_source":
            source = replace(
                source,
                experience=source.experience.model_copy(
                    update={"visibility": VisibilityClass.SEALED}
                ),
            )
        else:
            receipt = receipt.model_copy(update={"visibility": VisibilityClass.SEALED})
        gaps[0] = (receipt, source)
        kwargs["gap_sources"] = tuple(gaps)

    def forbidden(*args, **kw):
        raise AssertionError("sealed input reached source provider")

    monkeypatch.setattr(module, "select_experiences", forbidden)
    with pytest.raises(ValueError, match="SEALED"):
        build_curriculum(sources, **kwargs)
