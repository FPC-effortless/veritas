from __future__ import annotations

import hashlib
import json

import pydantic

from . import record, schema

_LEVEL_RANK: dict[schema.FidelityLevel, int] = {
    schema.FidelityLevel.L0_ABSTRACT_STATE_MODEL: 0,
    schema.FidelityLevel.L1_STRUCTURED_SYNTHETIC_APPLICATION: 1,
    schema.FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION: 2,
    schema.FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA: 3,
    schema.FidelityLevel.L4_CONTROLLED_REAL_SYSTEM_INTEGRATION: 4,
}


class FidelityClaimRequirement(pydantic.BaseModel):
    """A content-bound qualification hook describing realism required for one claim."""

    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    claim_id: str = pydantic.Field(min_length=1)
    content_sha256: str = ""
    minimum_level: schema.FidelityLevel
    required_dimensions: tuple[schema.FidelityDimension, ...] = ()
    require_full_coverage: bool = False

    @pydantic.model_validator(mode="after")
    def validate_identity(self) -> "FidelityClaimRequirement":
        payload = {
            "claim_id": self.claim_id,
            "minimum_level": self.minimum_level.value,
            "required_dimensions": [item.value for item in self.required_dimensions],
            "require_full_coverage": self.require_full_coverage,
        }
        canonical = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        content_sha256 = hashlib.sha256(canonical).hexdigest()
        if self.content_sha256 and self.content_sha256 != content_sha256:
            raise ValueError("fidelity claim requirement content digest does not match contents")
        object.__setattr__(self, "content_sha256", content_sha256)
        return self


class FidelityCompatibilityResult(pydantic.BaseModel):
    """Deterministic result of checking one fidelity disclosure against one claim."""

    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    compatible: bool
    claim_id: str
    actual_level: schema.FidelityLevel
    minimum_level: schema.FidelityLevel
    failures: tuple[str, ...]


class FidelityCompatibilityError(ValueError):
    """Raised when a fidelity declaration cannot support a requested claim."""


def revalidate_fidelity_claim_requirement(
    requirement: FidelityClaimRequirement,
) -> FidelityClaimRequirement:
    """Reconstruct a content-bound requirement so copied policy state fails closed."""

    if not requirement.content_sha256:
        raise ValueError("fidelity claim requirement is missing content digest")
    return FidelityClaimRequirement.model_validate(requirement.model_dump(mode="python"))


def evaluate_fidelity_compatibility(
    fidelity_record: record.FidelityRecord,
    requirement: FidelityClaimRequirement,
) -> FidelityCompatibilityResult:
    validated_record = record.revalidate_fidelity_record(fidelity_record)
    validated_requirement = revalidate_fidelity_claim_requirement(requirement)
    failures: list[str] = []
    actual_level = validated_record.declaration.level
    if _LEVEL_RANK[actual_level] < _LEVEL_RANK[validated_requirement.minimum_level]:
        failures.append(
            f"fidelity level {actual_level.value} is below required "
            f"{validated_requirement.minimum_level.value}"
        )

    coverage = {item.dimension: item for item in validated_record.declaration.coverage}
    for dimension in validated_requirement.required_dimensions:
        item = coverage.get(dimension)
        if item is None or item.status == schema.CoverageStatus.OMITTED:
            failures.append(f"required fidelity dimension is not implemented: {dimension.value}")
            continue
        if (
            validated_requirement.require_full_coverage
            and item.status != schema.CoverageStatus.FULL
        ):
            failures.append(f"required fidelity dimension is not full: {dimension.value}")

    return FidelityCompatibilityResult(
        compatible=not failures,
        claim_id=validated_requirement.claim_id,
        actual_level=actual_level,
        minimum_level=validated_requirement.minimum_level,
        failures=tuple(failures),
    )


def require_fidelity_compatibility(
    fidelity_record: record.FidelityRecord,
    requirement: FidelityClaimRequirement,
) -> None:
    result = evaluate_fidelity_compatibility(fidelity_record, requirement)
    if not result.compatible:
        detail = "; ".join(result.failures)
        raise FidelityCompatibilityError(
            f"fidelity disclosure cannot support claim {result.claim_id}: {detail}"
        )
