"""Real public profile execution; fixtures are not measured model evidence."""

import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from investigation_world.capability_science import (
    CapabilitySpec,
    EvaluationConditions,
    EvaluationPopulation,
    PrerequisiteGraph,
    ingest_capability_failure,
)
from investigation_world.curriculum import (
    CurriculumPolicy,
    FixedPanels,
    FrontierObservation,
    build_curriculum,
    validate_curriculum,
)
from investigation_world.experience import ExperienceReference, machine_experience_from_trajectory
from investigation_world.experience.counterfactual import execute_counterfactual_experience
from investigation_world.experience.counterfactual.validation import verify_recorded
from investigation_world.experience.diagnostics import intervention_failure_families
from investigation_world.experience_foundry.admission import (
    COMPANION_SOURCE,
    RECORDER_VERSION,
    PublicTrainingRecorder,
    admit_experience,
    authorized_registry,
    public_training_fixture,
)
from investigation_world.experience_foundry.bundle_bridge import compile_verified_bundle
from investigation_world.experience_foundry.derivation import (
    compile_learning_assets,
    validate_compilation,
)
from investigation_world.experience_foundry.public_profiles import (
    profile_id_from_trace,
    profile_provenance,
    structural_training_fixture,
    validate_profile_action_events,
)
from investigation_world.experience_selection import SelectionPolicy, select_experiences
from investigation_world.foundry.training_product import TrainerKind, TrainingRecipe
from investigation_world.operational import EpisodeSubmission
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import TrajectoryV2, canonical_hash
from investigation_world.trajectory.reverify import REPLAY_EVIDENCE_PRIVATE_KEY
from investigation_world.trajectory.reverify.models import OperationalReplayEvidence

PROFILES = ("financial-ordered-v2", "financial-ordered-context-v2")


def _record(root, profile_id=None, formula="good"):
    recorder = PublicTrainingRecorder(root, profile_id=profile_id)
    rows = recorder.runtime.public_payload()["records"]
    audit = next(row for row in rows if row["record_type"] == "formula_audit")
    good = f"=SUM(Revenue!B2:B{audit['fields']['expected_periods'] + 1})"
    chosen = (
        good if formula == "good" else audit["fields"]["formula"] if formula == "bad" else formula
    )
    recorder.act("repair_formula", cell=audit["object_id"], formula=chosen)
    recorder.act("recalculate_model")
    source = recorder.submit(
        EpisodeSubmission(
            conclusion="Constructed public protocol; no model execution claim",
            evidence_ids=[
                row["record_id"]
                for row in rows
                if row["record_type"] in {"formula_audit", "model_check"}
            ],
        )
    )
    return source, {"cell": audit["object_id"], "formula": good}


def _recipe(source):
    return TrainingRecipe(
        recipe_id="public-profiles-test",
        trainer=TrainerKind.SFT,
        capability_contract_id=source.capability.capability_id,
    )


def _rebind_companion(source, trace):
    """Repair hashes deliberately: regeneration, not only hash checking, must reject."""
    trace.trace_id = "bridge-trace-" + canonical_hash(
        trace.model_dump(mode="json", exclude={"trace_id"})
    )
    payload = source.experience.trajectory.model_dump(mode="python")
    payload["trajectory_id"] = ""
    payload["provenance"] = tuple(
        {
            **item,
            "source_id": trace.trace_id,
            "source_digest": canonical_hash(trace.model_dump(mode="json")),
        }
        if item["source_kind"] == COMPANION_SOURCE
        else item
        for item in payload["provenance"]
    )
    return replace(
        source,
        companion=trace,
        experience=machine_experience_from_trajectory(TrajectoryV2.model_validate(payload)),
    )


def test_v1_fixture_matches_independent_pre_extension_golden():
    # Captured from unmodified main afca077, not calculated by the new profile generator.
    case, capability = public_training_fixture()
    assert canonical_hash(case.model_dump(mode="json")) == (
        "b0b1f995c2414b8a7ee77d712778c4f265c4a54ea91f4666ae36cd1c8d89fb72"
    )
    assert canonical_hash(case.episode.model_dump(mode="json")) == (
        "9e3effd8dd4f3eb88b8f581ba9305458d4817cb5fa6176a1350fe69c697de688"
    )
    assert capability.content_digest == "CCONTRACT-C18CBD41EF02AA01E8F0"
    assert compile_operational_episode(case.episode).contract_id == (
        "poc-v1-sha256:8c6bf7ad7c39344afbc9af0e30881e99d9782cc18cd68ed36a19c0e1e5beec72"
    )
    assert canonical_hash(case.episode.public_payload()) == (
        "8f319096aecde9ed944efeb2c40ffe7bd7a2919b14bb1bc59d983e074c740789"
    )


def test_v1_recording_and_trainer_projection_remain_unchanged(tmp_path):
    source, _ = _record(tmp_path / "legacy")
    assert source.companion.harness_version == RECORDER_VERSION
    assert profile_id_from_trace(source.companion) is None
    assert source.companion.metadata == {
        "recorder": RECORDER_VERSION,
        "source_digest": "9e3effd8dd4f3eb88b8f581ba9305458d4817cb5fa6176a1350fe69c697de688",
    }
    result = compile_verified_bundle([source], _recipe(source), registry=authorized_registry())
    assert hashlib.sha256(result.trainer_bytes).hexdigest() == (
        "f59c15d1c08e287a80536b5051a68dcf7190c7c4056730a370afeea92b16033c"
    )


@pytest.mark.parametrize("profile_id", PROFILES)
def test_profiles_are_reproducible_fresh_and_do_not_mutate_v1(profile_id):
    original = public_training_fixture()
    first = structural_training_fixture(profile_id)
    expected = copy.deepcopy(first)
    first[0].episode.records[0].fields["caller-edit"] = "not canonical"
    assert structural_training_fixture(profile_id) == expected
    assert public_training_fixture() == original
    provenance = profile_provenance(profile_id)
    assert provenance and profile_id in json.dumps(provenance)
    assert profile_provenance(profile_id) == provenance
    provenance["caller-edit"] = "not canonical"
    assert "caller-edit" not in profile_provenance(profile_id)


@pytest.mark.parametrize("profile_id", ["", "financial-ordered-v3", "iid_test", {}, True])
def test_profile_grammar_is_closed_before_artifact_creation(tmp_path, profile_id):
    root = tmp_path / "not-created"
    with pytest.raises((ValueError, TypeError)):
        structural_training_fixture(profile_id)
    with pytest.raises((ValueError, TypeError)):
        PublicTrainingRecorder(root, profile_id=profile_id)
    assert not root.exists()


def test_profile_generation_never_traverses_a_heldout_case(monkeypatch):
    from investigation_world.experience_foundry import admission

    original = admission.iter_operational_distribution

    def first_only(config):
        yield next(original(config))
        raise AssertionError("profile generator traversed beyond the first public TRAIN case")

    monkeypatch.setattr(admission, "iter_operational_distribution", first_only)
    for profile in PROFILES:
        case, _ = structural_training_fixture(profile)
        assert case.split.value == "train"


def test_dependency_is_an_executable_edge_not_a_scalar_or_label(tmp_path):
    legacy = PublicTrainingRecorder(tmp_path / "legacy")
    ordered = PublicTrainingRecorder(tmp_path / "ordered", profile_id=PROFILES[0])
    legacy.act("recalculate_model")
    before = ordered.runtime.state_snapshot()
    ordered.act("recalculate_model")
    assert legacy.runtime.events[-1].effect_applied
    assert not legacy.runtime.events[-1].blocked
    assert ordered.runtime.events[-1].blocked
    assert not ordered.runtime.events[-1].effect_applied
    assert ordered.runtime.state_snapshot() == before
    assert ordered.runtime.events[-1].cost == legacy.runtime.events[-1].cost
    assert ordered.runtime.events[-1].blocked_reason == "prior_action:repair_formula"
    assert ordered.runtime.episode.oracle.required_action_order == [
        "repair_formula",
        "recalculate_model",
    ]


@pytest.mark.parametrize("formula", ["good", "=0"])
def test_v2_native_action_projection_matches_success_and_blocked_calls(tmp_path, formula):
    source, _ = _record(tmp_path / "source", PROFILES[0], formula=formula)
    evidence = OperationalReplayEvidence.model_validate(
        source.experience.trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    )
    validate_profile_action_events(PROFILES[0], source.companion, evidence.action_events)
    for event, action in zip(source.companion.events, evidence.action_events, strict=False):
        assert event.payload["success"] is bool(action.effect_applied and not action.blocked)


@pytest.mark.parametrize("success", [False, 1, None])
def test_v2_native_action_projection_rejects_inconsistent_success_fields(tmp_path, success):
    source, _ = _record(tmp_path / "source", PROFILES[0])
    evidence = OperationalReplayEvidence.model_validate(
        source.experience.trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    )
    inconsistent = source.companion.model_copy(deep=True)
    inconsistent.events[0].payload["success"] = success
    with pytest.raises(ValueError, match="PROFILE_ACTION_EVIDENCE_MISMATCH"):
        validate_profile_action_events(PROFILES[0], inconsistent, evidence.action_events)


def test_context_variant_changes_the_public_record_graph():
    base, _ = structural_training_fixture(PROFILES[0])
    context, _ = structural_training_fixture(PROFILES[1])
    base_ids = {row.record_id for row in base.episode.records}
    added = [row for row in context.episode.records if row.record_id not in base_ids]
    assert len(context.episode.records) == len(base.episode.records) + 1
    assert len(added) == 1
    assert added[0].related_object_ids
    assert set(added[0].related_object_ids) <= {
        row.object_id for row in base.episode.records
    }
    assert context.episode.task.task_id != base.episode.task.task_id
    assert context.episode.oracle.required_actions == base.episode.oracle.required_actions
    assert len([a for a in context.episode.oracle.target_state if a.field_name == "formula"]) == 1


@pytest.mark.parametrize("profile_id", PROFILES)
def test_real_recording_reverifies_and_does_not_invent_canonical_identity(tmp_path, profile_id):
    source, _ = _record(tmp_path / "native", profile_id)
    before = copy.deepcopy(source)
    checked, _, verification, breakdown = verify_recorded(source)
    assert checked == source
    assert profile_id_from_trace(source.companion) == profile_id
    assert breakdown["outcome"] == 1
    assert breakdown["target_assertions_total"] == breakdown["target_assertions_met"]
    assert verification.record_id
    admitted = admit_experience(source, registry=authorized_registry())
    assert admitted.verified.assessment.terminal_success
    trajectory = source.experience.trajectory
    for identity in (trajectory.model, trajectory.agent, trajectory.harness, trajectory.runtime):
        assert all(value is None for value in identity.model_dump().values())
    assert trajectory.task.split is None
    assert trajectory.reset.seed is None
    assert source == before


@pytest.mark.parametrize("profile_id", PROFILES)
def test_profile_prompt_preserves_public_structure_without_private_material(tmp_path, profile_id):
    source, _ = _record(tmp_path / "source", profile_id)
    case, _ = structural_training_fixture(profile_id)
    result = compile_verified_bundle([source], _recipe(source), registry=authorized_registry())
    row = json.loads(result.trainer_bytes)
    assert row["prompt"]["objective"] == case.episode.task.objective
    assert row["prompt"]["constraints"] == case.episode.task.constraints
    by_id = {r["record_id"]: r for r in row["prompt"]["records"]}
    assert set(by_id) == {r.record_id for r in case.episode.records}
    for record in case.episode.records:
        assert by_id[record.record_id]["related_object_ids"] == record.related_object_ids
    for private in (
        "oracle", "native_submission", "private_metadata", "profile_provenance",
        str(tmp_path), source.companion.trace_id, source.experience.experience_id,
    ):
        assert private.encode() not in result.trainer_bytes
    assert result.provenance[0]["experience_id"] == source.experience.experience_id


@pytest.mark.parametrize("profile_id", PROFILES)
def test_failed_profile_is_valid_evidence_but_never_a_successful_bundle(tmp_path, profile_id):
    source, _ = _record(tmp_path / "source", profile_id, formula="=0")
    _, _, _, breakdown = verify_recorded(source)
    assert breakdown["outcome"] < 1
    assert "blocked_required:recalculate_model" in breakdown["process_violations"]
    with pytest.raises(ValueError, match="VERIFIER_"):
        admit_experience(source, registry=authorized_registry())
    with pytest.raises(ValueError, match="VERIFIER_"):
        compile_verified_bundle([source], _recipe(source), registry=authorized_registry())


def test_reidentified_unknown_provenance_is_not_an_admission_override(tmp_path):
    source, _ = _record(tmp_path / "source", PROFILES[0])
    trace = source.companion.model_copy(deep=True)
    trace.metadata["caller-profile-override"] = {"source_digest": "a" * 64, "accepted": True}
    forged = _rebind_companion(source, trace)
    with pytest.raises(ValueError):
        verify_recorded(forged)
    with pytest.raises(ValueError):
        admit_experience(forged, registry=authorized_registry())


def test_reidentified_other_allowed_profile_cannot_relabel_source_bytes(tmp_path):
    source, _ = _record(tmp_path / "source", PROFILES[0])
    trace = source.companion.model_copy(deep=True)
    assert trace.metadata["profile"]["profile_id"] == PROFILES[0]
    # Supply a fully valid *other* profile declaration and repair companion bindings.
    # The actual retained source still must match that independently regenerated profile.
    trace.metadata["profile"] = profile_provenance(PROFILES[1])
    forged = _rebind_companion(source, trace)
    with pytest.raises(ValueError):
        verify_recorded(forged)


def test_arbitrary_episode_changes_cannot_become_an_allowed_profile(tmp_path):
    recorder = PublicTrainingRecorder(tmp_path / "source", profile_id=PROFILES[0])
    recorder.runtime.episode.records[0].fields["caller-added-content"] = "not in finite grammar"
    # Recompute the ordinary recorder commitments rather than relying on a stale
    # contract mismatch. Only the independently regenerated allowlist can admit it.
    recorder.contract = compile_operational_episode(recorder.runtime.episode.model_copy(deep=True))
    recorder.source_digest = canonical_hash(recorder.runtime.episode.model_dump(mode="json"))
    source = recorder.submit(EpisodeSubmission(conclusion="No fabricated acceptance"))
    with pytest.raises(ValueError):
        verify_recorded(source)


@pytest.mark.parametrize("profile_id", PROFILES)
def test_native_artifact_mutation_still_requires_fresh_verification(tmp_path, profile_id):
    source, _ = _record(tmp_path / "source", profile_id)
    admit_experience(source, registry=authorized_registry())
    raw = source.experience.trajectory.private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY]
    Path(raw["native_submission"]["artifact_path"]).write_bytes(b"tampered retained artifact")
    with pytest.raises(ValueError, match="REVERIFICATION"):
        verify_recorded(source)
    with pytest.raises(ValueError, match="REVERIFICATION"):
        admit_experience(source, registry=authorized_registry())


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "veritas.public-training-profile.v999"),
        ("generator_digest", "0" * 64),
        ("configuration_digest", "1" * 64),
        ("structure_digest", "2" * 64),
        ("parent_source_digest", "3" * 64),
        ("source_kind", "REAL_SOURCE"),
        ("profile_id", "financial-unrestricted-v2"),
    ],
)
def test_reidentified_profile_provenance_tamper_rejects(tmp_path, field, value):
    source, _ = _record(tmp_path / "source", PROFILES[0])
    trace = source.companion.model_copy(deep=True)
    trace.metadata["profile"][field] = value
    forged = _rebind_companion(source, trace)
    with pytest.raises(ValueError):
        verify_recorded(forged)
    with pytest.raises(ValueError):
        admit_experience(forged, registry=authorized_registry())


def test_distinct_profile_tasks_keep_exact_success_lineage(tmp_path):
    sources = [_record(tmp_path / str(index), profile)[0] for index, profile in enumerate(PROFILES)]
    result = compile_verified_bundle(sources, _recipe(sources[0]), registry=authorized_registry())
    assert len(result.bundle.train_examples) == 2
    assert len(result.provenance) == 2
    assert {r["task_id"] for r in result.provenance} == {s.companion.task_id for s in sources}
    assert len({r["source_digest"] for r in result.provenance}) == 2
    for source in sources:
        with pytest.raises(ValueError, match="OVERLAP"):
            compile_verified_bundle(
                sources,
                _recipe(sources[0]),
                registry=authorized_registry(),
                frozen_panel_task_ids=(source.companion.task_id,),
            )


def test_existing_gap_selection_and_derivation_providers_accept_only_fresh_profiles(tmp_path):
    failed = [_record(tmp_path / f"failed-{index}", PROFILES[0], formula=value)
              for index, value in enumerate(("=0", "bad"))]
    pairs = tuple(
        (
            execute_counterfactual_experience(
                source,
                branch_step=0,
                replacement=replacement,
                artifact_root=tmp_path / f"contrast-{index}",
            ),
            source,
        )
        for index, (source, replacement) in enumerate(failed)
    )
    families = intervention_failure_families(pairs)
    assert len(families) == 1
    gap = ingest_capability_failure(families[0], sources=pairs)
    assert gap.candidate.gap.frequency == 2
    assert gap.capability_mapping == "DECLARED_TASK_ASSOCIATION"
    assert gap.causal_qualification == "UNKNOWN"
    success, _ = _record(tmp_path / "success", PROFILES[0])
    report = select_experiences(
        [success, failed[0][0]], gap_sources=pairs, policy=SelectionPolicy(max_items=2)
    )
    assert report.selected_count == 1
    assert report.rejection_counts == {"failed_not_training_candidate": 1}
    assert report.decisions[0].recorded_cost is not None
    assert report.resources.recorded_gap_execution_cost > 0
    assert report.training_qualified is False
    assert report.training_usefulness == "UNKNOWN"
    compilation = compile_learning_assets(
        [source for _, source in pairs], receipts=[receipt for receipt, _ in pairs]
    )
    assert {asset.transform.kind for asset in compilation.assets} >= {
        "negative", "counterfactual", "recovery", "next_state",
    }
    assert validate_compilation(
        compilation,
        sources=[source for _, source in pairs],
        receipts=[receipt for receipt, _ in pairs],
    ) == compilation
    for asset in compilation.assets:
        assert not asset.training_qualified
        assert asset.training_usefulness == "UNKNOWN"
        assert asset.visibility.value == "evaluator_private"
        assert asset.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
        with pytest.raises(ValueError, match="CANDIDATE_NOT_TRAINING_ADMITTED"):
            asset.trainer_payload()

    # These are disjoint panel declarations only, not loaded held-out tasks or
    # execution observations. Absence of model screens must stay UNKNOWN.
    capability = CapabilitySpec(contract=success.capability)

    def ref(name):
        return ExperienceReference(
            reference_id=name,
            reference_type="CONSTRUCTED_DECLARATION",
            digest=hashlib.sha256(name.encode()).hexdigest(),
        )

    def panel(name):
        return EvaluationPopulation(
            capability=capability,
            conditions=EvaluationConditions(
                environment_id="constructed-public-profile-world",
                environment_revision="v2",
                verifier_id="constructed-panel-declaration",
                verifier_revision="v1",
                metric="success_fraction",
                metric_definition_digest="a" * 64,
                distribution_id="constructed-disjoint-panel",
                structure_id=name,
                interface_id="constructed-interface",
                evidence_references=(ref(name + "-conditions"),),
            ),
            split="HELD_OUT",
            members=(ref(name + "-member"),),
            evidence_references=(ref(name + "-commitment"),),
        )

    expected = dict(
        graph=PrerequisiteGraph(specs=(capability,)),
        panels=FixedPanels(
            validation=(panel("constructed-validation"),),
            final_test=(panel("constructed-final"),),
        ),
        observation=FrontierObservation(),
        model_id="constructed-unexecuted-model",
        model_revision="constructed-unexecuted-checkpoint-0",
        policy=CurriculumPolicy(),
        gap_sources=pairs,
    )
    plan = build_curriculum([success], **expected)
    assert len(plan.candidates) == 1
    assert plan.stages[0].choices[0].reason == "fallback_no_observation"
    assert plan.qualification == "UNKNOWN"
    assert plan.observation.execution_attestation == "UNKNOWN"
    assert plan.candidates[0].experience_id == success.experience.experience_id
    assert not plan.candidates[0].training_qualified
    assert validate_curriculum(plan, [success], **expected) == plan
    assert plan.public_payload() == {"status": "UNKNOWN", "reason": "evidence_not_visible"}
