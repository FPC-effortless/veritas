from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigation_world.catalog import (
    BuyerSafeReference,
    BuyerSafeReferenceKind,
    CatalogClassification,
    CatalogEntry,
    CatalogPresentationClass,
    CatalogQuery,
    CatalogSort,
    QualificationFacetState,
    apply_catalog_query,
    serialize_buyer_safe_catalog,
)
from investigation_world.evidence import EvidenceSubjectRef, EvidenceVisibility
from investigation_world.qualification.maturity import (
    DEFAULT_MATURITY_POLICY,
    MATURITY_ORDER,
    EnvironmentIdentity,
    EnvironmentMaturity,
    GateOutcome,
    MaturityGateEvidence,
    VerifierIdentity,
    assess_environment_maturity,
)
from investigation_world.qualification.quality_scorecard import (
    DEFAULT_QUALITY_SCORECARD_POLICY,
    EnvironmentQualityScorecard,
    QualityDimension,
    QualityDimensionAssessment,
    QualityDimensionOutcome,
    QualityScorecardContext,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ENV_DIGEST = "a" * 64
VERIFIER_DIGEST = "b" * 64
PRIVATE_VERIFIER_ID = "PRIVATE-EVALUATOR-SENTINEL"


def _maturity(
    achieved: EnvironmentMaturity = EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
):
    environment = EnvironmentIdentity(
        environment_id=f"env.{achieved.value.lower()}",
        environment_version="1",
        content_sha256=ENV_DIGEST,
    )
    verifier = VerifierIdentity(
        verifier_id=PRIVATE_VERIFIER_ID,
        verifier_version="7",
        content_sha256=VERIFIER_DIGEST,
    )
    target = (
        EnvironmentMaturity.DRAFT
        if achieved == EnvironmentMaturity.DRAFT
        else EnvironmentMaturity.COMMERCIAL_RELEASE
    )
    target_rank = MATURITY_ORDER.index(achieved)
    evidence = []
    counter = 0
    for rank, status in enumerate(MATURITY_ORDER):
        if rank == 0 or rank > target_rank:
            continue
        for gate in DEFAULT_MATURITY_POLICY.requirements[status]:
            counter += 1
            evidence.append(
                MaturityGateEvidence(
                    gate=gate,
                    outcome=GateOutcome.PASS,
                    evidence_id=f"EVID-{counter}",
                    content_sha256=f"{counter % 10}" * 64,
                    environment_content_sha256=ENV_DIGEST,
                    verifier_content_sha256=VERIFIER_DIGEST,
                    qualification_policy_version=DEFAULT_MATURITY_POLICY.policy_version,
                    observed_at=NOW,
                    provenance={"source": "catalog-test"},
                )
            )
    return assess_environment_maturity(
        environment_identity=environment,
        verifier_identity=verifier,
        evidence=tuple(evidence),
        provenance={"source": "catalog-test"},
        target_status=target,
        evaluated_at=NOW,
    )


def _scorecard(record, overrides=None):
    overrides = overrides or {}
    assessments = []
    for rule in DEFAULT_QUALITY_SCORECARD_POLICY.rules:
        outcome = overrides.get(rule.dimension, QualityDimensionOutcome.UNKNOWN)
        assessments.append(
            QualityDimensionAssessment(
                dimension=rule.dimension,
                outcome=outcome,
                evidence=(),
                accepted_evidence_types=rule.accepted_evidence_types,
                minimum_records=rule.minimum_records,
                observed_records=1 if outcome != QualityDimensionOutcome.UNKNOWN else 0,
            )
        )
    return EnvironmentQualityScorecard(
        policy_id=DEFAULT_QUALITY_SCORECARD_POLICY.policy_id,
        policy_version=DEFAULT_QUALITY_SCORECARD_POLICY.policy_version,
        context=QualityScorecardContext(
            environment=EvidenceSubjectRef(
                kind="environment",
                subject_id=record.environment_identity.environment_id,
                version=record.environment_identity.environment_version,
                content_sha256=record.environment_identity.content_sha256,
            ),
            verifier=EvidenceSubjectRef(
                kind="verifier",
                subject_id=record.verifier_identity.verifier_id,
                version=record.verifier_identity.verifier_version,
                content_sha256=record.verifier_identity.content_sha256,
            ),
        ),
        dimensions=tuple(assessments),
    )


def _entry(
    achieved: EnvironmentMaturity = EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
    *,
    domain: str = "investigation",
    fidelity: str | None = None,
):
    record = _maturity(achieved)
    classification = None
    if fidelity is not None:
        classification = CatalogClassification(
            value=fidelity,
            reference=BuyerSafeReference(
                kind=BuyerSafeReferenceKind.FIDELITY,
                identity=f"FIDELITY-{fidelity}",
                content_sha256="c" * 64,
            ),
        )
    return CatalogEntry(
        domain=domain,
        maturity_record=record,
        quality_scorecard=_scorecard(record),
        fidelity=classification,
        limitations=("No broad transfer claim.",),
        buyer_safe_references=(
            BuyerSafeReference(
                kind=BuyerSafeReferenceKind.CONFORMANCE,
                identity="CONF-DEMO",
                version="1",
                content_sha256="d" * 64,
            ),
        ),
    )


def test_catalog_derives_presentation_and_qualification_facets() -> None:
    entry = _entry(EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED)
    facets = {item.facet.value: item.state for item in entry.qualification_facets}

    assert entry.presentation_class == CatalogPresentationClass.QUALIFIED
    assert facets == {
        "scientific": QualificationFacetState.PASS,
        "frontier": QualificationFacetState.UNKNOWN,
        "training": QualificationFacetState.UNKNOWN,
        "commercial": QualificationFacetState.UNKNOWN,
    }


def test_buyer_safe_projection_preserves_dimensions_without_scalar_quality() -> None:
    record = _maturity()
    scorecard = _scorecard(
        record,
        {
            QualityDimension.VERIFIER_PRECISION: QualityDimensionOutcome.FAIL,
            QualityDimension.GENERALIZATION: QualityDimensionOutcome.PASS,
        },
    )
    entry = CatalogEntry(
        domain="investigation",
        maturity_record=record,
        quality_scorecard=scorecard,
    )

    payload = json.loads(serialize_buyer_safe_catalog((entry,)))
    public_entry = payload["entries"][0]
    dimensions = public_entry["quality_scorecard"]["dimensions"]

    assert len(dimensions) == len(QualityDimension)
    assert dimensions["verifier_precision"] == "FAIL"
    assert dimensions["generalization"] == "PASS"
    assert "quality_score" not in public_entry
    assert "task_count" not in public_entry


def test_buyer_safe_projection_omits_verifier_and_private_evidence_identity() -> None:
    entry = _entry()
    payload = serialize_buyer_safe_catalog((entry,))

    assert PRIVATE_VERIFIER_ID.encode() not in payload
    assert VERIFIER_DIGEST.encode() not in payload
    assert b"evaluated_evidence" not in payload
    assert b"provenance" not in payload


def test_scorecard_must_match_exact_environment_and_verifier_revision() -> None:
    record = _maturity()
    scorecard = _scorecard(record)
    wrong_context = scorecard.context.model_copy(
        update={
            "environment": EvidenceSubjectRef(
                kind="environment",
                subject_id="env.other",
                version="1",
                content_sha256=ENV_DIGEST,
            )
        }
    )
    wrong_scorecard = EnvironmentQualityScorecard(
        policy_id=scorecard.policy_id,
        policy_version=scorecard.policy_version,
        context=wrong_context,
        dimensions=scorecard.dimensions,
    )

    with pytest.raises(ValidationError, match="different environment version"):
        CatalogEntry(
            domain="investigation",
            maturity_record=record,
            quality_scorecard=wrong_scorecard,
        )


def test_model_copy_marketing_upgrade_fails_closed_at_public_boundary() -> None:
    entry = _entry(EnvironmentMaturity.EXECUTABLE)
    copied = entry.model_copy(update={"presentation_class": CatalogPresentationClass.COMMERCIAL})

    assert copied.presentation_class == CatalogPresentationClass.COMMERCIAL
    with pytest.raises(ValidationError, match="presentation class"):
        serialize_buyer_safe_catalog((copied,))


def test_model_copy_nested_maturity_mutation_fails_closed() -> None:
    entry = _entry(EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED)
    mutated_record = entry.maturity_record.model_copy(
        update={
            "environment_identity": EnvironmentIdentity(
                environment_id="env.replaced",
                environment_version="1",
                content_sha256="e" * 64,
            )
        }
    )
    copied = entry.model_copy(update={"maturity_record": mutated_record})

    with pytest.raises(ValidationError):
        serialize_buyer_safe_catalog((copied,))


def test_public_classifications_require_correct_reference_kind_and_visibility() -> None:
    record = _maturity()
    scorecard = _scorecard(record)
    wrong_kind = CatalogClassification(
        value="L2_NATIVE_ARTIFACT_EXECUTION",
        reference=BuyerSafeReference(
            kind=BuyerSafeReferenceKind.EXPERIENCE,
            identity="EXP-PUBLIC",
            content_sha256="c" * 64,
        ),
    )
    with pytest.raises(ValidationError, match="fidelity reference"):
        CatalogEntry(
            domain="investigation",
            maturity_record=record,
            quality_scorecard=scorecard,
            fidelity=wrong_kind,
        )

    with pytest.raises(ValidationError, match="must be PUBLIC"):
        BuyerSafeReference(
            kind=BuyerSafeReferenceKind.PACKAGE,
            identity="PKG-PRIVATE",
            content_sha256="c" * 64,
            visibility=EvidenceVisibility.OPERATOR_PRIVATE,
        )


def test_query_filters_and_sorts_by_canonical_maturity_domain_and_fidelity() -> None:
    executable = _entry(
        EnvironmentMaturity.EXECUTABLE,
        domain="operations",
        fidelity="L1_STRUCTURED_SYNTHETIC_APPLICATION",
    )
    scientific = _entry(
        EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
        domain="investigation",
        fidelity="L2_NATIVE_ARTIFACT_EXECUTION",
    )
    commercial = _entry(
        EnvironmentMaturity.COMMERCIAL_RELEASE,
        domain="operations",
        fidelity="L2_NATIVE_ARTIFACT_EXECUTION",
    )

    selected = apply_catalog_query(
        (commercial, executable, scientific),
        CatalogQuery(
            minimum_maturity=EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
            fidelity_levels=("L2_NATIVE_ARTIFACT_EXECUTION",),
            sort_by=CatalogSort.MATURITY,
        ),
    )

    assert [item.maturity_record.status for item in selected] == [
        EnvironmentMaturity.SCIENTIFICALLY_QUALIFIED,
        EnvironmentMaturity.COMMERCIAL_RELEASE,
    ]


def test_catalog_rejects_raw_count_as_unrecognized_quality_metadata() -> None:
    entry = _entry()
    data = entry.model_dump()
    data["task_count"] = 10000

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CatalogEntry.model_validate(data)
