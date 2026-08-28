from __future__ import annotations

from enum import Enum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.experience.models import ExperienceSpan, StructuralRecord
from investigation_world.trajectory import VisibilityClass, canonical_hash

SEMANTIC_ANNOTATION_SCHEMA: Literal["veritas.semantic-experience-annotation.v1"] = (
    "veritas.semantic-experience-annotation.v1"
)


class AnnotationModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SemanticDerivationStatus(StrEnum):
    DERIVED = "derived"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class SemanticInvocationKind(StrEnum):
    ACTION = "action"
    OPERATION = "operation"
    UNKNOWN = "unknown"


class ResourceChargeAnnotation(AnnotationModel):
    resource: str
    unit: str
    amount: int = Field(ge=0)


class InvocationAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    kind: SemanticInvocationKind = SemanticInvocationKind.UNKNOWN
    name: str | None = None
    system: str | None = None
    action_kind: str | None = None
    interaction_mode: str | None = None
    source_fields: tuple[str, ...] = ()
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC

    @model_validator(mode="after")
    def validate_derived_identity(self) -> "InvocationAnnotation":
        if self.status is SemanticDerivationStatus.DERIVED:
            if self.kind is SemanticInvocationKind.UNKNOWN or not self.name:
                raise ValueError("derived invocation requires a known kind and name")
        return self


class StateTransitionAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    state_before_digest: str | None = None
    state_after_digest: str | None = None
    changed: bool | None = None
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class ProcessRequirementAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    required: bool | None = None
    forbidden: bool | None = None
    required_order_positions: tuple[int, ...] = ()
    required_count: int | None = Field(default=None, ge=1)
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.EVALUATOR_PRIVATE


class InvariantEffectAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    affected_invariant_ids: tuple[str, ...] = ()
    candidate_transition_indices: tuple[int, ...] = ()
    effect_verified: bool = False
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.EVALUATOR_PRIVATE


class EvidenceFlowAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    created_ids: tuple[str, ...] = ()
    consumed_ids: tuple[str, ...] = ()
    referenced_ids: tuple[str, ...] = ()
    direction_complete: bool = False
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class AuthorityAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    system: str | None = None
    statically_permitted: bool | None = None
    dynamic_permission_known: bool = False
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class BudgetImpactAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    declared_charges: tuple[ResourceChargeAnnotation, ...] = ()
    observed_event_cost: float | None = Field(default=None, ge=0.0)
    remaining_budget_known: bool = False
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class VerifierRelevanceAnnotation(AnnotationModel):
    status: SemanticDerivationStatus
    component_names: tuple[str, ...] = ()
    basis: tuple[str, ...] = ()
    reason: str | None = None
    visibility: VisibilityClass = VisibilityClass.EVALUATOR_PRIVATE


class SemanticEventAnnotation(AnnotationModel):
    annotation_id: str = ""
    event_index: int = Field(ge=0)
    step: int = Field(ge=0)
    event_type: str
    invocation: InvocationAnnotation
    state_transition: StateTransitionAnnotation
    process_requirement: ProcessRequirementAnnotation
    invariant_effect: InvariantEffectAnnotation
    evidence_flow: EvidenceFlowAnnotation
    authority: AuthorityAnnotation
    budget_impact: BudgetImpactAnnotation
    verifier_relevance: VerifierRelevanceAnnotation
    visibility: VisibilityClass = VisibilityClass.PUBLIC

    @model_validator(mode="after")
    def bind_identity(self) -> "SemanticEventAnnotation":
        payload = self.model_dump(mode="json", exclude={"annotation_id"})
        expected = f"SEMANN-{canonical_hash(payload)[:24].upper()}"
        if self.annotation_id and self.annotation_id != expected:
            raise ValueError("annotation_id does not match semantic annotation contents")
        object.__setattr__(self, "annotation_id", expected)
        return self


class SemanticAnnotationBundle(AnnotationModel):
    schema_version: Literal["veritas.semantic-experience-annotation.v1"] = (
        SEMANTIC_ANNOTATION_SCHEMA
    )
    bundle_id: str = ""
    trajectory_id: str
    contract_id: str
    public_contract_id: str
    contract_schema_version: str
    trajectory_verifier_id: str | None = None
    trajectory_verifier_version: str | None = None
    evaluator_semantics_id: str
    event_annotations: tuple[SemanticEventAnnotation, ...] = ()
    spans: tuple[ExperienceSpan, ...] = ()
    structural_records: tuple[StructuralRecord, ...] = ()

    @model_validator(mode="after")
    def validate_and_bind_identity(self) -> "SemanticAnnotationBundle":
        event_indices = [item.event_index for item in self.event_annotations]
        if len(event_indices) != len(set(event_indices)):
            raise ValueError("semantic annotation event indices must be unique")
        span_ids = [item.span_id for item in self.spans]
        if len(span_ids) != len(set(span_ids)):
            raise ValueError("semantic annotation span ids must be unique")
        record_ids = [item.record_id for item in self.structural_records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("semantic annotation structural record ids must be unique")

        payload = self.model_dump(mode="json", exclude={"bundle_id"})
        expected = f"SEMBUNDLE-{canonical_hash(payload)[:24].upper()}"
        if self.bundle_id and self.bundle_id != expected:
            raise ValueError("bundle_id does not match semantic annotation contents")
        object.__setattr__(self, "bundle_id", expected)
        return self

    def public_payload(self) -> dict[str, Any]:
        return self._projection(VisibilityClass.PUBLIC)

    def buyer_safe_payload(self) -> dict[str, Any]:
        return self._projection(VisibilityClass.BUYER_SAFE)

    def _projection(self, maximum: VisibilityClass) -> dict[str, Any]:
        validated = SemanticAnnotationBundle.model_validate(
            self.model_dump(mode="python")
        )
        payload = _safe_payload(validated, maximum, root=True)
        if not isinstance(payload, dict):
            raise ValueError("semantic annotation bundle could not be projected")
        # The full contract identity and evaluator binding commit to private semantics.
        # Public/buyer-safe consumers receive the independently content-bound public ID instead.
        payload.pop("contract_id", None)
        payload.pop("evaluator_semantics_id", None)
        return payload


_VISIBILITY_RANK = {
    VisibilityClass.PUBLIC: 0,
    VisibilityClass.BUYER_SAFE: 1,
    VisibilityClass.INTERNAL: 2,
    VisibilityClass.EVALUATOR_PRIVATE: 3,
    VisibilityClass.SEALED: 4,
}
_DROP = object()


def _safe_payload(value: Any, maximum: VisibilityClass, *, root: bool = False) -> Any:
    if isinstance(value, BaseModel):
        visibility = getattr(value, "visibility", None)
        if not root and isinstance(visibility, VisibilityClass):
            if _VISIBILITY_RANK[visibility] > _VISIBILITY_RANK[maximum]:
                return _DROP
        result: dict[str, Any] = {}
        for name in type(value).model_fields:
            child = _safe_payload(getattr(value, name), maximum)
            if child is not _DROP:
                result[name] = child
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        output = []
        for item in value:
            child = _safe_payload(item, maximum)
            if child is not _DROP:
                output.append(child)
        return output
    if isinstance(value, dict):
        result = {}
        for key, child_value in value.items():
            child = _safe_payload(child_value, maximum)
            if child is not _DROP:
                result[str(key)] = child
        return result
    return value
