from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

TRAJECTORY_V2_SCHEMA = "veritas.trajectory.v2"
REVERIFICATION_SCHEMA = "veritas.trajectory.reverification.v1"


class VisibilityClass(StrEnum):
    PUBLIC = "public"
    BUYER_SAFE = "buyer_safe"
    INTERNAL = "internal"
    EVALUATOR_PRIVATE = "evaluator_private"
    SEALED = "sealed"


_VISIBILITY_RANK = {
    VisibilityClass.PUBLIC: 0,
    VisibilityClass.BUYER_SAFE: 1,
    VisibilityClass.INTERNAL: 2,
    VisibilityClass.EVALUATOR_PRIVATE: 3,
    VisibilityClass.SEALED: 4,
}


class FailureCategory(StrEnum):
    MODEL_FAILURE = "model_failure"
    HARNESS_FAILURE = "harness_failure"
    TOOL_ACTION_FAILURE = "tool_action_failure"
    ENVIRONMENT_RUNTIME_FAILURE = "environment_runtime_failure"
    VERIFIER_FAILURE = "verifier_failure"
    DATASET_TASK_DEFECT = "dataset_task_defect"
    INFRASTRUCTURE_PROVIDER_FAILURE = "infrastructure_provider_failure"
    BUDGET_TERMINATION_FAILURE = "budget_termination_failure"
    UNKNOWN = "unknown_unattributed"


class StateDigestScope(StrEnum):
    PUBLIC = "public"
    SEMANTIC = "semantic"
    PUBLIC_SEMANTIC = "public_semantic"


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ArtifactIdentity(CanonicalModel):
    artifact_id: str
    contract: str | None = None
    version: str | None = None
    digest: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class WorldIdentity(CanonicalModel):
    environment_id: str | None = None
    environment_version: str | None = None
    world_id: str | None = None
    world_version: str | None = None
    world_bundle: ArtifactIdentity | None = None
    portable_operational_contract: ArtifactIdentity | None = None


class TaskIdentity(CanonicalModel):
    task_id: str
    taskset_version: str | None = None
    split: str | None = None


class ModelIdentity(CanonicalModel):
    provider: str | None = None
    model_id: str | None = None
    snapshot: str | None = None


class AgentIdentity(CanonicalModel):
    agent_id: str | None = None
    version: str | None = None


class HarnessIdentity(CanonicalModel):
    harness_id: str | None = None
    version: str | None = None


class RuntimeIdentity(CanonicalModel):
    runtime_id: str | None = None
    version: str | None = None


class VerifierIdentity(CanonicalModel):
    verifier_id: str | None = None
    version: str | None = None


class ResetIdentity(CanonicalModel):
    seed: int | str | None = None
    reset_id: str | None = None
    reset_index: int | None = Field(default=None, ge=0)


class StateDigest(CanonicalModel):
    digest: str
    algorithm: str = "sha256"
    scope: StateDigestScope = StateDigestScope.PUBLIC_SEMANTIC


class TrajectoryReference(CanonicalModel):
    reference_id: str
    reference_type: str
    digest: str | None = None
    uri: str | None = None
    visibility: VisibilityClass = VisibilityClass.PUBLIC
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)


class TrajectoryEvent(CanonicalModel):
    step: int = Field(ge=0)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    private_payload: dict[str, Any] = Field(default_factory=dict)
    state_before: StateDigest | None = None
    state_after: StateDigest | None = None
    cost: float | None = Field(default=None, ge=0.0)
    duration_s: float | None = Field(default=None, ge=0.0)
    observation_references: tuple[TrajectoryReference, ...] = ()
    evidence_references: tuple[TrajectoryReference, ...] = ()
    visibility: VisibilityClass = VisibilityClass.PUBLIC


class ProviderCallSummary(CanonicalModel):
    call_index: int = Field(ge=0)
    provider_id: str | None = None
    resource_id: str | None = None
    request_id: str | None = None
    model_id: str | None = None
    model_snapshot: str | None = None
    success: bool | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cost: float | None = Field(default=None, ge=0.0)
    duration_s: float | None = Field(default=None, ge=0.0)
    visibility: VisibilityClass = VisibilityClass.PUBLIC
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceCallSummary(CanonicalModel):
    call_index: int = Field(ge=0)
    resource_id: str | None = None
    operation: str
    success: bool | None = None
    cost: float | None = Field(default=None, ge=0.0)
    duration_s: float | None = Field(default=None, ge=0.0)
    observation_references: tuple[TrajectoryReference, ...] = ()
    evidence_references: tuple[TrajectoryReference, ...] = ()
    visibility: VisibilityClass = VisibilityClass.PUBLIC
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)


class UsageTotals(CanonicalModel):
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    provider_cost: float | None = Field(default=None, ge=0.0)
    environment_cost: float | None = Field(default=None, ge=0.0)
    total_cost: float | None = Field(default=None, ge=0.0)
    elapsed_s: float | None = Field(default=None, ge=0.0)


class EvaluationRecord(CanonicalModel):
    verifier: VerifierIdentity
    component_scores: dict[str, float] = Field(default_factory=dict)
    reward: float


class TerminationRecord(CanonicalModel):
    reason: str = "unknown"
    terminated: bool | None = None
    truncated: bool | None = None


class FailureClassification(CanonicalModel):
    category: FailureCategory = FailureCategory.UNKNOWN
    code: str | None = None
    detail: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def preserve_unknown_attribution(self) -> "FailureClassification":
        if self.category == FailureCategory.UNKNOWN and self.confidence not in {None, 0.0}:
            raise ValueError(
                "unknown failure attribution cannot carry positive attribution confidence"
            )
        return self


class ProvenanceRecord(CanonicalModel):
    source_kind: str
    source_id: str | None = None
    source_version: str | None = None
    source_digest: str | None = None
    adapter_id: str | None = None
    adapter_version: str | None = None
    timestamp: datetime | None = None
    visibility: VisibilityClass = VisibilityClass.INTERNAL
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)


class ReverificationRecord(CanonicalModel):
    schema_version: Literal["veritas.trajectory.reverification.v1"] = REVERIFICATION_SCHEMA
    record_id: str = ""
    input_trajectory_id: str
    verifier: VerifierIdentity
    component_scores: dict[str, float] = Field(default_factory=dict)
    reward: float
    timestamp: datetime | None = None
    provenance: tuple[ProvenanceRecord, ...] = ()
    visibility: VisibilityClass = VisibilityClass.INTERNAL
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)

    def identity_payload(self) -> dict[str, Any]:
        return _semantic_value(self, keep_timestamp=True, exclude_fields={"record_id"})

    @model_validator(mode="after")
    def validate_record_id(self) -> "ReverificationRecord":
        expected = f"REVERIFY-{canonical_hash(self.identity_payload())[:24].upper()}"
        if self.record_id and self.record_id != expected:
            raise ValueError("record_id does not match reverification contents")
        object.__setattr__(self, "record_id", expected)
        return self


class TrajectoryV2(CanonicalModel):
    schema_version: Literal["veritas.trajectory.v2"] = TRAJECTORY_V2_SCHEMA
    trajectory_id: str = ""
    world: WorldIdentity
    task: TaskIdentity
    model: ModelIdentity = Field(default_factory=ModelIdentity)
    agent: AgentIdentity = Field(default_factory=AgentIdentity)
    harness: HarnessIdentity = Field(default_factory=HarnessIdentity)
    runtime: RuntimeIdentity = Field(default_factory=RuntimeIdentity)
    verifier: VerifierIdentity = Field(default_factory=VerifierIdentity)
    reset: ResetIdentity = Field(default_factory=ResetIdentity)
    initial_state: StateDigest
    events: tuple[TrajectoryEvent, ...] = ()
    provider_calls: tuple[ProviderCallSummary, ...] = ()
    resource_calls: tuple[ResourceCallSummary, ...] = ()
    observation_references: tuple[TrajectoryReference, ...] = ()
    evidence_references: tuple[TrajectoryReference, ...] = ()
    usage: UsageTotals = Field(default_factory=UsageTotals)
    original_evaluation: EvaluationRecord
    termination: TerminationRecord = Field(default_factory=TerminationRecord)
    final_state: StateDigest | None = None
    failure: FailureClassification = Field(default_factory=FailureClassification)
    capability_tags: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    reverifications: tuple[ReverificationRecord, ...] = ()
    visibility: VisibilityClass = VisibilityClass.PUBLIC
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("capability_tags")
    @classmethod
    def canonicalize_capability_tags(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(sorted(set(value)))

    def identity_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "world": _semantic_value(self.world),
            "task": _semantic_value(self.task),
            "model": _semantic_value(self.model),
            "agent": _semantic_value(self.agent),
            "harness": _semantic_value(self.harness),
            "runtime": _semantic_value(self.runtime),
            "verifier": _semantic_value(self.verifier),
            "reset": _semantic_value(self.reset),
            "initial_state": _semantic_value(self.initial_state),
            "events": [_semantic_value(item) for item in self.events],
            "provider_calls": [_semantic_value(item) for item in self.provider_calls],
            "resource_calls": [_semantic_value(item) for item in self.resource_calls],
            "observation_references": [
                _semantic_value(item) for item in self.observation_references
            ],
            "evidence_references": [
                _semantic_value(item) for item in self.evidence_references
            ],
            "usage": _semantic_value(self.usage),
            "original_evaluation": _semantic_value(self.original_evaluation),
            "termination": _semantic_value(self.termination),
            "final_state": _semantic_value(self.final_state),
            "failure": _semantic_value(self.failure),
            "capability_tags": list(self.capability_tags),
        }

    @model_validator(mode="after")
    def validate_trajectory(self) -> "TrajectoryV2":
        if self.original_evaluation.verifier != self.verifier:
            raise ValueError("original evaluation verifier must match trajectory verifier")
        expected = f"TRAJ-V2-{canonical_hash(self.identity_payload())[:32].upper()}"
        if self.trajectory_id and self.trajectory_id != expected:
            raise ValueError("trajectory_id does not match immutable semantic contents")
        if any(record.input_trajectory_id != expected for record in self.reverifications):
            raise ValueError("reverification record references a different trajectory")
        record_ids = [record.record_id for record in self.reverifications]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("duplicate reverification record ids are not allowed")
        object.__setattr__(self, "trajectory_id", expected)
        return self

    def with_reverification(self, record: ReverificationRecord) -> "TrajectoryV2":
        if record.input_trajectory_id != self.trajectory_id:
            raise ValueError("reverification input trajectory id does not match")
        if any(existing.record_id == record.record_id for existing in self.reverifications):
            raise ValueError("reverification record is already appended")
        payload = self.model_dump(mode="python")
        payload["reverifications"] = (*self.reverifications, record)
        return TrajectoryV2.model_validate(payload)

    def public_payload(self) -> dict[str, Any]:
        payload = _safe_payload(self, VisibilityClass.PUBLIC)
        if payload is _DROP:
            raise ValueError("trajectory is not classified for public serialization")
        return payload

    def buyer_safe_payload(self) -> dict[str, Any]:
        payload = _safe_payload(self, VisibilityClass.BUYER_SAFE)
        if payload is _DROP:
            raise ValueError("trajectory is not classified for buyer-safe serialization")
        return payload


_DROP = object()
_PRIVATE_BUCKETS = frozenset({"private_metadata", "private_payload"})
_NONSEMANTIC_MODEL_FIELDS = frozenset({"visibility", "public_metadata", "private_metadata"})


def _semantic_value(
    value: Any,
    *,
    keep_timestamp: bool = False,
    exclude_fields: frozenset[str] | set[str] = frozenset(),
) -> Any:
    if isinstance(value, BaseModel):
        result: dict[str, Any] = {}
        for name in type(value).model_fields:
            if name in exclude_fields or name in _NONSEMANTIC_MODEL_FIELDS:
                continue
            if name == "timestamp" and not keep_timestamp:
                continue
            result[name] = _semantic_value(
                getattr(value, name),
                keep_timestamp=keep_timestamp,
            )
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple | list):
        return [_semantic_value(item, keep_timestamp=keep_timestamp) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _semantic_value(child, keep_timestamp=keep_timestamp)
            for key, child in value.items()
        }
    return value


def _canonicalize(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonicalize(value.model_dump(mode="json"))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, tuple):
        return [_canonicalize(item) for item in value]
    if isinstance(value, list):
        return [_canonicalize(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonicalize(child) for key, child in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _canonicalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _safe_payload(value: Any, maximum: VisibilityClass, *, root: bool = False) -> Any:
    if isinstance(value, BaseModel):
        fields = type(value).model_fields
        visibility = getattr(value, "visibility", None)
        if not root and isinstance(visibility, VisibilityClass):
            if _VISIBILITY_RANK[visibility] > _VISIBILITY_RANK[maximum]:
                return _DROP
        result: dict[str, Any] = {}
        for name in fields:
            if name in _PRIVATE_BUCKETS:
                continue
            child = _safe_payload(getattr(value, name), maximum)
            if child is not _DROP:
                result[name] = child
        return result
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
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
            if str(key) in _PRIVATE_BUCKETS:
                continue
            child = _safe_payload(child_value, maximum)
            if child is not _DROP:
                result[str(key)] = child
        return result
    return value
