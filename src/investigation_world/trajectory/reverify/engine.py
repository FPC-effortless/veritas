from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from investigation_world.operational.models import EpisodeSubmission, VerificationBreakdown
from investigation_world.trajectory.models import (
    ProvenanceRecord,
    ReverificationRecord,
    TrajectoryEvent,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    canonical_hash,
)
from investigation_world.trajectory.reverify.models import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    REPLAY_EVIDENCE_REFERENCE_TYPE,
    REVERIFICATION_ENGINE_ID,
    REVERIFICATION_ENGINE_VERSION,
    OperationalReplayEvidence,
    ReverificationOutcome,
    ReverificationStatus,
)
from investigation_world.trajectory.reverify.operational import (
    AuthorizedVerifierRegistry,
    OperationalVerifierBinding,
    evaluator_input_from_evidence,
)

_REWARD_COMPONENTS = (
    "outcome",
    "state",
    "constraints",
    "side_effects",
    "process",
    "efficiency",
    "evidence",
)


@dataclass(frozen=True)
class _EvidenceIssue(Exception):
    status: ReverificationStatus
    code: str


def _issue(status: ReverificationStatus, code: str) -> None:
    raise _EvidenceIssue(status=status, code=code)


def _matching_private_reference(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    matches = [
        reference
        for reference in trajectory.evidence_references
        if reference.reference_type == REPLAY_EVIDENCE_REFERENCE_TYPE
        and reference.reference_id == evidence.evidence_id
    ]
    if not matches:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "REPLAY_EVIDENCE_REFERENCE_MISSING")
    if len(matches) != 1:
        _issue(ReverificationStatus.UNKNOWN, "REPLAY_EVIDENCE_REFERENCE_AMBIGUOUS")
    reference = matches[0]
    if reference.visibility is not VisibilityClass.EVALUATOR_PRIVATE:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "REPLAY_EVIDENCE_NOT_EVALUATOR_PRIVATE")
    if reference.digest != evidence.evidence_digest:
        _issue(ReverificationStatus.UNKNOWN, "REPLAY_EVIDENCE_DIGEST_MISMATCH")


def _validate_contract_binding(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    artifact = trajectory.world.portable_operational_contract
    if artifact is None:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "PORTABLE_CONTRACT_IDENTITY_MISSING")
    if artifact.artifact_id != evidence.portable_contract.contract_id:
        _issue(ReverificationStatus.UNKNOWN, "PORTABLE_CONTRACT_IDENTITY_MISMATCH")
    if trajectory.task.task_id != evidence.portable_contract.public.identity.task_id:
        _issue(ReverificationStatus.UNKNOWN, "TASK_IDENTITY_MISMATCH")
    contract_world_id = evidence.portable_contract.public.identity.world_id
    if trajectory.world.world_id is not None and trajectory.world.world_id != contract_world_id:
        _issue(ReverificationStatus.UNKNOWN, "WORLD_IDENTITY_MISMATCH")
    if not evidence.portable_contract.private.evaluator.deterministic:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "NONDETERMINISTIC_EVALUATOR_CONTRACT")


def _successful_calls(trajectory: TrajectoryV2, method: str) -> list[TrajectoryEvent]:
    return [
        event
        for event in trajectory.events
        if event.payload.get("method") == method and event.payload.get("success") is True
    ]


def _decode_operational_act(event: TrajectoryEvent) -> tuple[str, dict[str, Any]]:
    raw_args = event.payload.get("args", [])
    raw_kwargs = event.payload.get("kwargs", {})
    if not isinstance(raw_args, list) or not isinstance(raw_kwargs, dict):
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "ACTION_CALL_SHAPE_UNAVAILABLE")
    if len(raw_args) > 1:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "ACTION_CALL_SHAPE_UNSUPPORTED")
    if raw_args:
        action_name = raw_args[0]
        parameters = dict(raw_kwargs)
    else:
        action_name = raw_kwargs.get("action_name")
        parameters = {key: value for key, value in raw_kwargs.items() if key != "action_name"}
    if not isinstance(action_name, str):
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "ACTION_NAME_UNAVAILABLE")
    return action_name, parameters


def _validate_action_events(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    trace_actions = _successful_calls(trajectory, "act")
    if len(trace_actions) != len(evidence.action_events):
        _issue(ReverificationStatus.UNKNOWN, "ACTION_EVENT_COUNT_MISMATCH")

    action_specs = {
        action.name: action for action in evidence.portable_contract.public.actions
    }
    for index, (trace_event, action_event) in enumerate(
        zip(trace_actions, evidence.action_events, strict=True),
        start=1,
    ):
        action_name, parameters = _decode_operational_act(trace_event)
        if action_event.sequence != index:
            _issue(ReverificationStatus.UNKNOWN, "ACTION_SEQUENCE_MISMATCH")
        if action_event.action_name != action_name or action_event.parameters != parameters:
            _issue(ReverificationStatus.UNKNOWN, "ACTION_PUBLIC_PROJECTION_MISMATCH")
        spec = action_specs.get(action_event.action_name)
        if spec is None:
            _issue(ReverificationStatus.UNKNOWN, "ACTION_NOT_IN_PORTABLE_CONTRACT")
        if action_event.system != spec.system or action_event.kind.value != spec.kind:
            _issue(ReverificationStatus.UNKNOWN, "ACTION_SCHEMA_MISMATCH")
        if action_event.cost != spec.cost:
            _issue(ReverificationStatus.UNKNOWN, "ACTION_COST_MISMATCH")
        if trace_event.cost is None or float(trace_event.cost) != float(action_event.cost):
            _issue(ReverificationStatus.UNKNOWN, "ACTION_TRACE_COST_MISMATCH")


def _decode_submission(event: TrajectoryEvent) -> EpisodeSubmission:
    raw_args = event.payload.get("args", [])
    raw_kwargs = event.payload.get("kwargs", {})
    candidate: Any = None
    if isinstance(raw_args, list) and len(raw_args) == 1 and isinstance(raw_args[0], dict):
        candidate = raw_args[0]
    elif isinstance(raw_args, list) and not raw_args and isinstance(raw_kwargs, dict):
        nested = raw_kwargs.get("submission")
        if isinstance(nested, dict):
            candidate = nested
    if candidate is None:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "SUBMISSION_PAYLOAD_UNAVAILABLE")
    try:
        return EpisodeSubmission.model_validate(candidate)
    except ValidationError:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "SUBMISSION_PAYLOAD_INVALID")
    raise AssertionError("unreachable")


def _validate_submission(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    submit_events = _successful_calls(trajectory, "submit")
    if len(submit_events) != 1:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "EXACT_SUBMISSION_EVENT_REQUIRED")
    traced_submission = _decode_submission(submit_events[0])
    if traced_submission != evidence.submission:
        _issue(ReverificationStatus.UNKNOWN, "SUBMISSION_EVIDENCE_MISMATCH")


def _validate_state_chain(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    if trajectory.initial_state.digest != evidence.initial_state_digest:
        _issue(ReverificationStatus.UNKNOWN, "INITIAL_STATE_DIGEST_MISMATCH")
    if trajectory.final_state is None:
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "FINAL_STATE_DIGEST_MISSING")
    if trajectory.final_state.digest != evidence.final_state_digest:
        _issue(ReverificationStatus.UNKNOWN, "FINAL_STATE_DIGEST_MISMATCH")

    replayed_state = copy.deepcopy(evidence.initial_state)
    for event in evidence.action_events:
        replayed_state.update(copy.deepcopy(event.state_changes))
    if replayed_state != evidence.final_state:
        _issue(ReverificationStatus.UNKNOWN, "REPLAYED_FINAL_STATE_MISMATCH")


def _validate_budget_binding(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    environment_cost = trajectory.usage.environment_cost
    if environment_cost is not None and float(environment_cost) != float(evidence.cost_spent):
        _issue(ReverificationStatus.UNKNOWN, "ENVIRONMENT_COST_MISMATCH")


def _validate_evidence_against_trajectory(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> None:
    if evidence.input_trajectory_id != trajectory.trajectory_id:
        _issue(ReverificationStatus.UNKNOWN, "REPLAY_EVIDENCE_TRAJECTORY_ID_MISMATCH")
    if evidence.trajectory_events_digest != canonical_hash(trajectory.events):
        _issue(ReverificationStatus.UNKNOWN, "TRAJECTORY_EVENT_SEQUENCE_DIGEST_MISMATCH")
    _matching_private_reference(trajectory, evidence)
    _validate_contract_binding(trajectory, evidence)
    _validate_action_events(trajectory, evidence)
    _validate_submission(trajectory, evidence)
    _validate_state_chain(trajectory, evidence)
    _validate_budget_binding(trajectory, evidence)


def _extract_evidence(trajectory: TrajectoryV2) -> OperationalReplayEvidence:
    raw = trajectory.private_metadata.get(REPLAY_EVIDENCE_PRIVATE_KEY)
    if not isinstance(raw, dict):
        _issue(ReverificationStatus.NOT_REVERIFIABLE, "PRIVATE_REPLAY_EVIDENCE_MISSING")
    try:
        evidence = OperationalReplayEvidence.model_validate(raw)
    except ValidationError:
        _issue(ReverificationStatus.UNKNOWN, "PRIVATE_REPLAY_EVIDENCE_INVALID")
    _validate_evidence_against_trajectory(trajectory, evidence)
    return evidence


def attach_operational_replay_evidence(
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
) -> TrajectoryV2:
    """Attach already identity-referenced private evidence without changing trajectory identity."""
    bound = evidence.for_trajectory(trajectory)
    _validate_evidence_against_trajectory(trajectory, bound)
    private_metadata = copy.deepcopy(trajectory.private_metadata)
    existing = private_metadata.get(REPLAY_EVIDENCE_PRIVATE_KEY)
    payload = bound.model_dump(mode="json")
    if existing is not None and existing != payload:
        raise ValueError("trajectory already carries different operational replay evidence")
    private_metadata[REPLAY_EVIDENCE_PRIVATE_KEY] = payload
    updated = TrajectoryV2.model_validate(
        {
            **trajectory.model_dump(mode="python"),
            "private_metadata": private_metadata,
        }
    )
    if updated.trajectory_id != trajectory.trajectory_id:
        raise AssertionError("private replay evidence must not change trajectory identity")
    return updated


def _record_from_breakdown(
    *,
    trajectory: TrajectoryV2,
    evidence: OperationalReplayEvidence,
    binding: OperationalVerifierBinding,
    breakdown: VerificationBreakdown,
) -> ReverificationRecord:
    component_scores = {
        name: float(getattr(breakdown, name))
        for name in _REWARD_COMPONENTS
    }
    provenance = (
        ProvenanceRecord(
            source_kind="trajectory.original_verifier",
            source_id=trajectory.verifier.verifier_id,
            source_version=trajectory.verifier.version,
            source_digest=trajectory.trajectory_id,
            visibility=VisibilityClass.INTERNAL,
        ),
        ProvenanceRecord(
            source_kind="trajectory.reverification_evidence",
            source_id=evidence.evidence_id,
            source_version=evidence.schema_version,
            source_digest=evidence.evidence_digest,
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        ),
        ProvenanceRecord(
            source_kind="trajectory.authorized_verifier_binding",
            source_id=binding.identity.verifier_id,
            source_version=binding.identity.version,
            source_digest=binding.source_git_blob_sha1,
            visibility=VisibilityClass.INTERNAL,
        ),
    )
    return ReverificationRecord(
        input_trajectory_id=trajectory.trajectory_id,
        verifier=binding.identity,
        component_scores=dict(sorted(component_scores.items())),
        reward=float(breakdown.overall_reward),
        provenance=provenance,
        visibility=VisibilityClass.INTERNAL,
        public_metadata={
            "engine_id": REVERIFICATION_ENGINE_ID,
            "engine_version": REVERIFICATION_ENGINE_VERSION,
        },
        private_metadata={
            "verification_breakdown": breakdown.model_dump(mode="json"),
        },
    )


def _result(
    *,
    trajectory: TrajectoryV2,
    requested_verifier: VerifierIdentity,
    status: ReverificationStatus,
    reason_code: str | None = None,
    detail: str | None = None,
    record: ReverificationRecord | None = None,
    updated: TrajectoryV2 | None = None,
) -> ReverificationOutcome:
    return ReverificationOutcome(
        status=status,
        input_trajectory_id=trajectory.trajectory_id,
        original_verifier=trajectory.verifier,
        requested_verifier=requested_verifier,
        reason_code=reason_code,
        detail=detail,
        record=record,
        trajectory_with_reverification=updated,
    )


def reverify_trajectory(
    trajectory: TrajectoryV2,
    *,
    verifier: VerifierIdentity,
    registry: AuthorizedVerifierRegistry,
) -> ReverificationOutcome:
    """Re-score a canonical trajectory using only authorized offline evaluator material."""
    try:
        canonical = TrajectoryV2.model_validate(trajectory.model_dump(mode="python"))
    except (ValidationError, TypeError, ValueError):
        return _result(
            trajectory=trajectory,
            requested_verifier=verifier,
            status=ReverificationStatus.UNKNOWN,
            reason_code="TRAJECTORY_IDENTITY_INVALID",
        )

    if verifier.verifier_id is None or verifier.version is None:
        return _result(
            trajectory=canonical,
            requested_verifier=verifier,
            status=ReverificationStatus.UNAUTHORIZED,
            reason_code="VERIFIER_IDENTITY_INCOMPLETE",
        )
    binding = registry.resolve(verifier)
    if binding is None:
        return _result(
            trajectory=canonical,
            requested_verifier=verifier,
            status=ReverificationStatus.UNAUTHORIZED,
            reason_code="EXACT_VERIFIER_BINDING_NOT_AUTHORIZED",
        )

    try:
        evidence = _extract_evidence(canonical)
    except _EvidenceIssue as issue:
        return _result(
            trajectory=canonical,
            requested_verifier=verifier,
            status=issue.status,
            reason_code=issue.code,
        )

    try:
        evaluator_input = evaluator_input_from_evidence(evidence)
    except (ValidationError, TypeError, ValueError):
        return _result(
            trajectory=canonical,
            requested_verifier=verifier,
            status=ReverificationStatus.NOT_REVERIFIABLE,
            reason_code="EVALUATOR_INPUT_RECONSTRUCTION_FAILED",
        )

    try:
        breakdown = binding.verify(evaluator_input)
    except Exception as exc:
        return _result(
            trajectory=canonical,
            requested_verifier=verifier,
            status=ReverificationStatus.UNKNOWN,
            reason_code="AUTHORIZED_VERIFIER_FAILED",
            detail=f"authorized verifier raised {type(exc).__name__}",
        )

    record = _record_from_breakdown(
        trajectory=canonical,
        evidence=evidence,
        binding=binding,
        breakdown=breakdown,
    )
    existing = next(
        (item for item in canonical.reverifications if item.record_id == record.record_id),
        None,
    )
    if existing is not None:
        return _result(
            trajectory=canonical,
            requested_verifier=verifier,
            status=ReverificationStatus.ALREADY_RECORDED,
            reason_code="REVERIFICATION_RECORD_ALREADY_PRESENT",
            record=existing,
            updated=canonical,
        )

    updated = canonical.with_reverification(record)
    return _result(
        trajectory=canonical,
        requested_verifier=verifier,
        status=ReverificationStatus.REVERIFIED,
        record=record,
        updated=updated,
    )
