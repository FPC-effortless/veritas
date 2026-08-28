from __future__ import annotations

import pydantic
import pytest

import investigation_world.fidelity as fidelity

SHA = "a" * 64
POLICY_SHA = "b" * 64


def _evidence(
    evidence_id: str,
    evidence_type: fidelity.FidelityEvidenceType,
    *dimensions: fidelity.FidelityDimension,
    version: str = "1.0.0",
) -> fidelity.FidelityEvidenceRef:
    return fidelity.FidelityEvidenceRef(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        content_sha256=SHA,
        subject_version=version,
        supports_dimensions=dimensions,
        detail=f"evidence for {evidence_id}",
    )


def _coverage(
    dimension: fidelity.FidelityDimension,
    evidence_id: str,
    *,
    status: fidelity.CoverageStatus = fidelity.CoverageStatus.FULL,
) -> fidelity.DimensionCoverage:
    return fidelity.DimensionCoverage(
        dimension=dimension,
        status=status,
        evidence_ids=(evidence_id,),
        detail=f"coverage for {dimension.value}",
    )


def _l2_declaration() -> fidelity.FidelityDeclaration:
    evidence = (
        _evidence(
            "config",
            fidelity.FidelityEvidenceType.CONFIGURATION,
            fidelity.FidelityDimension.STATE_MODEL,
        ),
        _evidence(
            "behavior",
            fidelity.FidelityEvidenceType.BEHAVIORAL,
            fidelity.FidelityDimension.APPLICATION_BEHAVIOR,
        ),
        _evidence(
            "artifact",
            fidelity.FidelityEvidenceType.NATIVE_ARTIFACT,
            fidelity.FidelityDimension.NATIVE_ARTIFACTS,
        ),
    )
    return fidelity.FidelityDeclaration(
        environment_id="gold-test",
        environment_version="1.0.0",
        level=fidelity.FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
        evidence=evidence,
        coverage=(
            _coverage(fidelity.FidelityDimension.STATE_MODEL, "config"),
            _coverage(fidelity.FidelityDimension.APPLICATION_BEHAVIOR, "behavior"),
            _coverage(fidelity.FidelityDimension.NATIVE_ARTIFACTS, "artifact"),
            fidelity.DimensionCoverage(
                dimension=fidelity.FidelityDimension.SERVICE_TOPOLOGY,
                status=fidelity.CoverageStatus.OMITTED,
                detail="multi-service behavior is not represented",
            ),
        ),
        limitations=("network services are not replicated",),
        omitted_real_world_semantics=("external service timing and outages",),
        reproducibility=fidelity.ReproducibilityProfile(
            reset_mode=fidelity.ResetMode.DETERMINISTIC_SNAPSHOT,
            deterministic_replay=True,
            constraints=("native toolchain version must be pinned",),
        ),
    )


def _record() -> fidelity.FidelityRecord:
    return fidelity.FidelityRecord(
        declaration=_l2_declaration(),
        assessment_policy=fidelity.FidelityPolicyRef(
            policy_id="default-fidelity-policy",
            policy_version="1",
            content_sha256=POLICY_SHA,
        ),
    )


def test_declaration_is_version_bound_and_content_addressed() -> None:
    record = _record()
    assert record.record_id.startswith("FID-")
    assert len(record.content_sha256) == 64
    assert fidelity.FidelityRecord.model_validate(record.model_dump()) == record


def test_declared_level_requires_level_specific_evidence() -> None:
    declaration = _l2_declaration()
    payload = declaration.model_dump()
    payload["evidence"] = payload["evidence"][:2]
    with pytest.raises(pydantic.ValidationError, match="native_artifact evidence"):
        fidelity.FidelityDeclaration.model_validate(payload)


def test_native_artifact_alone_cannot_upgrade_environment_to_l2() -> None:
    artifact = _evidence(
        "artifact",
        fidelity.FidelityEvidenceType.NATIVE_ARTIFACT,
        fidelity.FidelityDimension.NATIVE_ARTIFACTS,
    )
    with pytest.raises(pydantic.ValidationError, match="state_model"):
        fidelity.FidelityDeclaration(
            environment_id="not-faithful",
            environment_version="1.0.0",
            level=fidelity.FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
            evidence=(artifact,),
            coverage=(
                _coverage(fidelity.FidelityDimension.NATIVE_ARTIFACTS, "artifact"),
            ),
            limitations=("state and behavior are not modeled",),
            omitted_real_world_semantics=("application behavior",),
            reproducibility=fidelity.ReproducibilityProfile(
                reset_mode=fidelity.ResetMode.DETERMINISTIC_SNAPSHOT,
                deterministic_replay=True,
                constraints=("fixture only",),
            ),
        )


def test_evidence_from_other_environment_version_is_rejected() -> None:
    declaration = _l2_declaration()
    payload = declaration.model_dump()
    payload["evidence"][0]["subject_version"] = "0.9.0"
    with pytest.raises(pydantic.ValidationError, match="bind the declared environment version"):
        fidelity.FidelityDeclaration.model_validate(payload)


def test_coverage_must_be_supported_by_referenced_evidence() -> None:
    declaration = _l2_declaration()
    payload = declaration.model_dump()
    payload["coverage"][0]["evidence_ids"] = ("artifact",)
    with pytest.raises(pydantic.ValidationError, match="does not support"):
        fidelity.FidelityDeclaration.model_validate(payload)


def test_claim_policy_accepts_sufficient_level_and_dimensions() -> None:
    requirement = fidelity.FidelityClaimRequirement(
        claim_id="native-artifact-behavior",
        minimum_level=fidelity.FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
        required_dimensions=(fidelity.FidelityDimension.NATIVE_ARTIFACTS,),
        require_full_coverage=True,
    )
    result = fidelity.evaluate_fidelity_compatibility(_record(), requirement)
    assert result.compatible
    assert result.failures == ()


def test_claim_policy_fails_closed_for_higher_fidelity_claim() -> None:
    requirement = fidelity.FidelityClaimRequirement(
        claim_id="faithful-service-replica",
        minimum_level=fidelity.FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA,
        required_dimensions=(fidelity.FidelityDimension.SERVICE_TOPOLOGY,),
    )
    result = fidelity.evaluate_fidelity_compatibility(_record(), requirement)
    assert not result.compatible
    assert len(result.failures) == 2
    with pytest.raises(fidelity.FidelityCompatibilityError, match="faithful-service-replica"):
        fidelity.require_fidelity_compatibility(_record(), requirement)


def test_copied_level_upgrade_is_rejected_at_external_boundaries() -> None:
    declaration = _l2_declaration().model_copy(
        update={"level": fidelity.FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA}
    )
    stale_record = _record().model_copy(update={"declaration": declaration})
    requirement = fidelity.FidelityClaimRequirement(
        claim_id="stale-upgrade",
        minimum_level=fidelity.FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA,
    )

    with pytest.raises(pydantic.ValidationError, match="service_replica evidence"):
        fidelity.serialize_fidelity_record(stale_record)
    with pytest.raises(pydantic.ValidationError, match="service_replica evidence"):
        fidelity.evaluate_fidelity_compatibility(stale_record, requirement)


def test_copied_environment_version_is_rejected_at_serialization() -> None:
    declaration = _l2_declaration().model_copy(
        update={"environment_version": "2.0.0"}
    )
    stale_record = _record().model_copy(update={"declaration": declaration})

    with pytest.raises(pydantic.ValidationError, match="bind the declared environment version"):
        fidelity.serialize_fidelity_record(stale_record)


def test_copied_evidence_content_invalidates_stale_record_identity() -> None:
    declaration = _l2_declaration()
    changed_evidence = declaration.evidence[0].model_copy(
        update={"content_sha256": "c" * 64}
    )
    changed_declaration = declaration.model_copy(
        update={"evidence": (changed_evidence, *declaration.evidence[1:])}
    )
    stale_record = _record().model_copy(update={"declaration": changed_declaration})

    with pytest.raises(pydantic.ValidationError, match="content digest"):
        fidelity.serialize_fidelity_record(stale_record)


def test_weakened_copied_claim_requirement_is_rejected_at_policy_boundaries() -> None:
    strict_requirement = fidelity.FidelityClaimRequirement(
        claim_id="faithful-service-policy",
        minimum_level=fidelity.FidelityLevel.L3_FAITHFUL_MULTI_SERVICE_REPLICA,
        required_dimensions=(fidelity.FidelityDimension.SERVICE_TOPOLOGY,),
        require_full_coverage=True,
    )
    assert len(strict_requirement.content_sha256) == 64
    weakened_requirement = strict_requirement.model_copy(
        update={
            "minimum_level": fidelity.FidelityLevel.L2_NATIVE_ARTIFACT_EXECUTION,
            "required_dimensions": (),
            "require_full_coverage": False,
        }
    )

    with pytest.raises(pydantic.ValidationError, match="claim requirement content digest"):
        fidelity.evaluate_fidelity_compatibility(_record(), weakened_requirement)
    with pytest.raises(pydantic.ValidationError, match="claim requirement content digest"):
        fidelity.require_fidelity_compatibility(_record(), weakened_requirement)
