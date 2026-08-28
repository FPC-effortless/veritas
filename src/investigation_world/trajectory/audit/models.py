from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

TRAJECTORY_METADATA_AUDIT_SCHEMA = "veritas.trajectory-metadata-audit.v1"
_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")


class MetadataRequirement(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"


class MetadataCoverage(StrEnum):
    PRESENT = "PRESENT"
    CONDITIONAL = "CONDITIONAL"
    ABSENT = "ABSENT"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"


class ProducerKind(StrEnum):
    TRAJECTORY_PRODUCER = "TRAJECTORY_PRODUCER"
    SEMANTIC_RUNTIME = "SEMANTIC_RUNTIME"
    EXTERNAL_ADAPTER = "EXTERNAL_ADAPTER"


class ProducerCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    CONDITIONAL = "CONDITIONAL"
    INCOMPLETE = "INCOMPLETE"


class AuditStatus(StrEnum):
    COMPLETE = "COMPLETE"
    GAPS_FOUND = "GAPS_FOUND"


class TrajectoryMetadataField(StrEnum):
    WORLD_ENVIRONMENT_IDENTITY = "world_environment_identity"
    TASK_IDENTITY = "task_identity"
    MODEL_IDENTITY = "model_identity"
    AGENT_IDENTITY = "agent_identity"
    HARNESS_IDENTITY = "harness_identity"
    HARNESS_CONFIG_IDENTITY = "harness_config_identity"
    RUNTIME_IDENTITY = "runtime_identity"
    VERIFIER_IDENTITY = "verifier_identity"
    SEED_RESET_IDENTITY = "seed_reset_identity"
    OBSERVATIONS = "observations"
    ACTION_TOOL_RESOURCE_CALLS = "action_tool_resource_calls"
    PROVIDER_CALLS = "provider_calls"
    PROVIDER_REQUEST_ID = "provider_request_id"
    ARTIFACT_EVIDENCE_REFERENCES = "artifact_evidence_references"
    STATE_DIGESTS_TRANSITIONS = "state_digests_transitions"
    REWARD_COMPONENTS = "reward_components"
    TOKEN_USAGE = "token_usage"
    COST_USAGE = "cost_usage"
    TIME_USAGE = "time_usage"
    TERMINATION_TRUNCATION = "termination_truncation"
    FAILURE_ORIGIN_CLASSIFICATION = "failure_origin_classification"
    PUBLIC_PRIVATE_VISIBILITY = "public_private_visibility"
    PROVENANCE_SOURCE_REFERENCES = "provenance_source_references"


class _AuditModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def _canonical_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _canonical_value(value.model_dump(mode="json"))
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(child) for key, child in value.items()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical value type: {type(value).__name__}")


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _canonical_value(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _normalize_strings(values: tuple[str, ...], *, field_name: str) -> tuple[str, ...]:
    normalized = tuple(sorted({value.strip() for value in values if value.strip()}))
    if len(normalized) != len(values):
        raise ValueError(f"{field_name} must contain unique non-empty values")
    return normalized


class MetadataFieldCoverage(_AuditModel):
    field: TrajectoryMetadataField
    requirement: MetadataRequirement
    coverage: MetadataCoverage
    evidence_paths: tuple[str, ...]
    detail: str = Field(min_length=1)
    condition: str | None = None

    @model_validator(mode="after")
    def validate_coverage(self) -> "MetadataFieldCoverage":
        paths = _normalize_strings(self.evidence_paths, field_name="evidence_paths")
        object.__setattr__(self, "evidence_paths", paths)
        if not paths:
            raise ValueError("metadata coverage requires at least one evidence path")
        if self.coverage == MetadataCoverage.CONDITIONAL:
            if self.condition is None or not self.condition.strip():
                raise ValueError("CONDITIONAL metadata coverage must state its condition")
            object.__setattr__(self, "condition", self.condition.strip())
        elif self.condition is not None:
            raise ValueError("condition is only valid for CONDITIONAL metadata coverage")
        return self


class ProducerMetadataCoverage(_AuditModel):
    producer_id: str = Field(min_length=1)
    producer_kind: ProducerKind
    emits_trajectory_v2: bool
    fields: tuple[MetadataFieldCoverage, ...]
    completeness: ProducerCompleteness | None = None
    required_present_fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    required_gaps: tuple[TrajectoryMetadataField, ...] = ()
    notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_producer(self) -> "ProducerMetadataCoverage":
        fields = tuple(sorted(self.fields, key=lambda item: item.field.value))
        field_keys = [item.field for item in fields]
        if len(field_keys) != len(set(field_keys)):
            raise ValueError("producer metadata fields must be unique")
        missing = set(TrajectoryMetadataField) - set(field_keys)
        if missing:
            names = ", ".join(sorted(item.value for item in missing))
            raise ValueError(f"producer audit omits metadata fields: {names}")
        notes = _normalize_strings(self.notes, field_name="notes")

        required = [
            item for item in fields if item.requirement == MetadataRequirement.REQUIRED
        ]
        if not required:
            raise ValueError("producer audit must contain required metadata fields")
        present = [item for item in required if item.coverage == MetadataCoverage.PRESENT]
        gaps = tuple(
            sorted(
                (item.field for item in required if item.coverage != MetadataCoverage.PRESENT),
                key=lambda item: item.value,
            )
        )
        has_hard_gap = any(
            item.coverage
            in {
                MetadataCoverage.ABSENT,
                MetadataCoverage.UNSUPPORTED,
                MetadataCoverage.UNKNOWN,
            }
            for item in required
        )
        completeness = (
            ProducerCompleteness.INCOMPLETE
            if has_hard_gap
            else ProducerCompleteness.CONDITIONAL
            if gaps
            else ProducerCompleteness.COMPLETE
        )
        fraction = len(present) / len(required)

        if self.completeness is not None and self.completeness != completeness:
            raise ValueError("producer completeness does not match metadata coverage")
        if (
            self.required_present_fraction is not None
            and self.required_present_fraction != fraction
        ):
            raise ValueError("required_present_fraction does not match metadata coverage")
        if self.required_gaps and self.required_gaps != gaps:
            raise ValueError("required_gaps do not match metadata coverage")

        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "completeness", completeness)
        object.__setattr__(self, "required_present_fraction", fraction)
        object.__setattr__(self, "required_gaps", gaps)
        object.__setattr__(self, "notes", notes)
        return self

    def coverage_for(self, field: TrajectoryMetadataField) -> MetadataFieldCoverage:
        return next(item for item in self.fields if item.field == field)


class InterfaceGapRequest(_AuditModel):
    gap_id: str = Field(min_length=1)
    field: TrajectoryMetadataField
    owner: str = Field(min_length=1)
    requested_change: str = Field(min_length=1)
    evidence_paths: tuple[str, ...]
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_gap(self) -> "InterfaceGapRequest":
        paths = _normalize_strings(self.evidence_paths, field_name="evidence_paths")
        if not paths:
            raise ValueError("interface gap requires evidence paths")
        object.__setattr__(self, "evidence_paths", paths)
        return self


class TrajectoryMetadataAudit(_AuditModel):
    schema_version: str = TRAJECTORY_METADATA_AUDIT_SCHEMA
    audit_id: str = ""
    content_sha256: str = ""
    base_commit_sha: str
    producers: tuple[ProducerMetadataCoverage, ...]
    interface_gaps: tuple[InterfaceGapRequest, ...] = ()
    status: AuditStatus | None = None

    @model_validator(mode="after")
    def validate_audit(self) -> "TrajectoryMetadataAudit":
        if self.schema_version != TRAJECTORY_METADATA_AUDIT_SCHEMA:
            raise ValueError("unsupported trajectory metadata audit schema version")
        if _COMMIT_RE.fullmatch(self.base_commit_sha) is None:
            raise ValueError("base_commit_sha must be a lowercase 40-character commit SHA")
        producers = tuple(sorted(self.producers, key=lambda item: item.producer_id))
        producer_ids = [item.producer_id for item in producers]
        if len(producer_ids) != len(set(producer_ids)):
            raise ValueError("producer_id values must be unique")
        if not producers:
            raise ValueError("metadata audit requires producer/path coverage")
        gaps = tuple(sorted(self.interface_gaps, key=lambda item: item.gap_id))
        gap_ids = [item.gap_id for item in gaps]
        if len(gap_ids) != len(set(gap_ids)):
            raise ValueError("interface gap IDs must be unique")

        has_gaps = bool(gaps) or any(
            item.completeness != ProducerCompleteness.COMPLETE for item in producers
        )
        status = AuditStatus.GAPS_FOUND if has_gaps else AuditStatus.COMPLETE
        if self.status is not None and self.status != status:
            raise ValueError("audit status does not match producer/interface evidence")

        object.__setattr__(self, "producers", producers)
        object.__setattr__(self, "interface_gaps", gaps)
        object.__setattr__(self, "status", status)

        payload = self.model_dump(
            mode="json",
            exclude={"audit_id", "content_sha256"},
        )
        digest = _sha256(payload)
        identifier = f"TRAJMETA-{digest[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != digest:
            raise ValueError("trajectory metadata audit digest does not match contents")
        if self.audit_id and self.audit_id != identifier:
            raise ValueError("trajectory metadata audit ID does not match contents")
        object.__setattr__(self, "content_sha256", digest)
        object.__setattr__(self, "audit_id", identifier)
        return self


def validated_audit(audit: TrajectoryMetadataAudit) -> TrajectoryMetadataAudit:
    return TrajectoryMetadataAudit.model_validate(audit.model_dump(mode="python"))


def serialize_metadata_audit(audit: TrajectoryMetadataAudit) -> bytes:
    return _canonical_json(validated_audit(audit)).encode("utf-8")
