from __future__ import annotations

from enum import StrEnum
from re import fullmatch

from pydantic import BaseModel, ConfigDict, Field, model_validator

FIDELITY_SCHEMA_VERSION = "veritas.environment-fidelity.v1"


class FidelityLevel(StrEnum):
    L0_ABSTRACT_STATE_MODEL = "L0_ABSTRACT_STATE_MODEL"
    L1_STRUCTURED_SYNTHETIC_APPLICATION = "L1_STRUCTURED_SYNTHETIC_APPLICATION"
    L2_NATIVE_ARTIFACT_EXECUTION = "L2_NATIVE_ARTIFACT_EXECUTION"
    L3_FAITHFUL_MULTI_SERVICE_REPLICA = "L3_FAITHFUL_MULTI_SERVICE_REPLICA"
    L4_CONTROLLED_REAL_SYSTEM_INTEGRATION = "L4_CONTROLLED_REAL_SYSTEM_INTEGRATION"


class FidelityDimension(StrEnum):
    STATE_MODEL = "state_model"
    APPLICATION_BEHAVIOR = "application_behavior"
    NATIVE_ARTIFACTS = "native_artifacts"
    SERVICE_TOPOLOGY = "service_topology"
    REAL_SYSTEM_BOUNDARY = "real_system_boundary"


class CoverageStatus(StrEnum):
    FULL = "full"
    PARTIAL = "partial"
    OMITTED = "omitted"


class FidelityEvidenceType(StrEnum):
    CONFIGURATION = "configuration"
    BEHAVIORAL = "behavioral"
    NATIVE_ARTIFACT = "native_artifact"
    SERVICE_REPLICA = "service_replica"
    REAL_SYSTEM_INTEGRATION = "real_system_integration"


class ResetMode(StrEnum):
    DETERMINISTIC_SNAPSHOT = "deterministic_snapshot"
    CONTROLLED_REPROVISION = "controlled_reprovision"
    BEST_EFFORT = "best_effort"
    NONE = "none"


def _validate_sha256(value: str, *, field_name: str) -> None:
    if fullmatch(r"[0-9a-f]{64}", value) is None:
        raise ValueError(f"{field_name} must be a lowercase SHA-256 digest")


class FidelityEvidenceRef(BaseModel):
    """Opaque, version-bound evidence supporting an environment fidelity declaration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_id: str = Field(min_length=1)
    evidence_type: FidelityEvidenceType
    content_sha256: str
    subject_version: str = Field(min_length=1)
    supports_dimensions: tuple[FidelityDimension, ...] = Field(min_length=1)
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_evidence(self) -> "FidelityEvidenceRef":
        _validate_sha256(self.content_sha256, field_name="evidence content_sha256")
        if len(set(self.supports_dimensions)) != len(self.supports_dimensions):
            raise ValueError("evidence supports_dimensions must be unique")
        return self


class DimensionCoverage(BaseModel):
    """Discloses how much of one realism dimension the environment implements."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dimension: FidelityDimension
    status: CoverageStatus
    evidence_ids: tuple[str, ...] = ()
    detail: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_coverage(self) -> "DimensionCoverage":
        if self.status != CoverageStatus.OMITTED and not self.evidence_ids:
            raise ValueError("implemented fidelity coverage must reference evidence")
        if self.status == CoverageStatus.OMITTED and self.evidence_ids:
            raise ValueError("omitted fidelity coverage cannot reference implementation evidence")
        if len(set(self.evidence_ids)) != len(self.evidence_ids):
            raise ValueError("coverage evidence_ids must be unique")
        return self


class ReproducibilityProfile(BaseModel):
    """Reset and replay semantics that qualify a fidelity disclosure."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reset_mode: ResetMode
    deterministic_replay: bool
    constraints: tuple[str, ...] = Field(min_length=1)


_REQUIRED_EVIDENCE_TYPE: dict[FidelityLevel, FidelityEvidenceType] = {
    FidelityLevel.L0_ABSTRACT_STATE_MODEL: FidelityEvidenceType.CONFIGURATION,
    FidelityLevel.L1_STRUCTURED_SYNTHETIC_APPLICATION: FidelityEvidenceType.BEHAVIORAL,
    FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION: FidelityEvidenceType.NATIVE_ARTIFACT,
    FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA: FidelityEvidenceType.SERVICE_REPLICA,
    FidelityLevel.L4_CONTROLLED_REAL_SYSTEM_INTEGRATION: FidelityEvidenceType.REAL_SYSTEM_INTEGRATION,
}

_REQUIRED_DIMENSIONS: dict[FidelityLevel, tuple[FidelityDimension, ...]] = {
    FidelityLevel.L0_ABSTRACT_STATE_MODEL: (FidelityDimension.STATE_MODEL,),
    FidelityLevel.L1_STRUCTURED_SYNTHETIC_APPLICATION: (
        FidelityDimension.STATE_MODEL,
        FidelityDimension.APPLICATION_BEHAVIOR,
    ),
    FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION: (
        FidelityDimension.STATE_MODEL,
        FidelityDimension.APPLICATION_BEHAVIOR,
        FidelityDimension.NATIVE_ARTIFACTS,
    ),
    FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA: (
        FidelityDimension.STATE_MODEL,
        FidelityDimension.APPLICATION_BEHAVIOR,
        FidelityDimension.NATIVE_ARTIFACTS,
        FidelityDimension.SERVICE_TOPOLOGY,
    ),
    FidelityLevel.L4_CONTROLLED_REAL_SYSTEM_INTEGRATION: (
        FidelityDimension.STATE_MODEL,
        FidelityDimension.APPLICATION_BEHAVIOR,
        FidelityDimension.NATIVE_ARTIFACTS,
        FidelityDimension.SERVICE_TOPOLOGY,
        FidelityDimension.REAL_SYSTEM_BOUNDARY,
    ),
}


class FidelityDeclaration(BaseModel):
    """Version-bound, evidence-backed disclosure of environment realism.

    The declaration validates a conservative baseline contract. A qualification or claim policy may
    impose stricter requirements, but cannot waive these evidence and coverage requirements.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = FIDELITY_SCHEMA_VERSION
    environment_id: str = Field(min_length=1)
    environment_version: str = Field(min_length=1)
    level: FidelityLevel
    evidence: tuple[FidelityEvidenceRef, ...] = Field(min_length=1)
    coverage: tuple[DimensionCoverage, ...] = Field(min_length=1)
    limitations: tuple[str, ...] = Field(min_length=1)
    omitted_real_world_semantics: tuple[str, ...] = Field(min_length=1)
    reproducibility: ReproducibilityProfile

    @model_validator(mode="after")
    def validate_contract(self) -> "FidelityDeclaration":
        if self.schema_version != FIDELITY_SCHEMA_VERSION:
            raise ValueError("unsupported fidelity schema version")

        evidence_by_id = {item.evidence_id: item for item in self.evidence}
        if len(evidence_by_id) != len(self.evidence):
            raise ValueError("fidelity evidence IDs must be unique")
        if any(item.subject_version != self.environment_version for item in self.evidence):
            raise ValueError("all fidelity evidence must bind the declared environment version")

        coverage_by_dimension = {item.dimension: item for item in self.coverage}
        if len(coverage_by_dimension) != len(self.coverage):
            raise ValueError("fidelity coverage dimensions must be unique")

        required_type = _REQUIRED_EVIDENCE_TYPE[self.level]
        if not any(item.evidence_type == required_type for item in self.evidence):
            raise ValueError(f"{self.level.value} requires {required_type.value} evidence")

        for dimension in _REQUIRED_DIMENSIONS[self.level]:
            coverage = coverage_by_dimension.get(dimension)
            if coverage is None or coverage.status == CoverageStatus.OMITTED:
                raise ValueError(
                    f"{self.level.value} requires implemented coverage for {dimension.value}"
                )

        for coverage in self.coverage:
            for evidence_id in coverage.evidence_ids:
                evidence = evidence_by_id.get(evidence_id)
                if evidence is None:
                    raise ValueError("coverage references unknown fidelity evidence")
                if coverage.dimension not in evidence.supports_dimensions:
                    raise ValueError(
                        "coverage evidence does not support the disclosed fidelity dimension"
                    )
        return self


class FidelityPolicyRef(BaseModel):
    """Content-bound policy identity used when fidelity gates a claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    policy_id: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    content_sha256: str

    @model_validator(mode="after")
    def validate_policy(self) -> "FidelityPolicyRef":
        _validate_sha256(self.content_sha256, field_name="policy content_sha256")
        return self
