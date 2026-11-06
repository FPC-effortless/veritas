"""First public native TRAIN fixture and exact, fail-closed companion admission.

ponytail: the original fixture and two closed structural derivatives only;
new profiles need equivalent regeneration evidence, not an inferred inverse adapter.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investigation_world.experience import MachineExperience, machine_experience_from_trajectory
from investigation_world.experience_foundry.public_profiles import (
    profile_fixture,
    profile_id_from_trace,
    recorder_metadata,
    recorder_version,
    validate_profile_action_events,
)
from investigation_world.foundry.expert_trajectories import (
    ExpertiseAssessment,
    TrainingUse,
    TrajectoryRole,
    VerifiedTrajectory,
)
from investigation_world.foundry.models import (
    CapabilityContract,
    DistributionSplit,
    RolloutTrace,
    TraceEvent,
    stable_hash,
)
from investigation_world.operational import (
    EpisodeSubmission,
    NativeOperationalRuntime,
    native_runtime,
)
from investigation_world.operational import runtime as runtime_module
from investigation_world.operational.artifacts import attach_native_artifact_descriptor
from investigation_world.operational.distribution import (
    OperationalDistributionConfig,
    iter_operational_distribution,
)
from investigation_world.operational.models import StateAssertion, capability_binding_from_contract
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.trajectory import (
    ArtifactIdentity,
    OperationalRuntimeAdapterContext,
    TrajectoryV2,
    VisibilityClass,
    canonical_hash,
    trajectory_v2_from_operational_runtime,
)
from investigation_world.trajectory.models import ProvenanceRecord
from investigation_world.trajectory.reverify import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    AuthorizedVerifierRegistry,
    OperationalReplayEvidence,
    ReverificationStatus,
    attach_operational_replay_evidence,
    current_operational_verifier_binding,
    reverify_trajectory,
)

RECORDER_VERSION = "veritas.public-financial-training-recorder.v1"
TRANSFORM_VERSION = "veritas.verified-learning-sft.v1"
COMPANION_SOURCE = "experience_foundry.original_rollout_companion"
_COMPONENTS = (
    "outcome",
    "state",
    "constraints",
    "side_effects",
    "process",
    "efficiency",
    "evidence",
)


def authorized_registry() -> AuthorizedVerifierRegistry:
    return AuthorizedVerifierRegistry((current_operational_verifier_binding(),))


def runtime_source_digest() -> str:
    """Actual installed bytes, not an invented runtime version."""
    return canonical_hash(
        {
            name: hashlib.sha256(Path(str(module.__file__)).read_bytes()).hexdigest()
            for name, module in (("runtime", runtime_module), ("native_runtime", native_runtime))
        }
    )


def public_training_fixture():
    """Generate exactly one public synthetic TRAIN case; never traverse held-out cases."""
    config = OperationalDistributionConfig(
        seed=73,
        train_per_domain=1,
        iid_per_domain=1,
        ood_per_domain=1,
        adversarial_per_domain=1,
    )
    case = next(iter_operational_distribution(config))
    capability = CapabilityContract(
        capability_id="public-financial-formula-repair",
        objective="Repair the public synthetic native financial workbook",
        success_conditions=[item.key() for item in case.episode.oracle.target_state],
        hard_invariants=[item.invariant_id for item in case.episode.oracle.invariants],
    )
    case.episode.capability = capability_binding_from_contract(capability, case.episode)
    attach_native_artifact_descriptor(case.episode)
    return case, capability


@dataclass(frozen=True)
class RecordedExperience:
    """Evaluator-side source objects, never a trainer export or attestation."""

    experience: MachineExperience
    companion: RolloutTrace
    capability: CapabilityContract


@dataclass(frozen=True)
class AdmittedExperience:
    source: RecordedExperience
    verified: VerifiedTrajectory
    lineage: dict[str, str]


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


class PublicTrainingRecorder:
    """Capture an original companion during real execution of the supported fixture.

    This is a recorder, not a policy/trainer. Callers supply actual actions and submission.
    Observations are not invented; this SFT format records only the submitted action sequence.
    """

    def __init__(self, artifact_root: str | Path, *, profile_id: str | None = None):
        self.profile_id = profile_id
        self.recorder_version = recorder_version(profile_id)
        self.case, self.capability = profile_fixture(profile_id)
        self.runtime = NativeOperationalRuntime(
            self.case.episode.model_copy(deep=True), artifact_root=artifact_root
        )
        self.contract = compile_operational_episode(self.runtime.episode.model_copy(deep=True))
        self.initial = self.runtime.state_snapshot()
        self.events: list[TraceEvent] = []
        self.source_digest = canonical_hash(self.runtime.episode.model_dump(mode="json"))
        self.runtime_digest = runtime_source_digest()

    def act(self, action_name: str, **parameters: Any) -> dict[str, Any]:
        result = self.runtime.act(action_name, **parameters)
        event = self.runtime.events[-1]
        self.events.append(
            TraceEvent(
                step=event.sequence - 1,
                event_type="act",
                cost=float(event.cost),
                payload={
                    "method": "act",
                    "action_name": event.action_name,
                    "args": [event.action_name],
                    "kwargs": copy.deepcopy(event.parameters),
                    "success": bool(event.effect_applied and not event.blocked),
                },
            )
        )
        return result

    def submit(self, submission: EpisodeSubmission) -> RecordedExperience:
        if len(self.events) != len(self.runtime.events):
            raise ValueError("UNRECORDED_ACTION")
        result = self.runtime.submit(submission)
        receipt = self.runtime.last_native_submission
        if receipt is None:
            raise ValueError("NATIVE_RECEIPT_REQUIRED")
        context = OperationalRuntimeAdapterContext(
            world_version=self.case.episode.metadata["distribution_version"],
            portable_operational_contract=ArtifactIdentity(
                artifact_id=self.contract.contract_id,
                contract="veritas.portable-operational-contract",
                version=self.contract.schema_version,
            ),
            submission=submission,
            breakdown=result,
            truncated=False,
        )
        preliminary = trajectory_v2_from_operational_runtime(self.runtime, context=context)
        mapped = _trace_events(preliminary)
        if mapped[: len(self.events)] != self.events:
            raise ValueError("RECORDED_ACTION_DRIFT")
        companion = RolloutTrace(
            trace_id="",
            environment_version=self.case.episode.metadata["distribution_version"],
            task_id=self.case.episode.task.task_id,
            task_seed=self.case.seed,
            split=self.case.split,
            taskset_version=self.case.episode.metadata["distribution_version"],
            harness_version=self.recorder_version,
            runtime_version=self.runtime_digest,
            initial_state_hash=stable_hash(self.initial),
            events=[*self.events, *mapped[len(self.events) :]],
            verifier_components={name: float(getattr(result, name)) for name in _COMPONENTS},
            total_reward=result.overall_reward,
            final_state_hash=stable_hash(self.runtime.state_snapshot()),
            termination_reason="episode_submitted",
            total_cost=float(self.runtime.budget.spent),
            metadata=recorder_metadata(self.profile_id, self.source_digest),
        )
        companion.trace_id = _trace_id(companion)
        evidence = OperationalReplayEvidence(
            portable_contract=self.contract,
            trajectory_events_digest=canonical_hash(preliminary.events),
            initial_state=self.initial,
            initial_state_digest=stable_hash(self.initial),
            final_state=self.runtime.state_snapshot(),
            final_state_digest=stable_hash(self.runtime.state_snapshot()),
            action_events=tuple(self.runtime.events),
            submission=submission,
            tool_calls=self.runtime.budget.calls,
            cost_spent=self.runtime.budget.spent,
            native_submission=receipt,
        )
        context = context.model_copy(
            update={
                "evidence_references": (evidence.reference(),),
                "provenance": (
                    ProvenanceRecord(
                        source_kind=COMPANION_SOURCE,
                        source_id=companion.trace_id,
                        source_version=self.recorder_version,
                        source_digest=canonical_hash(companion.model_dump(mode="json")),
                        visibility=VisibilityClass.EVALUATOR_PRIVATE,
                    ),
                ),
            }
        )
        trajectory = trajectory_v2_from_operational_runtime(self.runtime, context=context)
        trajectory = attach_operational_replay_evidence(trajectory, evidence)
        return RecordedExperience(
            machine_experience_from_trajectory(trajectory),
            companion.model_copy(deep=True),
            self.capability.model_copy(deep=True),
        )


def admit_experience(
    source: RecordedExperience, *, registry: AuthorizedVerifierRegistry
) -> AdmittedExperience:
    """Reverify exact canonical input; never trust an earlier caller-authored PASS."""
    experience = MachineExperience.model_validate(source.experience.model_dump(mode="python"))
    trajectory = experience.trajectory
    trace = RolloutTrace.model_validate(source.companion.model_dump(mode="python"))
    profile_id = profile_id_from_trace(trace)
    version_recorder = recorder_version(profile_id)
    case, capability = profile_fixture(profile_id)
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
        or companions[0].source_version != version_recorder
        or companions[0].source_digest != canonical_hash(trace.model_dump(mode="json"))
    ):
        raise ValueError("COMPANION_BINDING_MISMATCH")
    raw = trajectory.private_metadata.get(REPLAY_EVIDENCE_PRIVATE_KEY)
    if raw is None:
        raise ValueError("REPLAY_REQUIRED")
    evidence = OperationalReplayEvidence.model_validate(raw)
    validate_profile_action_events(profile_id, trace, evidence.action_events)
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
        "harness_version": version_recorder,
        "runtime_version": runtime_source_digest(),
        "metadata": recorder_metadata(
            profile_id, canonical_hash(expected_episode.model_dump(mode="json"))
        ),
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
    required = (
        "invariant_violations",
        "target_assertions_total",
        "target_assertions_met",
        "missing_required_actions",
        "forbidden_actions_taken",
        "missing_evidence_ids",
        "process_violations",
        *_COMPONENTS,
    )
    if any(key not in breakdown for key in required):
        raise ValueError("EXPLICIT_VERIFIER_EVIDENCE_REQUIRED")
    if not evidence.portable_contract.private.semantic_state.invariants:
        raise ValueError("INVARIANT_EVIDENCE_REQUIRED")
    for field in (
        "invariant_violations",
        "missing_required_actions",
        "forbidden_actions_taken",
        "missing_evidence_ids",
        "process_violations",
    ):
        if breakdown[field] != []:
            raise ValueError("VERIFIER_FAILURE_" + field.upper())
    if (
        breakdown["target_assertions_total"] <= 0
        or breakdown["target_assertions_met"] != breakdown["target_assertions_total"]
        or breakdown["outcome"] != 1.0
    ):
        raise ValueError("VERIFIER_TERMINAL_FAILURE")
    if any(not math.isfinite(breakdown[name]) for name in _COMPONENTS):
        raise ValueError("NONFINITE_VERIFIER_EVIDENCE")
    if (
        record.component_scores != trajectory.original_evaluation.component_scores
        or record.reward != trajectory.original_evaluation.reward
    ):
        raise ValueError("ORIGINAL_EVALUATION_DRIFT")
    assessment = ExpertiseAssessment(
        verifier_score=breakdown["outcome"],
        invariant_pass=True,
        terminal_success=True,
        efficiency_score=breakdown["efficiency"],
        evidence_quality=breakdown["evidence"],
        rationale=["Fresh authorized offline verifier, explicit targets and invariants"],
    )
    verified = VerifiedTrajectory(
        trajectory_id="bridge-verified-"
        + canonical_hash(
            {
                "experience": experience.experience_id,
                "record": record.record_id,
                "transform": TRANSFORM_VERSION,
            }
        ),
        source_trace_id=trace.trace_id,
        task_id=trace.task_id,
        split=trace.split,
        role=TrajectoryRole.EXPERT,
        assessment=assessment,
        training_uses=[TrainingUse.SFT],
        trace=trace,
        annotations={},
    )
    return AdmittedExperience(
        source,
        verified,
        {
            "experience_id": experience.experience_id,
            "verified_trajectory_id": verified.trajectory_id,
            "task_id": trace.task_id,
            "trajectory_id": trajectory.trajectory_id,
            "reverification_id": record.record_id,
            "source_id": expected_episode.episode_id,
            "source_digest": native_provenance[0].source_digest or "",
            "fixture_digest": trace.metadata["source_digest"],
            "companion_digest": canonical_hash(trace.model_dump(mode="json")),
            "contract_id": evidence.portable_contract.contract_id,
            "capability_digest": capability.content_digest,
            "transform": TRANSFORM_VERSION,
        },
    )
