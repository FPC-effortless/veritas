from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from re import fullmatch
from typing import Any, Iterable, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.attestations import (
    AttestationVisibility,
    ContentIdentity,
    EnvironmentAttestation,
)
from investigation_world.conformance.certificate import (
    ConformanceCertificate,
    ConformanceCertificateStatus,
)
from investigation_world.evidence import EvidenceRecord, EvidenceVisibility
from investigation_world.portability.models import (
    PortableEnvironmentManifest,
    PortableVisibility,
)
from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    EnvironmentMaturity,
    MaturityRecord,
    VerifierIdentity,
)
from investigation_world.qualification.quality_scorecard import (
    EnvironmentQualityScorecard,
    QualityDimension,
    QualityDimensionOutcome,
)

PACKAGE_SCHEMA_VERSION = "veritas.qualified-environment-package.v1"
PUBLIC_MANIFEST_SCHEMA_VERSION = "veritas.qualified-environment-package-public.v1"


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


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


def _validate_token(value: str, *, field_name: str) -> None:
    if fullmatch(r"[a-z][a-z0-9_.-]*", value) is None:
        raise ValueError(f"{field_name} must be a lowercase namespaced token")


class PrivateEvaluatorStatus(StrEnum):
    PRESENT = "PRESENT"
    NOT_INCLUDED = "NOT_INCLUDED"
    UNKNOWN = "UNKNOWN"


class PackageEvidenceKind(StrEnum):
    REFERENCE = "reference"
    REVERIFICATION = "reverification"
    DIAGNOSTIC = "diagnostic"
    INSTALLATION = "installation"
    REPRODUCTION = "reproduction"


class PortablePackageBinding(BaseModel):
    """Buyer-safe identifiers copied from the canonical portable manifest."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest_id: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    environment_id: str = Field(min_length=1)
    environment_version: str = Field(min_length=1)
    visibility: PortableVisibility
    taskset_id: str = Field(min_length=1)
    taskset_version: str = Field(min_length=1)
    verifier_id: str = Field(min_length=1)
    verifier_version: str = Field(min_length=1)
    public_contract_id: str | None = None
    public_contract_schema_version: str | None = None

    @model_validator(mode="after")
    def validate_binding(self) -> "PortablePackageBinding":
        if self.visibility == PortableVisibility.PRIVATE_OPERATOR:
            raise ValueError("qualified packages require a public or buyer-safe portable manifest")
        if (self.public_contract_id is None) != (
            self.public_contract_schema_version is None
        ):
            raise ValueError(
                "public contract ID and schema version must be supplied together"
            )
        return self

    @classmethod
    def from_manifest(cls, manifest: PortableEnvironmentManifest) -> Self:
        validated = PortableEnvironmentManifest.model_validate(
            manifest.model_dump(mode="python")
        )
        operational = validated.operational_contract
        return cls(
            manifest_id=validated.manifest_id,
            schema_version=validated.schema_version,
            environment_id=validated.environment_id,
            environment_version=validated.environment_version,
            visibility=validated.visibility,
            taskset_id=validated.taskset.taskset_id,
            taskset_version=validated.taskset.taskset_version,
            verifier_id=validated.verifier.verifier_id,
            verifier_version=validated.verifier.version,
            public_contract_id=(
                operational.public_contract_id if operational is not None else None
            ),
            public_contract_schema_version=(
                operational.schema_version if operational is not None else None
            ),
        )


class MaturityBinding(BaseModel):
    """Content-bound view over Environment Maturity; it never recomputes qualification."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    maturity_record_id: str = Field(min_length=1)
    qualification_identity: str = Field(min_length=1)
    status: EnvironmentMaturity
    target_status: EnvironmentMaturity
    qualification_policy_id: str = Field(min_length=1)
    qualification_policy_version: str = Field(min_length=1)
    environment_content_sha256: str
    verifier_content_sha256: str
    failed_gates: tuple[str, ...] = ()
    unknown_gates: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_binding(self) -> "MaturityBinding":
        _validate_sha256(
            self.environment_content_sha256,
            field_name="maturity environment_content_sha256",
        )
        _validate_sha256(
            self.verifier_content_sha256,
            field_name="maturity verifier_content_sha256",
        )
        object.__setattr__(self, "failed_gates", tuple(sorted(set(self.failed_gates))))
        object.__setattr__(
            self, "unknown_gates", tuple(sorted(set(self.unknown_gates)))
        )
        if set(self.failed_gates).intersection(self.unknown_gates):
            raise ValueError("maturity failed and UNKNOWN gates must be disjoint")
        return self

    @classmethod
    def from_record(cls, record: MaturityRecord) -> Self:
        validated = MaturityRecord.model_validate(record.model_dump(mode="python"))
        return cls(
            maturity_record_id=validated.record_id,
            qualification_identity=validated.qualification_identity,
            status=validated.status,
            target_status=validated.target_status,
            qualification_policy_id=validated.qualification_policy_id,
            qualification_policy_version=validated.qualification_policy_version,
            environment_content_sha256=validated.environment_identity.content_sha256,
            verifier_content_sha256=validated.verifier_identity.content_sha256,
            failed_gates=validated.failed_gates,
            unknown_gates=validated.unknown_gates,
        )


class QualityDimensionBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: QualityDimension
    outcome: QualityDimensionOutcome


class QualityScorecardBinding(BaseModel):
    """Inspectable scorecard outcomes bound to the canonical scorecard identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scorecard_id: str = Field(min_length=1)
    scorecard_content_sha256: str
    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    environment_id: str = Field(min_length=1)
    environment_version: str | None = None
    environment_content_sha256: str
    verifier_id: str = Field(min_length=1)
    verifier_version: str | None = None
    verifier_content_sha256: str
    dimensions: tuple[QualityDimensionBinding, ...]

    @model_validator(mode="after")
    def validate_binding(self) -> "QualityScorecardBinding":
        _validate_sha256(
            self.scorecard_content_sha256,
            field_name="scorecard content_sha256",
        )
        _validate_sha256(
            self.environment_content_sha256,
            field_name="scorecard environment content_sha256",
        )
        _validate_sha256(
            self.verifier_content_sha256,
            field_name="scorecard verifier content_sha256",
        )
        dimensions = tuple(sorted(self.dimensions, key=lambda item: item.dimension.value))
        if set(item.dimension for item in dimensions) != set(QualityDimension):
            raise ValueError("package scorecard must contain every canonical quality dimension")
        if len(dimensions) != len({item.dimension for item in dimensions}):
            raise ValueError("package scorecard dimensions must be unique")
        object.__setattr__(self, "dimensions", dimensions)
        return self

    @classmethod
    def from_scorecard(cls, scorecard: EnvironmentQualityScorecard) -> Self:
        validated = EnvironmentQualityScorecard.model_validate(
            scorecard.model_dump(mode="python")
        )
        return cls(
            scorecard_id=validated.scorecard_id,
            scorecard_content_sha256=validated.scorecard_content_sha256,
            policy_id=validated.policy_id,
            policy_version=validated.policy_version,
            environment_id=validated.context.environment.subject_id,
            environment_version=validated.context.environment.version,
            environment_content_sha256=validated.context.environment.content_sha256,
            verifier_id=validated.context.verifier.subject_id,
            verifier_version=validated.context.verifier.version,
            verifier_content_sha256=validated.context.verifier.content_sha256,
            dimensions=tuple(
                QualityDimensionBinding(
                    dimension=item.dimension,
                    outcome=item.outcome,
                )
                for item in validated.dimensions
            ),
        )

    @property
    def failed_dimensions(self) -> tuple[QualityDimension, ...]:
        return tuple(
            item.dimension
            for item in self.dimensions
            if item.outcome == QualityDimensionOutcome.FAIL
        )

    @property
    def unknown_dimensions(self) -> tuple[QualityDimension, ...]:
        return tuple(
            item.dimension
            for item in self.dimensions
            if item.outcome == QualityDimensionOutcome.UNKNOWN
        )


class ConformanceBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    certificate_id: str = Field(min_length=1)
    certificate_content_sha256: str
    status: ConformanceCertificateStatus
    adapter_name: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    target_runtime_name: str = Field(min_length=1)
    target_runtime_version: str = Field(min_length=1)
    public_contract_id: str = Field(min_length=1)
    public_contract_schema_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_binding(self) -> "ConformanceBinding":
        _validate_sha256(
            self.certificate_content_sha256,
            field_name="conformance certificate content_sha256",
        )
        return self

    @classmethod
    def from_certificate(cls, certificate: ConformanceCertificate) -> Self:
        validated = ConformanceCertificate.model_validate(
            certificate.model_dump(mode="python")
        )
        return cls(
            certificate_id=validated.certificate_id,
            certificate_content_sha256=validated.certificate_content_sha256,
            status=validated.status,
            adapter_name=validated.adapter.adapter_name,
            adapter_version=validated.adapter.adapter_version,
            target_runtime_name=validated.target_runtime.runtime_name,
            target_runtime_version=validated.target_runtime.runtime_version,
            public_contract_id=validated.source_contract.public_contract_id,
            public_contract_schema_version=validated.source_contract.schema_version,
        )


class AttestationBinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    attestation_id: str = Field(min_length=1)
    content_sha256: str
    visibility: AttestationVisibility
    achieved_status: EnvironmentMaturity
    environment_content_sha256: str
    verifier_content_sha256: str

    @model_validator(mode="after")
    def validate_binding(self) -> "AttestationBinding":
        _validate_sha256(self.content_sha256, field_name="attestation content_sha256")
        _validate_sha256(
            self.environment_content_sha256,
            field_name="attestation environment content_sha256",
        )
        _validate_sha256(
            self.verifier_content_sha256,
            field_name="attestation verifier content_sha256",
        )
        return self

    @classmethod
    def from_attestation(cls, attestation: EnvironmentAttestation) -> Self:
        validated = EnvironmentAttestation.model_validate(
            attestation.model_dump(mode="python")
        )
        return cls(
            attestation_id=validated.attestation_id,
            content_sha256=validated.content_sha256,
            visibility=validated.visibility,
            achieved_status=validated.qualification.achieved_status,
            environment_content_sha256=validated.environment.content_sha256,
            verifier_content_sha256=validated.verifier.content_sha256,
        )


class PackageEvidenceBinding(BaseModel):
    """Opaque evidence reference; no artifact locator or private payload is carried."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: PackageEvidenceKind
    evidence_id: str = Field(min_length=1)
    content_sha256: str
    visibility: EvidenceVisibility

    @model_validator(mode="after")
    def validate_binding(self) -> "PackageEvidenceBinding":
        _validate_sha256(self.content_sha256, field_name="package evidence content_sha256")
        return self

    @classmethod
    def from_evidence_record(
        cls,
        record: EvidenceRecord,
        *,
        kind: PackageEvidenceKind,
    ) -> Self:
        validated = EvidenceRecord.model_validate(record.model_dump(mode="python"))
        return cls(
            kind=kind,
            evidence_id=validated.evidence_id,
            content_sha256=validated.evidence_content_sha256,
            visibility=validated.visibility,
        )


class PackageContentReference(BaseModel):
    """Visibility-aware source/license/image/dependency/SBOM identity without a path."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: str
    identity: str = Field(min_length=1)
    version: str | None = None
    content_sha256: str
    visibility: EvidenceVisibility = EvidenceVisibility.PUBLIC

    @model_validator(mode="after")
    def validate_reference(self) -> "PackageContentReference":
        _validate_token(self.kind, field_name="package content kind")
        _validate_sha256(self.content_sha256, field_name=f"{self.kind} content_sha256")
        return self

    @classmethod
    def from_content_identity(
        cls,
        identity: ContentIdentity,
        *,
        visibility: EvidenceVisibility = EvidenceVisibility.PUBLIC,
    ) -> Self:
        validated = ContentIdentity.model_validate(identity.model_dump(mode="python"))
        return cls(
            kind=validated.kind,
            identity=validated.identity,
            version=validated.version,
            content_sha256=validated.content_sha256,
            visibility=visibility,
        )


class PrivateEvaluatorReference(BaseModel):
    """Operator-only evaluator identity. Buyer-safe output exposes status only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: PrivateEvaluatorStatus
    reference_id: str | None = None
    version: str | None = None
    content_sha256: str | None = None

    @model_validator(mode="after")
    def validate_reference(self) -> "PrivateEvaluatorReference":
        supplied = (
            self.reference_id is not None,
            self.content_sha256 is not None,
        )
        if self.status == PrivateEvaluatorStatus.PRESENT:
            if supplied != (True, True):
                raise ValueError(
                    "PRESENT private evaluator requires reference ID and content digest"
                )
            assert self.content_sha256 is not None
            _validate_sha256(
                self.content_sha256,
                field_name="private evaluator content_sha256",
            )
        elif any(supplied) or self.version is not None:
            raise ValueError(
                "non-PRESENT private evaluator status cannot carry private identifiers"
            )
        return self


class PackageLimitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    detail: str = Field(min_length=1)
    unknown: bool = False

    @model_validator(mode="after")
    def validate_limitation(self) -> "PackageLimitation":
        _validate_token(self.code, field_name="limitation code")
        return self


def _sorted_unique(
    values: Iterable[BaseModel],
    *,
    key,
    field_name: str,
) -> tuple:
    ordered = tuple(sorted(values, key=key))
    identities = tuple(key(item) for item in ordered)
    if len(identities) != len(set(identities)):
        raise ValueError(f"{field_name} must be unique")
    return ordered


class BuyerSafeQualifiedPackageManifest(BaseModel):
    """Public procurement view. It never includes operator-private identity or hashes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = PUBLIC_MANIFEST_SCHEMA_VERSION
    manifest_id: str = ""
    manifest_content_sha256: str = ""
    environment: EnvironmentIdentity
    verifier: VerifierIdentity
    portable: PortablePackageBinding
    maturity: MaturityBinding
    scorecard: QualityScorecardBinding
    conformance: tuple[ConformanceBinding, ...] = ()
    attestations: tuple[AttestationBinding, ...] = ()
    evidence: tuple[PackageEvidenceBinding, ...] = ()
    supply_chain: tuple[PackageContentReference, ...] = ()
    private_evaluator_status: PrivateEvaluatorStatus
    known_limitations: tuple[PackageLimitation, ...] = ()

    @model_validator(mode="after")
    def validate_manifest(self) -> "BuyerSafeQualifiedPackageManifest":
        if self.schema_version != PUBLIC_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported buyer-safe qualified-package schema version")
        if any(
            item.visibility != AttestationVisibility.PUBLIC
            for item in self.attestations
        ):
            raise ValueError("buyer-safe manifest may contain only PUBLIC attestations")
        if any(item.visibility != EvidenceVisibility.PUBLIC for item in self.evidence):
            raise ValueError("buyer-safe manifest may contain only PUBLIC evidence references")
        if any(
            item.visibility != EvidenceVisibility.PUBLIC for item in self.supply_chain
        ):
            raise ValueError("buyer-safe manifest may contain only PUBLIC supply-chain references")

        payload = self.model_dump(
            mode="json",
            exclude={"manifest_id", "manifest_content_sha256"},
        )
        digest = _canonical_sha256(payload)
        identifier = f"QPKGPUB-{digest[:24].upper()}"
        if self.manifest_content_sha256 and self.manifest_content_sha256 != digest:
            raise ValueError("buyer-safe manifest digest does not match immutable contents")
        if self.manifest_id and self.manifest_id != identifier:
            raise ValueError("buyer-safe manifest ID does not match immutable contents")
        object.__setattr__(self, "manifest_content_sha256", digest)
        object.__setattr__(self, "manifest_id", identifier)
        return self


class QualifiedEnvironmentPackage(BaseModel):
    """Procurement-grade composition over existing Veritas authorities.

    This object binds exact identities and buyer/operator projections. It is deliberately not an
    authority for environment, verifier, conformance, attestation, scorecard, or maturity semantics.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = PACKAGE_SCHEMA_VERSION
    package_id: str = ""
    package_content_sha256: str = ""
    environment: EnvironmentIdentity
    verifier: VerifierIdentity
    portable: PortablePackageBinding
    maturity: MaturityBinding
    scorecard: QualityScorecardBinding
    conformance: tuple[ConformanceBinding, ...] = ()
    attestations: tuple[AttestationBinding, ...] = Field(min_length=1)
    evidence: tuple[PackageEvidenceBinding, ...] = ()
    supply_chain: tuple[PackageContentReference, ...] = ()
    private_evaluator: PrivateEvaluatorReference
    known_limitations: tuple[PackageLimitation, ...] = ()

    @model_validator(mode="after")
    def validate_package(self) -> "QualifiedEnvironmentPackage":
        if self.schema_version != PACKAGE_SCHEMA_VERSION:
            raise ValueError("unsupported qualified-package schema version")
        if (
            self.portable.environment_id != self.environment.environment_id
            or self.portable.environment_version != self.environment.environment_version
        ):
            raise ValueError("portable manifest belongs to a different environment")
        if (
            self.portable.verifier_id != self.verifier.verifier_id
            or self.portable.verifier_version != self.verifier.verifier_version
        ):
            raise ValueError("portable manifest belongs to a different verifier")
        if (
            self.maturity.environment_content_sha256
            != self.environment.content_sha256
        ):
            raise ValueError("maturity record belongs to a different environment")
        if self.maturity.verifier_content_sha256 != self.verifier.content_sha256:
            raise ValueError("maturity record belongs to a different verifier")
        if (
            self.scorecard.environment_id != self.environment.environment_id
            or self.scorecard.environment_version != self.environment.environment_version
            or self.scorecard.environment_content_sha256
            != self.environment.content_sha256
        ):
            raise ValueError("quality scorecard belongs to a different environment")
        if (
            self.scorecard.verifier_id != self.verifier.verifier_id
            or self.scorecard.verifier_version != self.verifier.verifier_version
            or self.scorecard.verifier_content_sha256 != self.verifier.content_sha256
        ):
            raise ValueError("quality scorecard belongs to a different verifier")

        conformance = _sorted_unique(
            self.conformance,
            key=lambda item: item.certificate_id,
            field_name="conformance certificates",
        )
        attestations = _sorted_unique(
            self.attestations,
            key=lambda item: item.attestation_id,
            field_name="attestations",
        )
        evidence = _sorted_unique(
            self.evidence,
            key=lambda item: (item.kind.value, item.evidence_id),
            field_name="evidence references",
        )
        supply_chain = _sorted_unique(
            self.supply_chain,
            key=lambda item: (
                item.kind,
                item.identity,
                item.version or "",
                item.content_sha256,
                item.visibility.value,
            ),
            field_name="supply-chain references",
        )
        limitations = _sorted_unique(
            self.known_limitations,
            key=lambda item: item.code,
            field_name="known limitations",
        )
        object.__setattr__(self, "conformance", conformance)
        object.__setattr__(self, "attestations", attestations)
        object.__setattr__(self, "evidence", evidence)
        object.__setattr__(self, "supply_chain", supply_chain)
        object.__setattr__(self, "known_limitations", limitations)

        for item in conformance:
            if self.portable.public_contract_id is None:
                raise ValueError(
                    "conformance certificates require a portable public contract identity"
                )
            if (
                item.public_contract_id != self.portable.public_contract_id
                or item.public_contract_schema_version
                != self.portable.public_contract_schema_version
            ):
                raise ValueError(
                    "conformance certificate belongs to a different portable contract"
                )
        for item in attestations:
            if item.environment_content_sha256 != self.environment.content_sha256:
                raise ValueError("attestation belongs to a different environment")
            if item.verifier_content_sha256 != self.verifier.content_sha256:
                raise ValueError("attestation belongs to a different verifier")

        disclosed_kinds = {item.kind for item in supply_chain}
        if "source" not in disclosed_kinds:
            raise ValueError("qualified package requires a source-lineage reference")
        if "license" not in disclosed_kinds:
            raise ValueError("qualified package requires a licensing reference")

        payload = self.model_dump(
            mode="json",
            exclude={"package_id", "package_content_sha256"},
        )
        digest = _canonical_sha256(payload)
        identifier = f"QPKG-{digest[:24].upper()}"
        if self.package_content_sha256 and self.package_content_sha256 != digest:
            raise ValueError("qualified package digest does not match immutable contents")
        if self.package_id and self.package_id != identifier:
            raise ValueError("qualified package ID does not match immutable contents")
        object.__setattr__(self, "package_content_sha256", digest)
        object.__setattr__(self, "package_id", identifier)
        return self

    def buyer_safe_manifest(self) -> BuyerSafeQualifiedPackageManifest:
        validated = QualifiedEnvironmentPackage.model_validate(
            self.model_dump(mode="python")
        )
        return BuyerSafeQualifiedPackageManifest(
            environment=validated.environment,
            verifier=validated.verifier,
            portable=validated.portable,
            maturity=validated.maturity,
            scorecard=validated.scorecard,
            conformance=validated.conformance,
            attestations=tuple(
                item
                for item in validated.attestations
                if item.visibility == AttestationVisibility.PUBLIC
            ),
            evidence=tuple(
                item
                for item in validated.evidence
                if item.visibility == EvidenceVisibility.PUBLIC
            ),
            supply_chain=tuple(
                item
                for item in validated.supply_chain
                if item.visibility == EvidenceVisibility.PUBLIC
            ),
            private_evaluator_status=validated.private_evaluator.status,
            known_limitations=validated.known_limitations,
        )


def build_qualified_environment_package(
    *,
    environment: EnvironmentIdentity,
    verifier: VerifierIdentity,
    portable_manifest: PortableEnvironmentManifest,
    maturity_record: MaturityRecord,
    scorecard: EnvironmentQualityScorecard,
    conformance_certificates: Iterable[ConformanceCertificate] = (),
    attestations: Iterable[EnvironmentAttestation],
    evidence: Iterable[PackageEvidenceBinding] = (),
    supply_chain: Iterable[PackageContentReference],
    private_evaluator: PrivateEvaluatorReference,
    known_limitations: Iterable[PackageLimitation] = (),
) -> QualifiedEnvironmentPackage:
    """Compose a package from existing authorities without recomputing their semantics."""

    return QualifiedEnvironmentPackage(
        environment=EnvironmentIdentity.model_validate(
            environment.model_dump(mode="python")
        ),
        verifier=VerifierIdentity.model_validate(verifier.model_dump(mode="python")),
        portable=PortablePackageBinding.from_manifest(portable_manifest),
        maturity=MaturityBinding.from_record(maturity_record),
        scorecard=QualityScorecardBinding.from_scorecard(scorecard),
        conformance=tuple(
            ConformanceBinding.from_certificate(item)
            for item in conformance_certificates
        ),
        attestations=tuple(
            AttestationBinding.from_attestation(item) for item in attestations
        ),
        evidence=tuple(evidence),
        supply_chain=tuple(supply_chain),
        private_evaluator=private_evaluator,
        known_limitations=tuple(known_limitations),
    )


def serialize_qualified_package(package: QualifiedEnvironmentPackage) -> bytes:
    validated = QualifiedEnvironmentPackage.model_validate(
        package.model_dump(mode="python")
    )
    return _canonical_bytes(validated.model_dump(mode="json"))


def serialize_buyer_safe_manifest(package: QualifiedEnvironmentPackage) -> bytes:
    return _canonical_bytes(package.buyer_safe_manifest().model_dump(mode="json"))
