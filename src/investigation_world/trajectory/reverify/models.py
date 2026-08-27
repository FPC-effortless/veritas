from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from investigation_world.operational.models import ActionEvent, EpisodeSubmission
from investigation_world.portable_contract.models import PortableOperationalContract
from investigation_world.trajectory.models import (
    CanonicalModel,
    ReverificationRecord,
    TrajectoryReference,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    canonical_hash,
)

REPLAY_EVIDENCE_SCHEMA = "veritas.trajectory.reverify.operational-evidence.v1"
REPLAY_EVIDENCE_REFERENCE_TYPE = "operational_reverification_evidence"
REPLAY_EVIDENCE_PRIVATE_KEY = "operational_reverification_evidence"
REVERIFICATION_ENGINE_ID = "investigation_world.trajectory.reverify"
REVERIFICATION_ENGINE_VERSION = "1"


class ReverificationStatus(StrEnum):
    REVERIFIED = "reverified"
    ALREADY_RECORDED = "already_recorded"
    NOT_REVERIFIABLE = "not_reverifiable"
    UNKNOWN = "unknown"
    UNAUTHORIZED = "unauthorized"


class OperationalReplayEvidence(CanonicalModel):
    """Evaluator-private evidence sufficient to reconstruct operational verifier input.

    The evidence digest deliberately excludes ``input_trajectory_id``. Producers can therefore
    create the digest-bearing private reference before the trajectory receives its canonical ID,
    then bind the private payload to that final ID without changing the evidence digest.
    """

    schema_version: Literal[
        "veritas.trajectory.reverify.operational-evidence.v1"
    ] = REPLAY_EVIDENCE_SCHEMA
    input_trajectory_id: str | None = None
    evidence_id: str = ""
    evidence_digest: str = ""
    portable_contract: PortableOperationalContract
    trajectory_events_digest: str
    initial_state: dict[str, Any]
    initial_state_digest: str
    final_state: dict[str, Any]
    final_state_digest: str
    action_events: tuple[ActionEvent, ...] = ()
    submission: EpisodeSubmission
    tool_calls: int = Field(ge=0)
    cost_spent: int = Field(ge=0)

    def digest_payload(self) -> dict[str, Any]:
        return self.model_dump(
            mode="python",
            exclude={"input_trajectory_id", "evidence_id", "evidence_digest"},
        )

    @model_validator(mode="after")
    def bind_evidence_identity(self) -> "OperationalReplayEvidence":
        expected_digest = canonical_hash(self.digest_payload())
        expected_id = f"REPLAY-EVIDENCE-{expected_digest[:24].upper()}"
        if self.evidence_digest and self.evidence_digest != expected_digest:
            raise ValueError("evidence_digest does not match replay evidence contents")
        if self.evidence_id and self.evidence_id != expected_id:
            raise ValueError("evidence_id does not match replay evidence contents")
        object.__setattr__(self, "evidence_digest", expected_digest)
        object.__setattr__(self, "evidence_id", expected_id)
        return self

    def reference(self) -> TrajectoryReference:
        """Return the evaluator-private, identity-bearing reference for this evidence payload."""
        return TrajectoryReference(
            reference_id=self.evidence_id,
            reference_type=REPLAY_EVIDENCE_REFERENCE_TYPE,
            digest=self.evidence_digest,
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        )

    def for_trajectory(self, trajectory: TrajectoryV2) -> "OperationalReplayEvidence":
        payload = self.model_dump(mode="python")
        payload["input_trajectory_id"] = trajectory.trajectory_id
        return OperationalReplayEvidence.model_validate(payload)


class ReverificationOutcome(CanonicalModel):
    status: ReverificationStatus
    input_trajectory_id: str
    original_verifier: VerifierIdentity
    requested_verifier: VerifierIdentity
    reason_code: str | None = None
    detail: str | None = None
    record: ReverificationRecord | None = None
    trajectory_with_reverification: TrajectoryV2 | None = None
