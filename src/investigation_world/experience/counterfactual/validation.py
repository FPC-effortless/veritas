"""Evaluator-private, public-fixture-only source validation (no training admission)."""

from __future__ import annotations

import copy
import json

from investigation_world.experience import MachineExperience, machine_experience_from_trajectory
from investigation_world.experience_foundry.admission import (
    COMPANION_SOURCE,
    RECORDER_VERSION,
    RecordedExperience,
    authorized_registry,
    public_training_fixture,
    runtime_source_digest,
)
from investigation_world.foundry.models import (
    DistributionSplit,
    RolloutTrace,
    TraceEvent,
)
from investigation_world.operational.models import StateAssertion
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import (
    TrajectoryV2,
    VisibilityClass,
    canonical_hash,
)
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    OperationalReplayEvidence,
    ReverificationStatus,
    current_operational_verifier_binding,
    reverify_trajectory,
)


def _trace_id(trace: RolloutTrace) -> str:
    return "bridge-trace-" + canonical_hash(trace.model_dump(mode="json", exclude={"trace_id"}))


def _trace_events(trajectory: TrajectoryV2) -> list[TraceEvent]:
    # Native evaluator transitions remain in the private companion, never trainer bytes.
    if any(event.cost is None for event in trajectory.events):
        raise ValueError("EVENT_COST_EVIDENCE_REQUIRED")
    return [
        TraceEvent(
            step=e.step,
            event_type=e.event_type,
            payload=copy.deepcopy(e.payload),
            state_hash_before=e.state_before.digest if e.state_before else None,
            state_hash_after=e.state_after.digest if e.state_after else None,
            cost=float(e.cost),  # type: ignore[arg-type]
        )
        for e in trajectory.events
    ]


def verify_recorded(source: RecordedExperience):
    """Revalidate the pinned recorder profile and reverify failures as well as successes."""
    registry = authorized_registry()
    experience = MachineExperience.model_validate(source.experience.model_dump(mode="python"))
    trajectory = experience.trajectory
    # Only recorder-produced E0 wrappers are in this profile. Caller readiness,
    # diagnostics, annotations and private/public metadata cannot add authority.
    if experience != machine_experience_from_trajectory(trajectory):
        raise ValueError("RECORDER_EXPERIENCE_PROFILE_MISMATCH")
    trace = RolloutTrace.model_validate(source.companion.model_dump(mode="python"))
    case, capability = public_training_fixture()
    expected_episode = case.episode
    if source.capability.model_dump(mode="json") != capability.model_dump(mode="json"):
        raise ValueError("CAPABILITY_IDENTITY_MISMATCH")
    if (
        experience.visibility is not VisibilityClass.PUBLIC
        or trajectory.visibility is not VisibilityClass.PUBLIC
    ):
        raise ValueError("SOURCE_VISIBILITY_UNSUPPORTED")
    expected_event_visibility = {
        "act": VisibilityClass.PUBLIC,
        "submit": VisibilityClass.PUBLIC,
        "native_submission": VisibilityClass.EVALUATOR_PRIVATE,
    }
    if any(
        event.event_type not in expected_event_visibility
        or event.visibility is not expected_event_visibility[event.event_type]
        for event in trajectory.events
    ):
        raise ValueError("EVENT_VISIBILITY_PROFILE_MISMATCH")
    expected_provenance_visibility = {
        "operational.episode_execution": VisibilityClass.BUYER_SAFE,
        COMPANION_SOURCE: VisibilityClass.EVALUATOR_PRIVATE,
    }
    if any(
        item.source_kind not in expected_provenance_visibility
        or item.visibility is not expected_provenance_visibility[item.source_kind]
        for item in trajectory.provenance
    ):
        raise ValueError("PROVENANCE_VISIBILITY_PROFILE_MISMATCH")
    if trace.split is not DistributionSplit.TRAIN:
        raise ValueError("TRAIN_ONLY")
    if trace.trace_id != _trace_id(trace):
        raise ValueError("COMPANION_IDENTITY_MISMATCH")
    companions = [p for p in trajectory.provenance if p.source_kind == COMPANION_SOURCE]
    if len(companions) != 1 or (
        companions[0].source_id != trace.trace_id
        or companions[0].source_version != RECORDER_VERSION
        or companions[0].source_digest != canonical_hash(trace.model_dump(mode="json"))
    ):
        raise ValueError("COMPANION_BINDING_MISMATCH")
    raw = trajectory.private_metadata.get(REPLAY_EVIDENCE_PRIVATE_KEY)
    if raw is None:
        raise ValueError("REPLAY_REQUIRED")
    evidence = OperationalReplayEvidence.model_validate(raw)
    receipt = evidence.native_submission
    if receipt is None:
        raise ValueError("NATIVE_RECEIPT_REQUIRED")
    if json.loads(receipt.episode_json) != expected_episode.model_dump(mode="json"):
        raise ValueError("UNSUPPORTED_SOURCE_OR_SPLIT")
    expected_contract = compile_operational_episode(expected_episode)
    if evidence.portable_contract != expected_contract:
        raise ValueError("SOURCE_CONTRACT_MISMATCH")
    version = expected_episode.metadata["distribution_version"]
    # Check the real adapter's source and unknown identity profile independently of
    # caller-recomputed trajectory/companion hashes. The native runtime appends
    # verifier target keys after recording receipt.episode_json.
    post_episode = expected_episode.model_copy(deep=True)
    existing = {item.key() for item in post_episode.oracle.target_state}
    for key in sorted(json.loads(receipt.verification_json)["checks"]):
        if "native_artifact." + key not in existing:
            post_episode.oracle.target_state.append(
                StateAssertion(object_id="native_artifact", field_name=key, expected_value=True)
            )
    native_provenance = [
        p for p in trajectory.provenance if p.source_kind == "operational.episode_execution"
    ]
    if (
        len(trajectory.provenance) != 2
        or len(native_provenance) != 1
        or native_provenance[0].source_id != expected_episode.episode_id
        or native_provenance[0].source_digest
        != canonical_hash(post_episode.model_dump(mode="json"))
        or native_provenance[0].adapter_id != "veritas.operational-runtime-to-trajectory-v2"
        or native_provenance[0].adapter_version != "1"
        or native_provenance[0].source_version is not None
    ):
        raise ValueError("NATIVE_ADAPTER_SOURCE_MISMATCH")
    world = trajectory.world
    artifact = world.portable_operational_contract
    if (
        world.environment_id is not None
        or world.world_bundle is not None
        or world.world_id != expected_episode.world_id
        or world.environment_version != version
        or world.world_version != version
        or artifact is None
        or artifact.artifact_id != expected_contract.contract_id
        or artifact.contract != "veritas.portable-operational-contract"
        or artifact.version != expected_contract.schema_version
        or trajectory.task.task_id != expected_episode.task.task_id
        or trajectory.public_metadata
        or trajectory.capability_tags
        or trace.capability_tags
        or any(value is not None for value in trajectory.model.model_dump().values())
        or any(value is not None for value in trajectory.agent.model_dump().values())
        or any(value is not None for value in trajectory.harness.model_dump().values())
        or any(value is not None for value in trajectory.runtime.model_dump().values())
        or any(value is not None for value in trajectory.reset.model_dump().values())
    ):
        raise ValueError("CANONICAL_PROFILE_MISMATCH")
    expected_fields = {
        "task_id": expected_episode.task.task_id,
        "task_seed": case.seed,
        "environment_version": version,
        "taskset_version": version,
        "harness_version": RECORDER_VERSION,
        "runtime_version": runtime_source_digest(),
        "metadata": {
            "recorder": RECORDER_VERSION,
            "source_digest": canonical_hash(expected_episode.model_dump(mode="json")),
        },
        "initial_state_hash": evidence.initial_state_digest,
        "final_state_hash": evidence.final_state_digest,
        "total_cost": float(evidence.cost_spent),
        "termination_reason": "episode_submitted",
    }
    if any(getattr(trace, key) != value for key, value in expected_fields.items()):
        raise ValueError("COMPANION_SOURCE_MISMATCH")
    if trace.events != _trace_events(trajectory):
        raise ValueError("COMPANION_EVENT_MISMATCH")
    if (
        trace.verifier_components != trajectory.original_evaluation.component_scores
        or trace.total_reward != trajectory.original_evaluation.reward
    ):
        raise ValueError("COMPANION_EVALUATION_MISMATCH")
    # Canonical unknowns stay unknown; enriched private companion is not an inverse adapter.
    if (
        trajectory.task.split is not None
        or trajectory.reset.seed is not None
        or trajectory.task.taskset_version is not None
        or trajectory.runtime.version is not None
    ):
        raise ValueError("CANONICAL_PROFILE_MISMATCH")
    if (
        trajectory.termination.terminated is not True
        or trajectory.termination.truncated is not False
        or trajectory.termination.reason != "episode_submitted"
    ):
        raise ValueError("TERMINAL_EVIDENCE_REQUIRED")
    binding = current_operational_verifier_binding()
    if trajectory.verifier != binding.identity:
        raise ValueError("VERIFIER_IDENTITY_MISMATCH")
    # Prior records are caller input, including private annotations. Reverify the
    # identical execution identity without cached history so ALREADY_RECORDED
    # cannot return a caller-edited private breakdown in place of the fresh one.
    fresh_input = TrajectoryV2.model_validate(
        {
            **trajectory.model_dump(mode="python"),
            "reverifications": (),
        }
    )
    assert fresh_input.trajectory_id == trajectory.trajectory_id
    outcome = reverify_trajectory(fresh_input, verifier=binding.identity, registry=registry)
    if outcome.status not in (
        ReverificationStatus.REVERIFIED,
        ReverificationStatus.ALREADY_RECORDED,
    ):
        raise ValueError("REVERIFICATION_" + outcome.status.value.upper())
    record = outcome.record
    if record is None:
        raise ValueError("REVERIFICATION_RECORD_REQUIRED")
    breakdown = record.private_metadata.get("verification_breakdown")
    if not isinstance(breakdown, dict):
        raise ValueError("EXPLICIT_VERIFIER_EVIDENCE_REQUIRED")
    if (
        record.component_scores != trajectory.original_evaluation.component_scores
        or record.reward != trajectory.original_evaluation.reward
    ):
        raise ValueError("ORIGINAL_EVALUATION_DRIFT")
    return RecordedExperience(experience, trace, capability), evidence, record, breakdown
