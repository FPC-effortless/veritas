from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import StrEnum
from re import fullmatch
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidencePolicyRef,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)

from .models import AdapterConformanceReport

CONFORMANCE_CERTIFICATE_VERSION = "veritas.adapter-conformance-certificate.v1"


class ConformanceCertificateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _stable_hash(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class PortableContractReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(min_length=1)
    public_contract_id: str = Field(min_length=1)
    public_content_sha256: str

    @model_validator(mode="after")
    def validate_digest(self) -> "PortableContractReference":
        _validate_sha256(
            self.public_content_sha256, field_name="portable public content_sha256"
        )
        return self


class ConformanceAdapterReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_digest(self) -> "ConformanceAdapterReference":
        _validate_sha256(self.content_sha256, field_name="adapter content_sha256")
        return self


class TargetRuntimeReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    runtime_name: str = Field(min_length=1)
    runtime_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_digest(self) -> "TargetRuntimeReference":
        _validate_sha256(self.content_sha256, field_name="runtime content_sha256")
        return self


class ConformanceParity(BaseModel):
    """Buyer-safe parity assertions proven by the canonical conformance run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state: bool | None = None
    reward: bool | None = None
    termination: bool | None = None
    evidence: bool | None = None


class ConformanceCertificate(BaseModel):
    """Content-addressed certificate over an AdapterConformanceReport.

    PASS is intentionally stricter than ``AdapterConformanceReport.passed``: a certificate also
    requires no declared unsupported fields and explicit positive parity evidence for state, reward,
    termination, and evidence. Missing parity evidence is UNKNOWN; any semantic loss or negative
    parity assertion is FAIL.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    certificate_version: str = CONFORMANCE_CERTIFICATE_VERSION
    certificate_id: str = ""
    certificate_content_sha256: str = ""
    source_contract: PortableContractReference
    adapter: ConformanceAdapterReference
    target_runtime: TargetRuntimeReference
    report_id: str = ""
    report_content_sha256: str = ""
    mapped_fields: dict[str, str] = Field(default_factory=dict)
    preserved_fields: tuple[str, ...] = ()
    generated_fields: tuple[str, ...] = ()
    excluded_private_fields: tuple[str, ...] = ()
    unsupported_fields: tuple[str, ...] = ()
    semantic_losses: tuple[str, ...] = ()
    test_vector_hash: str
    parity: ConformanceParity
    status: ConformanceCertificateStatus = ConformanceCertificateStatus.UNKNOWN

    @model_validator(mode="after")
    def validate_certificate(self) -> "ConformanceCertificate":
        if self.certificate_version != CONFORMANCE_CERTIFICATE_VERSION:
            raise ValueError("unsupported conformance certificate version")
        _validate_sha256(self.test_vector_hash, field_name="test vector hash")

        mapped_fields = dict(sorted(self.mapped_fields.items()))
        preserved_fields = tuple(sorted(set(self.preserved_fields)))
        generated_fields = tuple(sorted(set(self.generated_fields)))
        excluded_private_fields = tuple(sorted(set(self.excluded_private_fields)))
        unsupported_fields = tuple(sorted(set(self.unsupported_fields)))
        semantic_losses = tuple(sorted(set(self.semantic_losses)))
        object.__setattr__(self, "mapped_fields", mapped_fields)
        object.__setattr__(self, "preserved_fields", preserved_fields)
        object.__setattr__(self, "generated_fields", generated_fields)
        object.__setattr__(self, "excluded_private_fields", excluded_private_fields)
        object.__setattr__(self, "unsupported_fields", unsupported_fields)
        object.__setattr__(self, "semantic_losses", semantic_losses)

        parity_values = (
            self.parity.state,
            self.parity.reward,
            self.parity.termination,
            self.parity.evidence,
        )
        status = (
            ConformanceCertificateStatus.FAIL
            if semantic_losses or any(value is False for value in parity_values)
            else ConformanceCertificateStatus.UNKNOWN
            if unsupported_fields or any(value is None for value in parity_values)
            else ConformanceCertificateStatus.PASS
        )
        object.__setattr__(self, "status", status)

        report_payload = {
            "mapped_fields": mapped_fields,
            "preserved_fields": list(preserved_fields),
            "generated_fields": list(generated_fields),
            "excluded_private_fields": list(excluded_private_fields),
            "unsupported_fields": list(unsupported_fields),
            "semantic_losses": list(semantic_losses),
            "test_vector_hash": self.test_vector_hash,
        }
        report_sha256 = _stable_hash(report_payload)
        report_id = f"CONFREPORT-{report_sha256[:24].upper()}"
        if self.report_content_sha256 and self.report_content_sha256 != report_sha256:
            raise ValueError("conformance report digest does not match certificate contents")
        if self.report_id and self.report_id != report_id:
            raise ValueError("conformance report ID does not match certificate contents")
        object.__setattr__(self, "report_content_sha256", report_sha256)
        object.__setattr__(self, "report_id", report_id)

        payload = self.model_dump(
            mode="json",
            exclude={"certificate_id", "certificate_content_sha256"},
        )
        certificate_sha256 = _stable_hash(payload)
        certificate_id = f"CONFCERT-{certificate_sha256[:24].upper()}"
        if (
            self.certificate_content_sha256
            and self.certificate_content_sha256 != certificate_sha256
        ):
            raise ValueError("conformance certificate digest does not match immutable contents")
        if self.certificate_id and self.certificate_id != certificate_id:
            raise ValueError("conformance certificate ID does not match immutable contents")
        object.__setattr__(self, "certificate_content_sha256", certificate_sha256)
        object.__setattr__(self, "certificate_id", certificate_id)
        return self

    @property
    def passed(self) -> bool:
        return self.status == ConformanceCertificateStatus.PASS


def certify_adapter_conformance(
    report: AdapterConformanceReport,
    *,
    source_contract: PortableContractReference,
    adapter: ConformanceAdapterReference,
    target_runtime: TargetRuntimeReference,
    parity: ConformanceParity,
) -> ConformanceCertificate:
    return ConformanceCertificate(
        source_contract=source_contract,
        adapter=adapter,
        target_runtime=target_runtime,
        mapped_fields=report.mapped_fields,
        preserved_fields=report.preserved_fields,
        generated_fields=report.generated_fields,
        excluded_private_fields=report.excluded_private_fields,
        unsupported_fields=report.unsupported_fields,
        semantic_losses=report.semantic_losses,
        test_vector_hash=report.test_vector_hash,
        parity=parity,
    )


def conformance_evidence_record(
    certificate: ConformanceCertificate,
    *,
    producer: EvidenceProducerRef,
    policy: EvidencePolicyRef,
    visibility: EvidenceVisibility,
    observed_at: datetime,
    provenance: dict[str, Any],
) -> EvidenceRecord:
    outcome = EvidenceOutcome(certificate.status.value)
    claims = {
        ConformanceCertificateStatus.PASS: "Adapter preserves the certified portable semantics.",
        ConformanceCertificateStatus.FAIL: "Adapter does not preserve the certified portable semantics.",
        ConformanceCertificateStatus.UNKNOWN: "Adapter conformance remains unresolved.",
    }
    return EvidenceRecord(
        evidence_type="conformance.adapter",
        outcome=outcome,
        visibility=visibility,
        claim=claims[certificate.status],
        subjects=(
            EvidenceSubjectRef(
                kind="portable_contract",
                subject_id=certificate.source_contract.public_contract_id,
                version=certificate.source_contract.schema_version,
                content_sha256=certificate.source_contract.public_content_sha256,
            ),
            EvidenceSubjectRef(
                kind="adapter",
                subject_id=certificate.adapter.adapter_name,
                version=certificate.adapter.adapter_version,
                content_sha256=certificate.adapter.content_sha256,
            ),
            EvidenceSubjectRef(
                kind="runtime",
                subject_id=certificate.target_runtime.runtime_name,
                version=certificate.target_runtime.runtime_version,
                content_sha256=certificate.target_runtime.content_sha256,
            ),
        ),
        producer=producer,
        policy=policy,
        artifacts=(
            EvidenceArtifactRef(
                artifact_id=certificate.certificate_id,
                role="conformance_certificate",
                content_sha256=certificate.certificate_content_sha256,
                media_type="application/json",
            ),
            EvidenceArtifactRef(
                artifact_id=certificate.report_id,
                role="adapter_conformance_report",
                content_sha256=certificate.report_content_sha256,
                media_type="application/json",
            ),
        ),
        observed_at=observed_at,
        provenance=provenance,
    )
