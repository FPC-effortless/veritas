from __future__ import annotations

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
    """A qualification hook describing the realism required to make one claim."""

    model_config = pydantic.ConfigDict(extra="forbid", frozen=True)

    claim_id: str = pydantic.Field(min_length=1)
    minimum_level: schema.FidelityLevel
    required_dimensions: tuple[schema.FidelityDimension, ...] = ()
    require_full_coverage: bool = False


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


def evaluate_fidelity_compatibility(
    fidelity_record: record.FidelityRecord,
    requirement: FidelityClaimRequirement,
) -> FidelityCompatibilityResult:
    validated_record = record.revalidate_fidelity_record(fidelity_record)
    failures: list[str] = []
    actual_level = validated_record.declaration.level
    if _LEVEL_RANK[actual_level] < _LEVEL_RANK[requirement.minimum_level]:
        failures.append(
            f"fidelity level {actual_level.value} is below required "
            f"{requirement.minimum_level.value}"
        )

    coverage = {item.dimension: item for item in validated_record.declaration.coverage}
    for dimension in requirement.required_dimensions:
        item = coverage.get(dimension)
        if item is None or item.status == schema.CoverageStatus.OMITTED:
            failures.append(f"required fidelity dimension is not implemented: {dimension.value}")
            continue
        if requirement.require_full_coverage and item.status != schema.CoverageStatus.FULL:
            failures.append(f"required fidelity dimension is not full: {dimension.value}")

    return FidelityCompatibilityResult(
        compatible=not failures,
        claim_id=requirement.claim_id,
        actual_level=actual_level,
        minimum_level=requirement.minimum_level,
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
            f"fidelity disclosure cannot support claim {requirement.claim_id}: {detail}"
        )
