import pytest

from investigation_world.experience_foundry.admission import (
    PublicTrainingRecorder,
    admit_experience,
    authorized_registry,
)


def recorded(tmp_path):
    recorder = PublicTrainingRecorder(tmp_path)
    for action in recorder.runtime.episode.oracle.required_actions:
        effects = [
            e for e in recorder.runtime.episode.oracle.action_effects if e.action_name == action
        ]
        for effect in effects:
            recorder.act(action, **effect.required_parameters)
    from investigation_world.operational import EpisodeSubmission

    return recorder.submit(
        EpisodeSubmission(
            conclusion="Public fixture completed",
            evidence_ids=recorder.runtime.episode.oracle.required_evidence_ids,
        )
    )


def test_real_runtime_admission(tmp_path):
    source = recorded(tmp_path)
    accepted = admit_experience(source, registry=authorized_registry())
    assert accepted.verified.assessment.terminal_success
    assert accepted.verified.assessment.invariant_pass
    assert source.experience.trajectory.reset.seed is None
    assert source.experience.trajectory.task.split is None
    assert source.companion.task_seed != 0


def test_unauthorized_registry_rejects(tmp_path):
    from investigation_world.trajectory.reverify import AuthorizedVerifierRegistry

    with pytest.raises(ValueError, match="REVERIFICATION"):
        admit_experience(recorded(tmp_path), registry=AuthorizedVerifierRegistry(()))


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_seed", 0),
        ("runtime_version", "invented"),
        ("harness_version", "unknown"),
        ("initial_state_hash", "fake"),
        ("final_state_hash", None),
        ("split", "iid_test"),
        ("split", "ood"),
        ("split", "adversarial"),
        ("total_reward", -1),
        ("taskset_version", "invented"),
    ],
)
def test_changed_companion_fails_closed(tmp_path, field, value):
    from dataclasses import replace

    source = recorded(tmp_path)
    trace = source.companion.model_copy(update={field: value})
    with pytest.raises(ValueError):
        admit_experience(replace(source, companion=trace), registry=authorized_registry())


def _changed_trajectory(source, **changes):
    from dataclasses import replace

    from investigation_world.experience import machine_experience_from_trajectory
    from investigation_world.trajectory import TrajectoryV2

    payload = source.experience.trajectory.model_dump(mode="python")
    payload.update(changes)
    payload["trajectory_id"] = ""
    trajectory = TrajectoryV2.model_validate(payload)
    return replace(source, experience=machine_experience_from_trajectory(trajectory))


def test_missing_replay_fails_closed(tmp_path):
    source = _changed_trajectory(recorded(tmp_path), private_metadata={})
    with pytest.raises(ValueError, match="REPLAY_REQUIRED"):
        admit_experience(source, registry=authorized_registry())


def test_private_experience_cannot_be_widened(tmp_path):
    from dataclasses import replace

    from investigation_world.experience import MachineExperience

    source = recorded(tmp_path)
    payload = source.experience.model_dump(mode="python")
    payload.update(visibility="evaluator_private", experience_id="")
    source = replace(source, experience=MachineExperience.model_validate(payload))
    with pytest.raises(ValueError, match="VISIBILITY"):
        admit_experience(source, registry=authorized_registry())


@pytest.mark.parametrize("identity", ["world", "runtime", "harness", "model", "provenance"])
def test_reidentified_identity_drift_rejects(tmp_path, identity):
    source = recorded(tmp_path)
    trajectory = source.experience.trajectory
    if identity == "world":
        change = trajectory.world.model_copy(update={"world_version": "drift"})
    elif identity == "runtime":
        change = trajectory.runtime.model_copy(update={"runtime_id": "other"})
    elif identity == "harness":
        change = trajectory.harness.model_copy(update={"harness_id": "other"})
    elif identity == "model":
        change = trajectory.model.model_copy(update={"snapshot": "claimed"})
    else:
        change = tuple(
            p.model_copy(update={"adapter_version": "drift"})
            if p.source_kind == "operational.episode_execution"
            else p
            for p in trajectory.provenance
        )
    source = _changed_trajectory(source, **{identity: change})
    with pytest.raises(ValueError, match="MISMATCH"):
        admit_experience(source, registry=authorized_registry())


def test_unsuccessful_real_runtime_rejects(tmp_path):
    from investigation_world.operational import EpisodeSubmission

    source = PublicTrainingRecorder(tmp_path).submit(EpisodeSubmission(conclusion="No work"))
    with pytest.raises(ValueError, match="VERIFIER_"):
        admit_experience(source, registry=authorized_registry())


def test_explicit_invariant_failure_rejects(tmp_path):
    recorder = PublicTrainingRecorder(tmp_path)
    oracle = recorder.runtime.episode.oracle
    for effect in oracle.action_effects:
        if effect.forbidden:
            spec = next(
                a
                for a in recorder.runtime.episode.task.available_actions
                if a.name == effect.action_name
            )
            parameters = {name: "A1:A2" for name in spec.parameter_names}
            parameters.update(effect.required_parameters)
            recorder.act(effect.action_name, **parameters)
    from investigation_world.operational import EpisodeSubmission

    source = recorder.submit(EpisodeSubmission(conclusion="Unsafe run"))
    with pytest.raises(ValueError, match="VERIFIER_"):
        admit_experience(source, registry=authorized_registry())


def test_caller_pass_history_cannot_replace_fresh_verification(tmp_path):
    from investigation_world.trajectory.reverify import (
        current_operational_verifier_binding,
        reverify_trajectory,
    )

    source = recorded(tmp_path)
    outcome = reverify_trajectory(
        source.experience.trajectory,
        verifier=current_operational_verifier_binding().identity,
        registry=authorized_registry(),
    )
    # A poison value in a cached private annotation cannot replace the actual verifier result.
    record = outcome.record.model_copy(deep=True)
    record.private_metadata["verification_breakdown"]["outcome"] = -100.0
    source = _changed_trajectory(source, reverifications=(record,))
    admitted = admit_experience(source, registry=authorized_registry())
    assert admitted.verified.assessment.verifier_score == 1.0


def test_admission_does_not_mutate_source(tmp_path):
    source = recorded(tmp_path)
    before = source.experience.model_dump(mode="json"), source.companion.model_dump(mode="json")
    admit_experience(source, registry=authorized_registry())
    assert before == (
        source.experience.model_dump(mode="json"),
        source.companion.model_dump(mode="json"),
    )


def test_caller_pass_cannot_admit_a_failed_execution(tmp_path):
    from investigation_world.operational import EpisodeSubmission
    from investigation_world.trajectory.reverify import (
        current_operational_verifier_binding,
        reverify_trajectory,
    )

    source = PublicTrainingRecorder(tmp_path).submit(EpisodeSubmission(conclusion="No work"))
    outcome = reverify_trajectory(
        source.experience.trajectory,
        verifier=current_operational_verifier_binding().identity,
        registry=authorized_registry(),
    )
    record = outcome.record.model_copy(deep=True)
    record.private_metadata["verification_breakdown"].update(
        outcome=1.0,
        invariant_violations=[],
        missing_required_actions=[],
        missing_evidence_ids=[],
        process_violations=[],
    )
    source = _changed_trajectory(source, reverifications=(record,))
    with pytest.raises(ValueError, match="VERIFIER_"):
        admit_experience(source, registry=authorized_registry())


def test_missing_native_receipt_rejects(tmp_path):
    source = recorded(tmp_path)
    trajectory = source.experience.trajectory
    raw = trajectory.model_dump(mode="python")["private_metadata"]
    evidence = raw["operational_reverification_evidence"]
    evidence.update(native_submission=None, evidence_id="", evidence_digest="")
    source = _changed_trajectory(source, private_metadata=raw)
    with pytest.raises(ValueError, match="NATIVE_RECEIPT_REQUIRED"):
        admit_experience(source, registry=authorized_registry())


def test_capability_mutation_rejects(tmp_path):
    from dataclasses import replace

    source = recorded(tmp_path)
    capability = source.capability.model_copy(update={"objective": "changed"})
    with pytest.raises(ValueError, match="CAPABILITY"):
        admit_experience(replace(source, capability=capability), registry=authorized_registry())


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_seed", 1),
        ("taskset_version", "claimed-version"),
        ("initial_state_hash", "rehashed-but-untrue"),
    ],
)
def test_rehashed_companion_still_requires_source_evidence(tmp_path, field, value):
    from dataclasses import replace

    from investigation_world.experience import machine_experience_from_trajectory
    from investigation_world.trajectory import canonical_hash

    source = recorded(tmp_path)
    trace = source.companion.model_copy(update={field: value}, deep=True)
    trace.trace_id = "bridge-trace-" + canonical_hash(
        trace.model_dump(mode="json", exclude={"trace_id"})
    )
    trajectory = source.experience.trajectory.model_copy(deep=True)
    provenance = list(trajectory.provenance)
    provenance[1] = provenance[1].model_copy(
        update={
            "source_id": trace.trace_id,
            "source_digest": canonical_hash(trace.model_dump(mode="json")),
        }
    )
    trajectory = trajectory.model_copy(update={"provenance": tuple(provenance)})
    source = replace(
        source, companion=trace, experience=machine_experience_from_trajectory(trajectory)
    )
    with pytest.raises(ValueError, match="COMPANION_SOURCE_MISMATCH"):
        admit_experience(source, registry=authorized_registry())


def test_missing_invariant_contract_rejects(tmp_path):
    source = recorded(tmp_path)
    raw = source.experience.trajectory.model_dump(mode="python")["private_metadata"]
    raw["operational_reverification_evidence"]["portable_contract"]["private"]["semantic_state"][
        "invariants"
    ] = []
    source = _changed_trajectory(source, private_metadata=raw)
    with pytest.raises(ValueError):
        admit_experience(source, registry=authorized_registry())


@pytest.mark.parametrize("index,visibility", [(0, "evaluator_private"), (1, "public")])
def test_provenance_visibility_profile_rejects(tmp_path, index, visibility):
    from investigation_world.trajectory import VisibilityClass

    source = recorded(tmp_path)
    provenance = list(source.experience.trajectory.provenance)
    provenance[index] = provenance[index].model_copy(
        update={"visibility": VisibilityClass(visibility)}
    )
    source = _changed_trajectory(source, provenance=tuple(provenance))
    with pytest.raises(ValueError, match="VISIBILITY"):
        admit_experience(source, registry=authorized_registry())
