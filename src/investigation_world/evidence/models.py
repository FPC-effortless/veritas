from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from re import fullmatch
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

EVIDENCE_SCHEMA_VERSION = "veritas.shared-evidence.v1"


class EvidenceVisibility(StrEnum):
    PUBLIC = "public"
    OPERATOR_PRIVATE = "operator_private"
    SEALED = "sealed"


class EvidenceOutcome(StrEnum):
    OBSERVED = "OBSERVED"
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def _canonical_sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


class EvidenceSubjectRef(BaseModel):
    """Content-bound subject that an evidence record is about."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    version: str | None = None
    content_sha256: str

    @model_validator(mode="after")
    def validate_subject(self) -> "EvidenceSubjectRef":
        _validate_sha256(self.content_sha256, field_name="subject content_sha256")
        if fullmatch(r"[a-z][a-z0-9_.-]*", self.kind) is None:
            raise ValueError("subject kind must be a lowercase namespaced token")
        return self


class EvidenceProducerRef(BaseModel):
    """Versioned producer of the evidence observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    producer_id: str = Field(min_length=1)
    producer_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_producer(self) -> "EvidenceProducerRef":
        _validate_sha256(self.content_sha256, field_name="producer content_sha256")
        return self


class EvidencePolicyRef(BaseModel):
    """Exact policy under which evidence was classified or interpreted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_policy(self) -> "EvidencePolicyRef":
        _validate_sha256(self.content_sha256, field_name="policy content_sha256")
        return self


class EvidenceArtifactRef(BaseModel):
    """Opaque artifact identity plus its exact content digest; no locator is carried."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    role: str = Field(default="primary", min_length=1)
    content_sha256: str
    media_type: str | None = None

    @model_validator(mode="after")
    def validate_artifact(self) -> "EvidenceArtifactRef":
        _validate_sha256(self.content_sha256, field_name="artifact content_sha256")
        return self


class EvidenceDependencyRef(BaseModel):
    """Dependency on another shared evidence identity without embedding its payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str
    content_sha256: str
    relation: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_dependency(self) -> "EvidenceDependencyRef":
        if fullmatch(r"EVID-[0-9A-F]{24}", self.evidence_id) is None:
            raise ValueError("dependency evidence_id must be a canonical shared evidence ID")
        _validate_sha256(self.content_sha256, field_name="dependency content_sha256")
        return self


class EvidenceRecord(BaseModel):
    """Shared content-addressed evidence envelope used across Veritas subsystems.

    The semantic evidence identity excludes observation time and provenance, so repeating the
    same exact observation under the same producer/policy yields the same ``evidence_id``.
    ``record_id`` additionally binds the observation event and provenance, preserving an
    append-only audit history without changing the underlying evidence identity.

    Raw evaluator truth is intentionally not a field. Evidence points to opaque, hashed artifacts;
    the record visibility controls whether the envelope itself may appear in buyer-safe output.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = EVIDENCE_SCHEMA_VERSION
    evidence_id: str = ""
    evidence_content_sha256: str = ""
    record_id: str = ""
    evidence_type: str = Field(min_length=1)
    outcome: EvidenceOutcome
    visibility: EvidenceVisibility
    claim: str = Field(min_length=1)
    subjects: tuple[EvidenceSubjectRef, ...] = Field(min_length=1)
    producer: EvidenceProducerRef
    policy: EvidencePolicyRef | None = None
    artifacts: tuple[EvidenceArtifactRef, ...] = Field(min_length=1)
    dependencies: tuple[EvidenceDependencyRef, ...] = ()
    observed_at: datetime
    provenance: dict[str, Any] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_identity(self) -> "EvidenceRecord":
        if self.schema_version != EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported shared evidence schema version")
        if fullmatch(r"[a-z][a-z0-9_.-]*", self.evidence_type) is None:
            raise ValueError("evidence_type must be a lowercase namespaced token")

        subjects = tuple(
            sorted(
                self.subjects,
                key=lambda item: (
                    item.kind,
                    item.subject_id,
                    item.version or "",
                    item.content_sha256,
                ),
            )
        )
        if len(subjects) != len(
            {
                (item.kind, item.subject_id, item.version, item.content_sha256)
                for item in subjects
            }
        ):
            raise ValueError("evidence subjects must be unique")

        artifacts = tuple(
            sorted(
                self.artifacts,
                key=lambda item: (item.role, item.artifact_id, item.content_sha256),
            )
        )
        if len(artifacts) != len(
            {(item.role, item.artifact_id, item.content_sha256) for item in artifacts}
        ):
            raise ValueError("evidence artifacts must be unique")

        dependencies = tuple(
            sorted(
                self.dependencies,
                key=lambda item: (item.relation, item.evidence_id, item.content_sha256),
            )
        )
        if len(dependencies) != len(
            {(item.relation, item.evidence_id, item.content_sha256) for item in dependencies}
        ):
            raise ValueError("evidence dependencies must be unique")

        object.__setattr__(self, "subjects", subjects)
        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "dependencies", dependencies)

        semantic_payload = {
            "schema_version": self.schema_version,
            "evidence_type": self.evidence_type,
            "outcome": self.outcome.value,
            "visibility": self.visibility.value,
            "claim": self.claim,
            "subjects": [item.model_dump(mode="json") for item in subjects],
            "producer": self.producer.model_dump(mode="json"),
            "policy": self.policy.model_dump(mode="json") if self.policy else None,
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "dependencies": [item.model_dump(mode="json") for item in dependencies],
        }
        content_sha256 = _canonical_sha256(semantic_payload)
        evidence_id = f"EVID-{content_sha256[:24].upper()}"

        if self.evidence_content_sha256 and self.evidence_content_sha256 != content_sha256:
            raise ValueError("evidence content digest does not match immutable contents")
        if self.evidence_id and self.evidence_id != evidence_id:
            raise ValueError("evidence ID does not match immutable contents")

        record_payload = {
            "evidence_id": evidence_id,
            "evidence_content_sha256": content_sha256,
            "observed_at": self.observed_at.isoformat(),
            "provenance": self.provenance,
        }
        record_sha256 = _canonical_sha256(record_payload)
        record_id = f"EREC-{record_sha256[:24].upper()}"
        if self.record_id and self.record_id != record_id:
            raise ValueError("evidence record ID does not match observation/provenance")

        object.__setattr__(self, "evidence_content_sha256", content_sha256)
        object.__setattr__(self, "evidence_id", evidence_id)
        object.__setattr__(self, "record_id", record_id)
        return self

    def dependency_ref(self, *, relation: str) -> EvidenceDependencyRef:
        return EvidenceDependencyRef(
            evidence_id=self.evidence_id,
            content_sha256=self.evidence_content_sha256,
            relation=relation,
        )


def serialize_evidence_record(record: EvidenceRecord) -> bytes:
    return _canonical_bytes(record.model_dump(mode="json"))


def serialize_public_evidence(records: Iterable[EvidenceRecord]) -> bytes:
    public_records = sorted(
        (record for record in records if record.visibility == EvidenceVisibility.PUBLIC),
        key=lambda record: record.record_id,
    )
    payload = {
        "schema_version": EVIDENCE_SCHEMA_VERSION,
        "records": [record.model_dump(mode="json") for record in public_records],
    }
    return _canonical_bytes(payload)
