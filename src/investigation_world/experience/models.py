from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from investigation_world.trajectory import (
    FailureCategory,
    TrajectoryV2,
    VisibilityClass,
    canonical_hash,
)

MACHINE_EXPERIENCE_SCHEMA = "veritas.machine-experience.v1"
EXPERIENCE_SEQUENCE_SCHEMA = "veritas.experience-sequence.v1"


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ReadinessStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ExperienceMaturity(StrEnum):
    E0_TRACEABLE = "E0_TRACEABLE"
    E1_REVERIFIABLE = "E1_REVERIFIABLE"
    E2_DIAGNOSTIC = "E2_DIAGNOSTIC"
    E3_COUNTERFACTUAL = "E3_COUNTERFACTUAL"
    E4_CURRICULUM_READY = "E4_CURRICULUM_READY"
    E5_PROCEDURE_READY = "E5_PROCEDURE_READY"
    E6_ABSTRACTION_READY = "E6_ABSTRACTION_READY"
    E7_CONTINUAL_LEARNING_READY = "E7_CONTINUAL_LEARNING_READY"


class FailureMechanism(StrEnum):
    KNOWLEDGE = "knowledge"
    OBSERVATION = "observation"
    RETRIEVAL = "retrieval"
    EVIDENCE_WEIGHTING = "evidence_weighting"
    IDENTITY_RESOLUTION = "identity_resolution"
    PLANNING = "planning"
    TOOL_SELECTION = "tool_selection"
    TOOL_EXECUTION = "tool_execution"
    PERMISSION_AUTHORITY = "permission_authority"
    STATE_TRACKING = "state_tracking"
    TEMPORAL_REASONING = "temporal_reasoning"
    PROCESS = "process"
    RECOVERY = "recovery"
    VERIFICATION = "verification"
    RESOURCE_BUDGET = "resource_budget"
    PREMATURE_TERMINATION = "premature_termination"
    OVER_ACTION = "over_action"
    UNDER_ACTION = "under_action"
    COORDINATION = "coordination"
    UNKNOWN = "unknown"


_VISIBILITY_RANK = {
    VisibilityClass.PUBLIC: 0,
    VisibilityClass.BUYER_SAFE: 1,
    VisibilityClass.INTERNAL: 2,
    VisibilityClass.EVALUATOR_PRIVATE: 3,
    VisibilityClass.SEALED: 4,
}


class ExperienceReference(CanonicalModel):
    reference_id: str
    reference_type: str
    digest: str | None = None
    uri: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)


class ReadinessAssessment(CanonicalModel):
    status: ReadinessStatus = ReadinessStatus.UNKNOWN
    evidence_references: tuple[ExperienceReference, ...] = ()
    rationale: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC

    @model_validator(mode="after")
    def validate_evidence(self) -> "ReadinessAssessment":
        if self.status is ReadinessStatus.PASS and not self.evidence_references:
            raise ValueError("PASS readiness requires at least one evidence reference")
        if self.status is ReadinessStatus.PASS:
            hidden = [
                item.reference_id
                for item in self.evidence_references
                if _VISIBILITY_RANK[item.visibility] > _VISIBILITY_RANK[self.visibility]
            ]
            if hidden:
                raise ValueError(
                    "PASS readiness evidence cannot be more private than the assessment: "
                    f"{sorted(hidden)}"
                )
        return self


class ExperienceReadiness(CanonicalModel):
    reverification_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    failure_analysis_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    counterfactual_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    causal_analysis_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    procedure_induction_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    abstraction_induction_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    curriculum_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    training_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)
    continual_learning_ready: ReadinessAssessment = Field(default_factory=ReadinessAssessment)


class ExperienceInitialConditions(CanonicalModel):
    public_state_reference: ExperienceReference | None = None
    private_evaluator_reference: ExperienceReference | None = None
    role: str | None = None
    objectives: tuple[str, ...] = ()
    constraints: dict[str, Any] = Field(default_factory=dict)
    budgets: dict[str, float | int] = Field(default_factory=dict)

    @model_validator(mode="after")
    def protect_private_evaluator_reference(self) -> "ExperienceInitialConditions":
        if self.private_evaluator_reference is None:
            return self
        if self.private_evaluator_reference.visibility not in {
            VisibilityClass.EVALUATOR_PRIVATE,
            VisibilityClass.SEALED,
        }:
            raise ValueError(
                "private_evaluator_reference must be evaluator-private or sealed"
            )
        return self


class HypothesisState(CanonicalModel):
    hypothesis_id: str
    statement: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_for: tuple[str, ...] = ()
    evidence_against: tuple[str, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    decision_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class EpistemicSnapshot(CanonicalModel):
    snapshot_id: str
    step: int = Field(ge=0)
    hypotheses: tuple[HypothesisState, ...] = ()
    unresolved_questions: tuple[str, ...] = ()
    contradictions: tuple[str, ...] = ()
    missing_information: tuple[str, ...] = ()
    visibility: VisibilityClass = VisibilityClass.PUBLIC

    @model_validator(mode="after")
    def validate_hypothesis_ids(self) -> "EpistemicSnapshot":
        ids = [item.hypothesis_id for item in self.hypotheses]
        if len(ids) != len(set(ids)):
            raise ValueError("hypothesis ids must be unique within an epistemic snapshot")
        return self


class BeliefRevision(CanonicalModel):
    revision_id: str
    step: int = Field(ge=0)
    hypothesis_id: str
    prior_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    revised_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_reference_ids: tuple[str, ...] = ()
    revision_type: Literal[
        "new_hypothesis",
        "evidence_update",
        "contradiction_update",
        "falsification",
        "recovery",
        "other",
    ] = "evidence_update"
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class ExperienceSpan(CanonicalModel):
    span_id: str
    span_type: str
    start_step: int = Field(ge=0)
    end_step: int = Field(ge=0)
    parent_span_id: str | None = None
    capability_tags: tuple[str, ...] = ()
    reference_ids: tuple[str, ...] = ()
    visibility: VisibilityClass = VisibilityClass.PUBLIC

    @field_validator("capability_tags")
    @classmethod
    def canonicalize_capability_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_range(self) -> "ExperienceSpan":
        if self.end_step < self.start_step:
            raise ValueError("experience span end_step cannot precede start_step")
        return self


class StructuralRecord(CanonicalModel):
    record_id: str
    step: int = Field(ge=0)
    record_type: Literal[
        "entity",
        "relation",
        "causal_candidate",
        "subgoal",
        "plan",
        "procedure_candidate",
        "abstraction_candidate",
        "other",
    ]
    subject_references: tuple[str, ...] = ()
    attributes: dict[str, Any] = Field(default_factory=dict)
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class ExperienceDiagnostics(CanonicalModel):
    failure_mechanisms: tuple[FailureMechanism, ...] = ()
    first_divergence_reference: ExperienceReference | None = None
    recovery_point_references: tuple[ExperienceReference, ...] = ()
    successful_recovery_references: tuple[ExperienceReference, ...] = ()
    capability_gap_references: tuple[ExperienceReference, ...] = ()
    visibility: VisibilityClass = VisibilityClass.INTERNAL

    @field_validator("failure_mechanisms")
    @classmethod
    def canonicalize_failure_mechanisms(
        cls,
        value: tuple[FailureMechanism, ...],
    ) -> tuple[FailureMechanism, ...]:
        return tuple(sorted(set(value), key=str))


_REQUIRED_READINESS_BY_MATURITY: dict[ExperienceMaturity, tuple[str, ...]] = {
    ExperienceMaturity.E0_TRACEABLE: (),
    ExperienceMaturity.E1_REVERIFIABLE: ("reverification_ready",),
    ExperienceMaturity.E2_DIAGNOSTIC: (
        "reverification_ready",
        "failure_analysis_ready",
    ),
    ExperienceMaturity.E3_COUNTERFACTUAL: (
        "reverification_ready",
        "failure_analysis_ready",
        "counterfactual_ready",
    ),
    ExperienceMaturity.E4_CURRICULUM_READY: (
        "reverification_ready",
        "failure_analysis_ready",
        "counterfactual_ready",
        "curriculum_ready",
    ),
    ExperienceMaturity.E5_PROCEDURE_READY: (
        "reverification_ready",
        "failure_analysis_ready",
        "counterfactual_ready",
        "curriculum_ready",
        "procedure_induction_ready",
    ),
    ExperienceMaturity.E6_ABSTRACTION_READY: (
        "reverification_ready",
        "failure_analysis_ready",
        "counterfactual_ready",
        "curriculum_ready",
        "procedure_induction_ready",
        "abstraction_induction_ready",
    ),
    ExperienceMaturity.E7_CONTINUAL_LEARNING_READY: (
        "reverification_ready",
        "failure_analysis_ready",
        "counterfactual_ready",
        "curriculum_ready",
        "procedure_induction_ready",
        "abstraction_induction_ready",
        "training_ready",
        "continual_learning_ready",
    ),
}


class MachineExperience(CanonicalModel):
    schema_version: Literal["veritas.machine-experience.v1"] = MACHINE_EXPERIENCE_SCHEMA
    experience_id: str = ""
    trajectory: TrajectoryV2
    maturity: ExperienceMaturity = ExperienceMaturity.E0_TRACEABLE
    readiness: ExperienceReadiness = Field(default_factory=ExperienceReadiness)
    initial_conditions: ExperienceInitialConditions = Field(
        default_factory=ExperienceInitialConditions
    )
    epistemic_snapshots: tuple[EpistemicSnapshot, ...] = ()
    belief_revisions: tuple[BeliefRevision, ...] = ()
    spans: tuple[ExperienceSpan, ...] = ()
    structural_records: tuple[StructuralRecord, ...] = ()
    diagnostics: ExperienceDiagnostics = Field(default_factory=ExperienceDiagnostics)
    derivation_references: tuple[ExperienceReference, ...] = ()
    visibility: VisibilityClass = VisibilityClass.PUBLIC
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_experience(self) -> "MachineExperience":
        required = _REQUIRED_READINESS_BY_MATURITY[self.maturity]
        missing = [
            name
            for name in required
            if getattr(self.readiness, name).status is not ReadinessStatus.PASS
        ]
        if missing:
            raise ValueError(
                f"experience maturity {self.maturity.value} requires PASS readiness: "
                f"{sorted(missing)}"
            )

        max_step = max((event.step for event in self.trajectory.events), default=0)
        self._validate_step_boundaries(max_step)
        self._validate_spans(max_step)
        self._validate_unique_annotation_ids()

        expected = f"EXP-{canonical_hash({'schema_version': self.schema_version, 'trajectory_id': self.trajectory.trajectory_id})[:32].upper()}"
        if self.experience_id and self.experience_id != expected:
            raise ValueError("experience_id does not match trajectory identity")
        object.__setattr__(self, "experience_id", expected)
        return self

    def _validate_step_boundaries(self, max_step: int) -> None:
        for snapshot in self.epistemic_snapshots:
            if snapshot.step > max_step:
                raise ValueError("epistemic snapshot step exceeds trajectory event range")
        for revision in self.belief_revisions:
            if revision.step > max_step:
                raise ValueError("belief revision step exceeds trajectory event range")
        for record in self.structural_records:
            if record.step > max_step:
                raise ValueError("structural record step exceeds trajectory event range")

    def _validate_spans(self, max_step: int) -> None:
        by_id = {span.span_id: span for span in self.spans}
        if len(by_id) != len(self.spans):
            raise ValueError("experience span ids must be unique")
        for span in self.spans:
            if span.end_step > max_step:
                raise ValueError("experience span exceeds trajectory event range")
            if span.parent_span_id is None:
                continue
            parent = by_id.get(span.parent_span_id)
            if parent is None:
                raise ValueError(f"unknown parent span: {span.parent_span_id}")
            if not (
                parent.start_step <= span.start_step
                and span.end_step <= parent.end_step
            ):
                raise ValueError("child experience span must be contained by its parent")

        for span in self.spans:
            seen: set[str] = set()
            current = span
            while current.parent_span_id is not None:
                if current.span_id in seen:
                    raise ValueError("experience span parent cycle detected")
                seen.add(current.span_id)
                current = by_id[current.parent_span_id]

    def _validate_unique_annotation_ids(self) -> None:
        groups = {
            "epistemic snapshot": [item.snapshot_id for item in self.epistemic_snapshots],
            "belief revision": [item.revision_id for item in self.belief_revisions],
            "structural record": [item.record_id for item in self.structural_records],
        }
        for label, ids in groups.items():
            if len(ids) != len(set(ids)):
                raise ValueError(f"{label} ids must be unique")

    def public_payload(self) -> dict[str, Any]:
        payload = _safe_payload(self, VisibilityClass.PUBLIC, root=True)
        if payload is _DROP:
            raise ValueError("experience is not classified for public serialization")
        return payload

    def buyer_safe_payload(self) -> dict[str, Any]:
        payload = _safe_payload(self, VisibilityClass.BUYER_SAFE, root=True)
        if payload is _DROP:
            raise ValueError("experience is not classified for buyer-safe serialization")
        return payload


class ExperienceSequence(CanonicalModel):
    schema_version: Literal["veritas.experience-sequence.v1"] = EXPERIENCE_SEQUENCE_SCHEMA
    sequence_id: str = ""
    experience_ids: tuple[str, ...] = Field(min_length=1)
    transfer_test_experience_ids: tuple[str, ...] = ()
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_sequence_id(self) -> "ExperienceSequence":
        payload = {
            "schema_version": self.schema_version,
            "experience_ids": list(self.experience_ids),
            "transfer_test_experience_ids": list(self.transfer_test_experience_ids),
        }
        expected = f"EXPSEQ-{canonical_hash(payload)[:32].upper()}"
        if self.sequence_id and self.sequence_id != expected:
            raise ValueError("sequence_id does not match ordered experience contents")
        object.__setattr__(self, "sequence_id", expected)
        return self


class FailureFamily(CanonicalModel):
    family_id: str = ""
    member_experience_ids: tuple[str, ...] = Field(min_length=1)
    shared_precursor_reference: ExperienceReference | None = None
    common_divergence_reference: ExperienceReference | None = None
    affected_capability: str
    severity: float = Field(ge=0.0, le=1.0)
    recoverability: float | None = Field(default=None, ge=0.0, le=1.0)
    candidate_origin: FailureCategory = FailureCategory.UNKNOWN
    mechanisms: tuple[FailureMechanism, ...] = ()
    candidate_procedure_repair_references: tuple[ExperienceReference, ...] = ()
    challenge_generator_references: tuple[ExperienceReference, ...] = ()
    curriculum_priority: float | None = Field(default=None, ge=0.0, le=1.0)
    visibility: VisibilityClass = VisibilityClass.INTERNAL

    @field_validator("member_experience_ids")
    @classmethod
    def canonicalize_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))

    @field_validator("mechanisms")
    @classmethod
    def canonicalize_mechanisms(
        cls,
        value: tuple[FailureMechanism, ...],
    ) -> tuple[FailureMechanism, ...]:
        return tuple(sorted(set(value), key=str))

    @model_validator(mode="after")
    def validate_family_id(self) -> "FailureFamily":
        payload = {
            "members": list(self.member_experience_ids),
            "affected_capability": self.affected_capability,
            "candidate_origin": self.candidate_origin.value,
            "mechanisms": [item.value for item in self.mechanisms],
        }
        expected = f"FAILFAM-{canonical_hash(payload)[:24].upper()}"
        if self.family_id and self.family_id != expected:
            raise ValueError("family_id does not match failure-family contents")
        object.__setattr__(self, "family_id", expected)
        return self


class CapabilityGap(CanonicalModel):
    gap_id: str = ""
    capability: str
    supporting_failure_family_ids: tuple[str, ...] = ()
    frequency: int = Field(ge=0)
    severity: float = Field(ge=0.0, le=1.0)
    environment_ids: tuple[str, ...] = ()
    prerequisite_candidates: tuple[str, ...] = ()
    missing_procedure_candidates: tuple[str, ...] = ()
    likely_abstraction_deficit: str | None = None
    proposed_interventions: tuple[str, ...] = ()
    visibility: VisibilityClass = VisibilityClass.INTERNAL

    @field_validator(
        "supporting_failure_family_ids",
        "environment_ids",
        "prerequisite_candidates",
        "missing_procedure_candidates",
        "proposed_interventions",
    )
    @classmethod
    def canonicalize_string_sets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))

    @model_validator(mode="after")
    def validate_gap_id(self) -> "CapabilityGap":
        payload = {
            "capability": self.capability,
            "supporting_failure_family_ids": list(self.supporting_failure_family_ids),
            "environment_ids": list(self.environment_ids),
        }
        expected = f"CAPGAP-{canonical_hash(payload)[:24].upper()}"
        if self.gap_id and self.gap_id != expected:
            raise ValueError("gap_id does not match capability-gap contents")
        object.__setattr__(self, "gap_id", expected)
        return self


_DROP = object()
_PRIVATE_BUCKETS = frozenset({"private_metadata", "private_payload"})


def _safe_payload(
    value: Any,
    maximum: VisibilityClass,
    *,
    root: bool = False,
) -> Any:
    if isinstance(value, TrajectoryV2):
        if maximum is VisibilityClass.PUBLIC:
            return value.public_payload()
        if maximum is VisibilityClass.BUYER_SAFE:
            return value.buyer_safe_payload()
    if isinstance(value, BaseModel):
        visibility = getattr(value, "visibility", None)
        if not root and isinstance(visibility, VisibilityClass):
            if _VISIBILITY_RANK[visibility] > _VISIBILITY_RANK[maximum]:
                return _DROP
        result: dict[str, Any] = {}
        for name in type(value).model_fields:
            if name in _PRIVATE_BUCKETS:
                continue
            child = _safe_payload(getattr(value, name), maximum)
            if child is not _DROP:
                result[name] = child
        return result
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        result = []
        for item in value:
            child = _safe_payload(item, maximum)
            if child is not _DROP:
                result.append(child)
        return result
    if isinstance(value, dict):
        result = {}
        for key, child_value in value.items():
            if str(key) in _PRIVATE_BUCKETS:
                continue
            child = _safe_payload(child_value, maximum)
            if child is not _DROP:
                result[str(key)] = child
        return result
    return value
