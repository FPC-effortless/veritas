"""Constructed public TRAIN-derived native fixture; no protected split is generated."""

import json

import pytest

from investigation_world.experience import MachineExperience
from investigation_world.experience.diagnostics import buyer_safe_diagnostics, diagnose_experience
from investigation_world.foundry.models import stable_hash
from investigation_world.operational import NativeOperationalRuntime, OperationalDistributionConfig
from investigation_world.operational.distribution import iter_operational_distribution
from investigation_world.operational.models import (
    ActionKind,
    EpisodeSubmission,
    HiddenActionEffect,
    PublicActionSpec,
)
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import (
    ArtifactIdentity,
    OperationalRuntimeAdapterContext,
    TrajectoryV2,
    VisibilityClass,
    canonical_hash,
    trajectory_v2_from_operational_runtime,
)
from investigation_world.trajectory.reverify import (
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    attach_operational_replay_evidence,
    current_operational_verifier_binding,
)


def native_fixture(root, *, matching=True, unresolved=False):
    case = next(
        iter_operational_distribution(
            OperationalDistributionConfig(
                seed=73,
                train_per_domain=1,
                iid_per_domain=1,
                ood_per_domain=1,
                adversarial_per_domain=1,
            )
        )
    )
    assert case.split.value == "train"
    episode = case.episode.model_copy(deep=True)
    first_action = episode.oracle.required_actions[0]
    # Optional synthetic acknowledgement has a real prerequisite and no artifact effect.
    episode.task.available_actions.append(
        PublicActionSpec(
            name="diagnostic_acknowledge",
            kind=ActionKind.WRITE,
            system=episode.task.permitted_systems[0],
            description="Synthetic prerequisite probe",
            parameter_names=["message"],
            cost=1,
        )
    )
    episode.oracle.action_effects.append(
        HiddenActionEffect(
            action_name="diagnostic_acknowledge",
            required_parameters={"message": "ok"},
            required_prior_actions=[first_action],
            set_state={"diagnostic.acknowledged": True},
        )
    )
    if unresolved:
        episode.oracle.required_actions.append("diagnostic_acknowledge")
    runtime = NativeOperationalRuntime(episode, artifact_root=root)
    initial = runtime.state_snapshot()
    runtime.act("diagnostic_acknowledge", message="ok")
    assert runtime.events[-1].blocked
    for action in episode.oracle.required_actions[:]:
        if action == "diagnostic_acknowledge":
            continue
        effects = [e for e in episode.oracle.action_effects if e.action_name == action]
        for ordinal in range(episode.oracle.required_action_counts.get(action, 1)):
            runtime.act(action, **effects[min(ordinal, len(effects) - 1)].required_parameters)
    if matching:
        runtime.act("diagnostic_acknowledge", message="ok")
        assert runtime.events[-1].effect_applied
    submission = EpisodeSubmission(
        conclusion="Synthetic native fixture", evidence_ids=episode.oracle.required_evidence_ids
    )
    contract = compile_operational_episode(runtime.episode)
    result = runtime.submit(submission)
    receipt = runtime.last_native_submission
    assert receipt is not None
    trajectory = trajectory_v2_from_operational_runtime(
        runtime,
        context=OperationalRuntimeAdapterContext(
            submission=submission,
            breakdown=result,
            initial_state_digest=stable_hash(initial),
            portable_operational_contract=ArtifactIdentity(
                artifact_id=contract.contract_id,
                contract="veritas.portable-operational-contract",
                version="1.0.0",
            ),
            terminated=True,
            truncated=False,
        ),
    )
    final = json.loads(receipt.final_state_json)
    evidence = OperationalReplayEvidence(
        portable_contract=contract,
        trajectory_events_digest=canonical_hash(trajectory.events),
        initial_state=initial,
        initial_state_digest=stable_hash(initial),
        final_state=final,
        final_state_digest=stable_hash(final),
        action_events=tuple(runtime.events),
        submission=submission,
        tool_calls=runtime.budget.calls,
        cost_spent=runtime.budget.spent,
        native_submission=receipt,
    )
    payload = trajectory.model_dump(mode="python")
    payload.update(trajectory_id="", evidence_references=(evidence.reference(),))
    trajectory = TrajectoryV2.model_validate(payload)
    return MachineExperience(
        trajectory=attach_operational_replay_evidence(
            trajectory, evidence.for_trajectory(trajectory)
        )
    )


def registry():
    return AuthorizedVerifierRegistry((current_operational_verifier_binding(),))


def test_executed_native_retry_is_observed_not_causal_or_public(tmp_path):
    experience = native_fixture(tmp_path)
    report = diagnose_experience(experience, registry=registry())
    refs = report.diagnostics.successful_recovery_references
    assert refs, report.unavailable
    ref = refs[0]
    assert ref.visibility is VisibilityClass.EVALUATOR_PRIVATE
    assert ref.public_metadata["status"] == "OBSERVED"
    assert ref.public_metadata["causal_status"] == "UNKNOWN"
    assert ref.public_metadata["start_step"] == 0
    assert ref.public_metadata["end_step"] > 0
    assert ref.public_metadata["receipt_id"]
    assert ref.public_metadata["record_id"]
    assert buyer_safe_diagnostics(experience)["status"] == "UNKNOWN"


@pytest.mark.parametrize("matching,unresolved", [(False, False), (True, True)])
def test_no_recovery_for_absent_retry_or_unresolved_violation(tmp_path, matching, unresolved):
    experience = native_fixture(tmp_path, matching=matching, unresolved=unresolved)
    assert not diagnose_experience(
        experience, registry=registry()
    ).diagnostics.successful_recovery_references


@pytest.mark.parametrize("change", ["gap", "reorder", "missing_receipt"])
def test_incomplete_or_substituted_execution_binding_cannot_report_recovery(tmp_path, change):
    from investigation_world.trajectory.reverify import REPLAY_EVIDENCE_PRIVATE_KEY

    experience = native_fixture(tmp_path)
    payload = experience.model_dump(mode="python")
    if change == "gap":
        payload["trajectory"]["events"][0]["step"] = 100
    elif change == "reorder":
        events = list(payload["trajectory"]["events"])
        events[0], events[1] = events[1], events[0]
        payload["trajectory"]["events"] = events
    else:
        payload["trajectory"]["private_metadata"][REPLAY_EVIDENCE_PRIVATE_KEY][
            "native_submission"
        ] = None
    payload["trajectory"]["trajectory_id"] = ""
    payload["experience_id"] = ""
    try:
        tampered = MachineExperience.model_validate(payload)
    except ValueError:
        return  # Canonical input boundary may reject before diagnostic execution.
    assert not diagnose_experience(
        tampered, registry=registry()
    ).diagnostics.successful_recovery_references


def test_existing_same_id_record_cannot_inject_private_verifier_reasons(tmp_path):
    from investigation_world.trajectory import ReverificationRecord
    from investigation_world.trajectory.reverify import reverify_trajectory

    experience = native_fixture(tmp_path)
    result = reverify_trajectory(
        experience.trajectory, verifier=experience.trajectory.verifier, registry=registry()
    )
    assert result.record is not None
    raw = result.record.model_dump(mode="python")
    raw["private_metadata"]["verification_breakdown"]["forbidden_actions_taken"] = ["FORGED-REASON"]
    forged = ReverificationRecord.model_validate(raw)
    assert forged.record_id == result.record.record_id
    trajectory = experience.trajectory.with_reverification(forged)
    report = diagnose_experience(MachineExperience(trajectory=trajectory), registry=registry())
    assert not report.observations
    assert report.diagnostics.successful_recovery_references
    assert "FORGED-REASON" not in report.model_dump_json()
