from __future__ import annotations

import pytest
from pydantic import ValidationError

from investigation_world.fidelity import (
    CoverageStatus,
    DimensionCoverage,
    FidelityClaimRequirement,
    FidelityCompatibilityError,
    FidelityDeclaration,
    FidelityDimension,
    FidelityEvidenceRef,
    FidelityEvidenceType,
    FidelityLevel,
    FidelityPolicyRef,
    FidelityRecord,
    ReproducibilityProfile,
    ResetMode,
    evaluate_fidelity_compatibility,
    require_fidelity_compatibility,
    serialize_fidelity_record,
)


SHA = "a" * 64
POLICY_SHA = "b" * 64


def _evidence(
    evidence_id: str,
    evidence_type: FidelityEvidenceType,
    *dimensions: FidelityDimension,
    version: str = "1.0.0",
) -> FidelityEvidenceRef:
    return FidelityEvidenceRef(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        content_sha256=SHA,
        subject_version=version,
        supports_dimensions=dimensions,
        detail=f"evidence for {evidence_id}",
    )


def _coverage(
    dimension: FidelityDimension,
    evidence_id: str,
    *,
    status: CoverageStatus = CoverageStatus.FULL,
) -> DimensionCoverage:
    return DimensionCoverage(
        dimension=dimension,
        status=status,
        evidence_ids=(evidence_id,),
        detail=f"coverage for {dimension.value}",
    )


def _l2_declaration() -> FidelityDeclaration:
    evidence = (
        _evidence(
            "config",
            FidelityEvidenceType.CONFIGURATION,
            FidelityDimension.STATE_MODEL,
        ),
        _evidence(
            "behavior",
            FidelityEvidenceType.BEHAVIORAL,
            FidelityDimension.APPLICATION_BEHAVIOR,
        ),
        _evidence(
            "artifact",
            FidelityEvidenceType.NATIVE_ARTIFACT,
            FidelityDimension.NATIVE_ARTIFACTS,
        ),
    )
    return FidelityDeclaration(
        environment_id="gold-test",
        environment_version="1.0.0",
        level=FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
        evidence=evidence,
        coverage=(
            _coverage(FidelityDimension.STATE_MODEL, "config"),
            _coverage(FidelityDimension.APPLICATION_BEHAVIOR, "behavior"),
            _coverage(FidelityDimension.NATIVE_ARTIFACTS, "artifact"),
            DimensionCoverage(
                dimension=FidelityDimension.SERVICE_TOPOLOGY,
                status=CoverageStatus.OMITTED,
                detail="multi-service behavior is not represented",
            ),
        ),
        limitations=("network services are not replicated",),
        omitted_real_world_semantics=("external service timing and outages",),
        reproducibility=ReproducibilityProfile(
            reset_mode=ResetMode.DETERMINISTIC_SNAPSHOT,
            deterministic_replay=True,
            constraints=("native toolchain version must be pinned",),
        ),
    )


def _record() -> FidelityRecord:
    return FidelityRecord(
        declaration=_l2_declaration(),
        assessment_policy=FidelityPolicyRef(
            policy_id="default-fidelity-policy",
            policy_version="1",
            content_sha256=POLICY_SHA,
        ),
    )


def test_declaration_is_version_bound_and_content_addressed() -> None:
    record = _record()
    assert record.record_id.startswith("FID-")
    assert len(record.content_sha256) == 64
    assert FidelityRecord.model_validate(record.model_dump()) == record


def test_declared_level_requires_level_specific_evidence() -> None:
    declaration = _l2_declaration()
    payload = declaration.model_dump()
    payload["evidence"] = payload["evidence"][:2]
    with pytest.raises(ValidationError, match="native_artifact evidence"):
        FidelityDeclaration.model_validate(payload)


def test_native_artifact_alone_cannot_upgrade_environment_to_l2() -> None:
    artifact = _evidence(
        "artifact",
        FidelityEvidenceType.NATIVE_ARTIFACT,
        FidelityDimension.NATIVE_ARTIFACTS,
    )
    with pytest.raises(ValidationError, match="state_model"):
        FidelityDeclaration(
            environment_id="not-faithful",
            environment_version="1.0.0",
            level=FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
            evidence=(artifact,),
            coverage=(
                _coverage(FidelityDimension.NATIVE_ARTIFACTS, "artifact"),
            ),
            limitations=("state and behavior are not modeled",),
            omitted_real_world_semantics=("application behavior",),
            reproducibility=ReproducibilityProfile(
                reset_mode=ResetMode.DETERMINISTIC_SNAPSHOT,
                deterministic_replay=True,
                constraints=("fixture only",),
            ),
        )


def test_evidence_from_other_environment_version_is_rejected() -> None:
    declaration = _l2_declaration()
    payload = declaration.model_dump()
    payload["evidence"][0]["subject_version"] = "0.9.0"
    with pytest.raises(ValidationError, match="bind the declared environment version"):
        FidelityDeclaration.model_validate(payload)


def test_coverage_must_be_supported_by_referenced_evidence() -> None:
    declaration = _l2_declaration()
    payload = declaration.model_dump()
    payload["coverage"][0]["evidence_ids"] = ("artifact",)
    with pytest.raises(ValidationError, match="does not support"):
        FidelityDeclaration.model_validate(payload)


def test_claim_policy_accepts_sufficient_level_and_dimensions() -> None:
    requirement = FidelityClaimRequirement(
        claim_id="native-artifact-behavior",
        minimum_level=FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
        required_dimensions=(FidelityDimension.NATIVE_ARTIFACTS,),
        require_full_coverage=True,
    )
    result = evaluate_fidelity_compatibility(_record(), requirement)
    assert result.compatible
    assert result.failures == ()


def test_claim_policy_fails_closed_for_higher_fidelity_claim() -> None:
    requirement = FidelityClaimRequirement(
        claim_id="faithful-service-replica",
        minimum_level=FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA,
        required_dimensions=(FidelityDimension.SERVICE_TOPOLOGY,),
    )
    result = evaluate_fidelity_compatibility(_record(), requirement)
    assert not result.compatible
    assert len(result.failures) == 2
    with pytest.raises(FidelityCompatibilityError, match="faithful-service-replica"):
        require_fidelity_compatibility(_record(), requirement)


def test_copied_level_upgrade_is_rejected_at_external_boundaries() -> None:
    declaration = _l2_declaration().model_copy(
        update={"level": FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA}
    )
    stale_record = _record().model_copy(update={"declaration": declaration})
    requirement = FidelityClaimRequirement(
        claim_id="stale-upgrade",
        minimum_level=FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA,
    )

    with pytest.raises(ValidationError, match="service_replica evidence"):
        serialize_fidelity_record(stale_record)
    with pytest.raises(ValidationError, match="service_replica evidence"):
        evaluate_fidelity_compatibility(stale_record, requirement)


def test_copied_environment_version_is_rejected_at_serialization() -> None:
    declaration = _l2_declaration().model_copy(
        update={"environment_version": "2.0.0"}
    )
    stale_record = _record().model_copy(update={"declaration": declaration})

    with pytest.raises(ValidationError, match="bind the declared environment version"):
        serialize_fidelity_record(stale_record)


def test_copied_evidence_content_invalidates_stale_record_identity() -> None:
    declaration = _l2_declaration()
    changed_evidence = declaration.evidence[0].model_copy(
        update={"content_sha256": "c" * 64}
    )
    changed_declaration = declaration.model_copy(
        update={"evidence": (changed_evidence, *declaration.evidence[1:])}
    )
    stale_record = _record().model_copy(update={"declaration": changed_declaration})

    with pytest.raises(ValidationError, match="content digest"):
        serialize_fidelity_record(stale_record)
