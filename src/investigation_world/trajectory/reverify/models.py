from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import Field, model_validator

from investigation_world.operational.models import ActionEvent, EpisodeSubmission
from investigation_world.portable_contract.models import PortableOperationalContract
from investigation_world.trajectory.models import (
    CanonicalModel,
    ProvenanceRecord,
    ReverificationRecord,
    TrajectoryReference,
    TrajectoryV2,
    VerifierIdentity,
    VisibilityClass,
    canonical_hash,
)

REPLAY_EVIDENCE_SCHEMA: Literal[
    "veritas.trajectory.reverify.operational-evidence.v1"
] = "veritas.trajectory.reverify.operational-evidence.v1"
REPLAY_EVIDENCE_REFERENCE_TYPE = "operational_reverification_evidence"
REPLAY_EVIDENCE_PRIVATE_KEY = "operational_reverification_evidence"
REVERIFICATION_ENGINE_ID = "investigation_world.trajectory.reverify"
REVERIFICATION_ENGINE_VERSION = "1"
BATCH_REVERIFICATION_SCHEMA: Literal[
    "veritas.trajectory.batch-reverification.v1"
] = "veritas.trajectory.batch-reverification.v1"
BATCH_REVERIFICATION_SUMMARY_SCHEMA: Literal[
    "veritas.trajectory.batch-reverification-summary.v1"
] = "veritas.trajectory.batch-reverification-summary.v1"
BATCH_REVERIFICATION_ENGINE_VERSION = "1"


class ReverificationStatus(StrEnum):
    REVERIFIED = "reverified"
    ALREADY_RECORDED = "already_recorded"
    NOT_REVERIFIABLE = "not_reverifiable"
    UNKNOWN = "unknown"
    UNAUTHORIZED = "unauthorized"


class ComparisonStatus(StrEnum):
    COMPARED = "compared"
    NOT_AVAILABLE = "not_available"
    UNKNOWN = "unknown"


class EvaluationSource(StrEnum):
    ORIGINAL = "original"
    REVERIFICATION = "reverification"


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


class EvaluationSnapshot(CanonicalModel):
    snapshot_id: str = ""
    input_trajectory_id: str
    source: EvaluationSource
    source_record_id: str | None = None
    verifier: VerifierIdentity
    component_scores: dict[str, float] = Field(default_factory=dict)
    reward: float

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"snapshot_id"})

    @model_validator(mode="after")
    def bind_snapshot_identity(self) -> "EvaluationSnapshot":
        if self.source is EvaluationSource.ORIGINAL and self.source_record_id is not None:
            raise ValueError("original evaluation cannot name a reverification record")
        if self.source is EvaluationSource.REVERIFICATION and self.source_record_id is None:
            raise ValueError("reverification evaluation must name its source record")
        canonical_components = dict(sorted(self.component_scores.items()))
        object.__setattr__(self, "component_scores", canonical_components)
        expected = f"REVERIFY-SNAPSHOT-{canonical_hash(self.identity_payload())[:24].upper()}"
        if self.snapshot_id and self.snapshot_id != expected:
            raise ValueError("snapshot_id does not match evaluation contents")
        object.__setattr__(self, "snapshot_id", expected)
        return self


class VerifierReasonAttribution(CanonicalModel):
    """Evaluator-private reasons emitted by a verifier for one exact record."""

    source_record_id: str
    invariant_violations: tuple[str, ...] = ()
    missing_required_actions: tuple[str, ...] = ()
    forbidden_actions_taken: tuple[str, ...] = ()
    missing_evidence_ids: tuple[str, ...] = ()
    process_violations: tuple[str, ...] = ()
    evidence_provenance: tuple[ProvenanceRecord, ...] = ()


class ReverificationComparison(CanonicalModel):
    comparison_id: str = ""
    input_trajectory_id: str
    status: ComparisonStatus
    baseline_verifier: VerifierIdentity
    candidate_verifier: VerifierIdentity
    baseline: EvaluationSnapshot | None = None
    candidate: EvaluationSnapshot | None = None
    reward_delta: float | None = None
    component_deltas: dict[str, float] = Field(default_factory=dict)
    unknown_components: tuple[str, ...] = ()
    attribution: VerifierReasonAttribution | None = None
    reason_code: str | None = None

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"comparison_id"})

    @model_validator(mode="after")
    def validate_comparison(self) -> "ReverificationComparison":
        object.__setattr__(self, "component_deltas", dict(sorted(self.component_deltas.items())))
        object.__setattr__(self, "unknown_components", tuple(sorted(set(self.unknown_components))))
        for snapshot in (self.baseline, self.candidate):
            if snapshot is not None and snapshot.input_trajectory_id != self.input_trajectory_id:
                raise ValueError("comparison snapshot references a different trajectory")
        if self.baseline is not None and self.baseline.verifier != self.baseline_verifier:
            raise ValueError("baseline snapshot verifier identity mismatch")
        if self.candidate is not None and self.candidate.verifier != self.candidate_verifier:
            raise ValueError("candidate snapshot verifier identity mismatch")
        if self.status is ComparisonStatus.COMPARED:
            if self.baseline is None or self.candidate is None or self.reward_delta is None:
                raise ValueError("compared evaluation requires both snapshots and reward delta")
            if self.reason_code is not None:
                raise ValueError("successful comparison cannot carry a reason code")
        elif self.reward_delta is not None or self.component_deltas:
            raise ValueError("unavailable comparison cannot carry score deltas")
        if self.attribution is not None:
            if self.candidate is None or (
                self.attribution.source_record_id != self.candidate.source_record_id
            ):
                raise ValueError("attribution must bind to the candidate reverification record")
        expected = f"REVERIFY-COMPARISON-{canonical_hash(self.identity_payload())[:24].upper()}"
        if self.comparison_id and self.comparison_id != expected:
            raise ValueError("comparison_id does not match comparison contents")
        object.__setattr__(self, "comparison_id", expected)
        return self


class BatchReverificationEntry(CanonicalModel):
    entry_id: str = ""
    input_trajectory_id: str
    trajectory_visibility: VisibilityClass
    original_verifier: VerifierIdentity
    requested_verifier: VerifierIdentity
    status: ReverificationStatus
    reason_code: str | None = None
    record_id: str | None = None
    comparison: ReverificationComparison

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"entry_id"})

    @model_validator(mode="after")
    def bind_entry_identity(self) -> "BatchReverificationEntry":
        if self.comparison.input_trajectory_id != self.input_trajectory_id:
            raise ValueError("entry comparison references a different trajectory")
        if self.comparison.candidate_verifier != self.requested_verifier:
            raise ValueError("entry comparison candidate does not match requested verifier")
        scored = self.status in {
            ReverificationStatus.REVERIFIED,
            ReverificationStatus.ALREADY_RECORDED,
        }
        if scored != (self.record_id is not None):
            raise ValueError("record identity must exist exactly when reverification has a score")
        if scored and (
            self.comparison.candidate is None
            or self.comparison.candidate.source_record_id != self.record_id
        ):
            raise ValueError("scored entry must compare the exact appended record")
        expected = f"REVERIFY-ENTRY-{canonical_hash(self.identity_payload())[:24].upper()}"
        if self.entry_id and self.entry_id != expected:
            raise ValueError("entry_id does not match batch entry contents")
        object.__setattr__(self, "entry_id", expected)
        return self


class BuyerSafeReverificationEntry(CanonicalModel):
    input_trajectory_id: str
    status: ReverificationStatus
    reason_code: str | None = None


class BuyerSafeBatchSummary(CanonicalModel):
    schema_version: Literal[
        "veritas.trajectory.batch-reverification-summary.v1"
    ] = BATCH_REVERIFICATION_SUMMARY_SCHEMA
    summary_id: str = ""
    total_trajectories: int = Field(ge=0)
    disclosed_trajectory_count: int = Field(ge=0)
    hidden_trajectory_count: int = Field(ge=0)
    status_counts: dict[str, int] = Field(default_factory=dict)
    entries: tuple[BuyerSafeReverificationEntry, ...] = ()

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"summary_id"})

    @model_validator(mode="after")
    def bind_summary_identity(self) -> "BuyerSafeBatchSummary":
        if (
            self.disclosed_trajectory_count + self.hidden_trajectory_count
            != self.total_trajectories
        ):
            raise ValueError("buyer-safe trajectory counts do not reconcile")
        if self.disclosed_trajectory_count != len(self.entries):
            raise ValueError("disclosed trajectory count does not match entries")
        if any(count < 0 for count in self.status_counts.values()):
            raise ValueError("buyer-safe status counts cannot be negative")
        if sum(self.status_counts.values()) != self.total_trajectories:
            raise ValueError("buyer-safe status counts do not reconcile")
        object.__setattr__(self, "status_counts", dict(sorted(self.status_counts.items())))
        expected = f"REVERIFY-SUMMARY-{canonical_hash(self.identity_payload())[:24].upper()}"
        if self.summary_id and self.summary_id != expected:
            raise ValueError("summary_id does not match buyer-safe contents")
        object.__setattr__(self, "summary_id", expected)
        return self


class BatchReverificationReport(CanonicalModel):
    schema_version: Literal[
        "veritas.trajectory.batch-reverification.v1"
    ] = BATCH_REVERIFICATION_SCHEMA
    batch_id: str = ""
    engine_id: str = REVERIFICATION_ENGINE_ID
    engine_version: str = BATCH_REVERIFICATION_ENGINE_VERSION
    requested_verifier: VerifierIdentity
    baseline_mode: Literal["original", "exact_verifier"] = "original"
    baseline_verifier: VerifierIdentity | None = None
    entries: tuple[BatchReverificationEntry, ...] = ()
    status_counts: dict[str, int] = Field(default_factory=dict)

    def identity_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="python", exclude={"batch_id"})

    @model_validator(mode="after")
    def bind_batch_identity(self) -> "BatchReverificationReport":
        if self.baseline_mode == "exact_verifier" and self.baseline_verifier is None:
            raise ValueError("exact baseline mode requires a verifier identity")
        if self.baseline_mode == "original" and self.baseline_verifier is not None:
            raise ValueError("original baseline mode cannot carry one shared verifier identity")
        entries = tuple(sorted(self.entries, key=lambda item: item.input_trajectory_id))
        if len({item.input_trajectory_id for item in entries}) != len(entries):
            raise ValueError("batch report contains duplicate trajectory identity")
        expected_counts: dict[str, int] = {}
        for entry in entries:
            if entry.requested_verifier != self.requested_verifier:
                raise ValueError("batch entry requested verifier identity mismatch")
            if self.baseline_mode == "original":
                if entry.comparison.baseline_verifier != entry.original_verifier:
                    raise ValueError("batch entry does not use its original evaluation baseline")
            elif entry.comparison.baseline_verifier != self.baseline_verifier:
                raise ValueError("batch entry exact baseline verifier identity mismatch")
            expected_counts[entry.status.value] = expected_counts.get(entry.status.value, 0) + 1
        if self.status_counts and self.status_counts != expected_counts:
            raise ValueError("status_counts do not match batch entries")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "status_counts", dict(sorted(expected_counts.items())))
        expected = f"REVERIFY-BATCH-{canonical_hash(self.identity_payload())[:24].upper()}"
        if self.batch_id and self.batch_id != expected:
            raise ValueError("batch_id does not match report contents")
        object.__setattr__(self, "batch_id", expected)
        return self

    def buyer_safe_summary(self) -> BuyerSafeBatchSummary:
        canonical = type(self).model_validate(self.model_dump(mode="python"))
        visible = {
            VisibilityClass.PUBLIC,
            VisibilityClass.BUYER_SAFE,
        }
        entries = tuple(
            BuyerSafeReverificationEntry(
                input_trajectory_id=item.input_trajectory_id,
                status=item.status,
                reason_code=item.reason_code,
            )
            for item in canonical.entries
            if item.trajectory_visibility in visible
        )
        return BuyerSafeBatchSummary(
            total_trajectories=len(canonical.entries),
            disclosed_trajectory_count=len(entries),
            hidden_trajectory_count=len(canonical.entries) - len(entries),
            status_counts=canonical.status_counts,
            entries=entries,
        )


class BatchReverificationResult(CanonicalModel):
    report: BatchReverificationReport
    trajectories: tuple[TrajectoryV2, ...]

    @model_validator(mode="after")
    def match_report_to_trajectories(self) -> "BatchReverificationResult":
        trajectories = tuple(sorted(self.trajectories, key=lambda item: item.trajectory_id))
        if tuple(item.trajectory_id for item in trajectories) != tuple(
            item.input_trajectory_id for item in self.report.entries
        ):
            raise ValueError("batch result trajectories do not match report entries")
        object.__setattr__(self, "trajectories", trajectories)
        return self
