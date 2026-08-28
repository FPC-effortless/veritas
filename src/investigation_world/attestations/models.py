from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from re import fullmatch
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    EnvironmentMaturity,
    MaturityRecord,
    VerifierIdentity,
)

ATTESTATION_SCHEMA_VERSION = "veritas.environment-attestation.v1"
SIGNATURE_SCHEMA_VERSION = "veritas.environment-attestation-signature.v1"


class AttestationVisibility(StrEnum):
    PUBLIC = "public"
    OPERATOR_PRIVATE = "operator_private"
    SEALED = "sealed"


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


def _validate_token(value: str, *, field_name: str) -> None:
    if fullmatch(r"[a-z][a-z0-9_.-]*", value) is None:
        raise ValueError(f"{field_name} must be a lowercase namespaced token")


class ContentIdentity(BaseModel):
    """Opaque content-bound identity; deliberately carries no locator or payload."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    identity: str = Field(min_length=1)
    version: str | None = None
    content_sha256: str

    @model_validator(mode="after")
    def validate_identity(self) -> "ContentIdentity":
        _validate_token(self.kind, field_name="identity kind")
        _validate_sha256(self.content_sha256, field_name=f"{self.kind} content_sha256")
        return self


class ArtifactIdentity(BaseModel):
    """Content identity of a distributable artifact, without embedding artifact bytes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str = Field(min_length=1)
    role: str
    content_sha256: str
    media_type: str | None = None

    @model_validator(mode="after")
    def validate_artifact(self) -> "ArtifactIdentity":
        _validate_token(self.role, field_name="artifact role")
        _validate_sha256(self.content_sha256, field_name="artifact content_sha256")
        return self


class QualificationBinding(BaseModel):
    """Reference to validated maturity output; not a replacement for qualification evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    maturity_record_id: str = Field(min_length=1)
    qualification_identity: str = Field(min_length=1)
    achieved_status: EnvironmentMaturity
    qualification_policy_id: str = Field(min_length=1)
    qualification_policy_version: str = Field(min_length=1)
    environment_content_sha256: str
    verifier_content_sha256: str

    @model_validator(mode="after")
    def validate_binding(self) -> "QualificationBinding":
        if self.achieved_status == EnvironmentMaturity.DRAFT:
            raise ValueError("attestations require a maturity record beyond DRAFT")
        _validate_sha256(
            self.environment_content_sha256,
            field_name="qualification environment_content_sha256",
        )
        _validate_sha256(
            self.verifier_content_sha256,
            field_name="qualification verifier_content_sha256",
        )
        return self

    @classmethod
    def from_maturity_record(cls, record: MaturityRecord) -> "QualificationBinding":
        return cls(
            maturity_record_id=record.record_id,
            qualification_identity=record.qualification_identity,
            achieved_status=record.status,
            qualification_policy_id=record.qualification_policy_id,
            qualification_policy_version=record.qualification_policy_version,
            environment_content_sha256=record.environment_identity.content_sha256,
            verifier_content_sha256=record.verifier_identity.content_sha256,
        )


class EnvironmentAttestation(BaseModel):
    """Deterministic supply-chain statement for a qualified environment artifact set.

    This object binds identities and qualification outputs. It does not assert that qualification
    gates passed beyond the referenced validated ``MaturityRecord`` and it never embeds private
    evaluator evidence or artifact contents.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = ATTESTATION_SCHEMA_VERSION
    visibility: AttestationVisibility = AttestationVisibility.OPERATOR_PRIVATE
    attestation_id: str = ""
    content_sha256: str = ""
    environment: EnvironmentIdentity
    artifacts: tuple[ArtifactIdentity, ...] = Field(min_length=1)
    source: ContentIdentity
    builder: ContentIdentity
    verifier: VerifierIdentity
    qualification: QualificationBinding
    adapters: tuple[ContentIdentity, ...] = ()
    dependencies: tuple[ContentIdentity, ...] = ()
    sbom: ContentIdentity

    @model_validator(mode="after")
    def validate_attestation(self) -> "EnvironmentAttestation":
        if self.schema_version != ATTESTATION_SCHEMA_VERSION:
            raise ValueError("unsupported environment attestation schema version")
        if self.environment.content_sha256 != self.qualification.environment_content_sha256:
            raise ValueError("qualification belongs to a different environment artifact")
        if self.verifier.content_sha256 != self.qualification.verifier_content_sha256:
            raise ValueError("qualification belongs to a different verifier")
        if self.source.kind != "source":
            raise ValueError("source identity kind must be 'source'")
        if self.builder.kind != "builder":
            raise ValueError("builder identity kind must be 'builder'")
        if self.sbom.kind != "sbom":
            raise ValueError("SBOM identity kind must be 'sbom'")
        if any(item.kind != "adapter" for item in self.adapters):
            raise ValueError("adapter identities must use kind 'adapter'")
        if any(item.kind != "dependency" for item in self.dependencies):
            raise ValueError("dependency identities must use kind 'dependency'")

        artifacts = tuple(
            sorted(
                self.artifacts,
                key=lambda item: (item.role, item.artifact_id, item.content_sha256),
            )
        )
        adapters = _sorted_unique_identities(self.adapters, field_name="adapters")
        dependencies = _sorted_unique_identities(self.dependencies, field_name="dependencies")
        if len(artifacts) != len(
            {(item.role, item.artifact_id, item.content_sha256) for item in artifacts}
        ):
            raise ValueError("attested artifacts must be unique")

        object.__setattr__(self, "artifacts", artifacts)
        object.__setattr__(self, "adapters", adapters)
        object.__setattr__(self, "dependencies", dependencies)

        payload = {
            "schema_version": self.schema_version,
            "visibility": self.visibility.value,
            "environment": self.environment.model_dump(mode="json"),
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
            "source": self.source.model_dump(mode="json"),
            "builder": self.builder.model_dump(mode="json"),
            "verifier": self.verifier.model_dump(mode="json"),
            "qualification": self.qualification.model_dump(mode="json"),
            "adapters": [item.model_dump(mode="json") for item in adapters],
            "dependencies": [item.model_dump(mode="json") for item in dependencies],
            "sbom": self.sbom.model_dump(mode="json"),
        }
        expected_digest = _canonical_sha256(payload)
        expected_id = f"EATT-{expected_digest[:24].upper()}"
        if self.content_sha256 and self.content_sha256 != expected_digest:
            raise ValueError("attestation digest does not match immutable contents")
        if self.attestation_id and self.attestation_id != expected_id:
            raise ValueError("attestation ID does not match immutable contents")
        object.__setattr__(self, "content_sha256", expected_digest)
        object.__setattr__(self, "attestation_id", expected_id)
        return self


class AttestationSignature(BaseModel):
    """Detached signature metadata over an attestation content digest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = SIGNATURE_SCHEMA_VERSION
    attestation_id: str = Field(min_length=1)
    attestation_content_sha256: str
    algorithm: str
    key_id: str = Field(min_length=1)
    signature: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_signature(self) -> "AttestationSignature":
        if self.schema_version != SIGNATURE_SCHEMA_VERSION:
            raise ValueError("unsupported attestation signature schema version")
        if fullmatch(r"EATT-[0-9A-F]{24}", self.attestation_id) is None:
            raise ValueError("signature attestation_id must be a canonical attestation ID")
        _validate_sha256(
            self.attestation_content_sha256,
            field_name="signature attestation_content_sha256",
        )
        _validate_token(self.algorithm, field_name="signature algorithm")
        return self

    def binds(self, attestation: EnvironmentAttestation) -> bool:
        try:
            validated = _validated_attestation(attestation)
        except ValidationError:
            return False
        return (
            self.attestation_id == validated.attestation_id
            and self.attestation_content_sha256 == validated.content_sha256
        )


def _sorted_unique_identities(
    identities: Iterable[ContentIdentity], *, field_name: str
) -> tuple[ContentIdentity, ...]:
    sorted_identities = tuple(
        sorted(
            identities,
            key=lambda item: (item.kind, item.identity, item.version or "", item.content_sha256),
        )
    )
    keys = {
        (item.kind, item.identity, item.version, item.content_sha256) for item in sorted_identities
    }
    if len(keys) != len(sorted_identities):
        raise ValueError(f"attestation {field_name} must be unique")
    return sorted_identities


def _validated_attestation(attestation: EnvironmentAttestation) -> EnvironmentAttestation:
    """Re-run every attestation invariant instead of trusting an existing model instance."""
    return EnvironmentAttestation.model_validate(attestation.model_dump(mode="python"))


def serialize_attestation(attestation: EnvironmentAttestation) -> bytes:
    validated = _validated_attestation(attestation)
    return _canonical_bytes(validated.model_dump(mode="json"))


def serialize_public_attestation(attestation: EnvironmentAttestation) -> bytes:
    """Serialize only a semantically valid attestation authorized for public disclosure."""
    validated = _validated_attestation(attestation)
    if validated.visibility != AttestationVisibility.PUBLIC:
        raise ValueError("only PUBLIC attestations may be serialized for public disclosure")
    return _canonical_bytes(validated.model_dump(mode="json"))
