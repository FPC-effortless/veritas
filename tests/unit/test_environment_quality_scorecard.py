from __future__ import annotations

from datetime import datetime, timezone

from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)
from investigation_world.qualification.quality_scorecard import (
    DEFAULT_QUALITY_SCORECARD_POLICY,
    QualityDimension,
    QualityDimensionOutcome,
    QualityScorecardContext,
    build_environment_quality_scorecard,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ENVIRONMENT = EvidenceSubjectRef(
    kind="environment",
    subject_id="ENV-scorecard",
    version="1.0.0",
    content_sha256="a" * 64,
)
VERIFIER = EvidenceSubjectRef(
    kind="verifier",
    subject_id="VER-scorecard",
    version="1.0.0",
    content_sha256="b" * 64,
)
PORTABLE = EvidenceSubjectRef(
    kind="portable_contract",
    subject_id="POPC-PUBLIC-scorecard",
    version="1.0.0",
    content_sha256="c" * 64,
)
PRODUCER = EvidenceProducerRef(
    producer_id="quality-test",
    producer_version="1.0.0",
    content_sha256="d" * 64,
)
CONTEXT = QualityScorecardContext(
    environment=ENVIRONMENT,
    verifier=VERIFIER,
    portable_contract=PORTABLE,
)


def _subject(kind: str) -> EvidenceSubjectRef:
    return {
        "environment": ENVIRONMENT,
        "verifier": VERIFIER,
        "portable_contract": PORTABLE,
    }[kind]


def _record(
    evidence_type: str,
    *,
    subject_kind: str,
    outcome: EvidenceOutcome = EvidenceOutcome.PASS,
    visibility: EvidenceVisibility = EvidenceVisibility.PUBLIC,
    marker: int = 1,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_type=evidence_type,
        outcome=outcome,
        visibility=visibility,
        claim=f"Evidence for {evidence_type}.",
        subjects=(_subject(subject_kind),),
        producer=PRODUCER,
        artifacts=(
            EvidenceArtifactRef(
                artifact_id=f"ART-{marker}",
                content_sha256=f"{marker:064x}",
            ),
        ),
        observed_at=NOW,
        provenance={"runner": "unit-test"},
    )


def _complete_evidence() -> list[EvidenceRecord]:
    values: list[EvidenceRecord] = []
    for index, rule in enumerate(DEFAULT_QUALITY_SCORECARD_POLICY.rules, start=1):
        values.append(
            _record(
                rule.accepted_evidence_types[0],
                subject_kind=rule.subject_kind,
                marker=index,
            )
        )
    return values


def _dimension(scorecard, dimension: QualityDimension):
    return next(item for item in scorecard.dimensions if item.dimension == dimension)


def test_complete_all_pass_evidence_produces_complete_multidimensional_scorecard() -> None:
    scorecard = build_environment_quality_scorecard(
        context=CONTEXT,
        evidence=_complete_evidence(),
    )

    assert scorecard.complete
    assert not scorecard.failed_dimensions
    assert not scorecard.unknown_dimensions
    assert len(scorecard.dimensions) == len(QualityDimension)
    assert scorecard.scorecard_id.startswith("QSCORE-")


def test_missing_dimension_is_unknown_not_pass() -> None:
    evidence = _complete_evidence()
    evidence = [
        item
        for item in evidence
        if item.evidence_type != "qualification.frontier_headroom"
    ]

    scorecard = build_environment_quality_scorecard(context=CONTEXT, evidence=evidence)

    frontier = _dimension(scorecard, QualityDimension.FRONTIER_HEADROOM)
    assert frontier.outcome == QualityDimensionOutcome.UNKNOWN
    assert QualityDimension.FRONTIER_HEADROOM in scorecard.unknown_dimensions
    assert not scorecard.complete


def test_failed_evidence_fails_only_its_dimension_without_scalar_average() -> None:
    evidence = _complete_evidence()
    evidence = [
        _record(
            item.evidence_type,
            subject_kind=next(subject.kind for subject in item.subjects),
            outcome=(
                EvidenceOutcome.FAIL
                if item.evidence_type == "qualification.reward_hack_resistance"
                else item.outcome
            ),
            marker=index + 50,
        )
        for index, item in enumerate(evidence)
    ]

    scorecard = build_environment_quality_scorecard(context=CONTEXT, evidence=evidence)

    reward_hack = _dimension(scorecard, QualityDimension.REWARD_HACK_RESISTANCE)
    assert reward_hack.outcome == QualityDimensionOutcome.FAIL
    assert scorecard.failed_dimensions == (QualityDimension.REWARD_HACK_RESISTANCE,)
    assert not hasattr(scorecard, "overall_score")


def test_observed_or_unknown_evidence_cannot_become_dimension_pass() -> None:
    observed = _record(
        "qualification.task_ambiguity",
        subject_kind="environment",
        outcome=EvidenceOutcome.OBSERVED,
    )
    unknown = _record(
        "qualification.state_fidelity",
        subject_kind="environment",
        outcome=EvidenceOutcome.UNKNOWN,
        marker=2,
    )

    scorecard = build_environment_quality_scorecard(
        context=CONTEXT,
        evidence=(observed, unknown),
    )

    assert (
        _dimension(scorecard, QualityDimension.TASK_AMBIGUITY).outcome
        == QualityDimensionOutcome.UNKNOWN
    )
    assert (
        _dimension(scorecard, QualityDimension.STATE_FIDELITY).outcome
        == QualityDimensionOutcome.UNKNOWN
    )


def test_evidence_for_different_environment_is_not_reused() -> None:
    wrong_environment = EvidenceSubjectRef(
        kind="environment",
        subject_id=ENVIRONMENT.subject_id,
        version=ENVIRONMENT.version,
        content_sha256="f" * 64,
    )
    record = EvidenceRecord(
        evidence_type="qualification.task_qa",
        outcome=EvidenceOutcome.PASS,
        visibility=EvidenceVisibility.PUBLIC,
        claim="Task QA passes for another environment version.",
        subjects=(wrong_environment,),
        producer=PRODUCER,
        artifacts=(EvidenceArtifactRef(artifact_id="ART-wrong", content_sha256="1" * 64),),
        observed_at=NOW,
        provenance={"runner": "unit-test"},
    )

    scorecard = build_environment_quality_scorecard(context=CONTEXT, evidence=(record,))

    assert (
        _dimension(scorecard, QualityDimension.EXPERT_TASK_QA).outcome
        == QualityDimensionOutcome.UNKNOWN
    )


def test_runtime_conformance_binds_to_exact_portable_contract() -> None:
    good = _record("conformance.adapter", subject_kind="portable_contract")
    wrong_contract = EvidenceSubjectRef(
        kind="portable_contract",
        subject_id=PORTABLE.subject_id,
        version=PORTABLE.version,
        content_sha256="f" * 64,
    )
    wrong = EvidenceRecord(
        evidence_type="conformance.adapter",
        outcome=EvidenceOutcome.PASS,
        visibility=EvidenceVisibility.PUBLIC,
        claim="Different portable contract passes conformance.",
        subjects=(wrong_contract,),
        producer=PRODUCER,
        artifacts=(EvidenceArtifactRef(artifact_id="ART-wrong", content_sha256="2" * 64),),
        observed_at=NOW,
        provenance={"runner": "unit-test"},
    )

    scorecard = build_environment_quality_scorecard(
        context=CONTEXT,
        evidence=(wrong, good),
    )

    assessment = _dimension(scorecard, QualityDimension.RUNTIME_CONFORMANCE)
    assert assessment.outcome == QualityDimensionOutcome.PASS
    assert assessment.observed_records == 1


def test_public_projection_does_not_reveal_private_evidence_identity() -> None:
    private = _record(
        "qualification.task_qa",
        subject_kind="environment",
        visibility=EvidenceVisibility.OPERATOR_PRIVATE,
    )

    public_scorecard = build_environment_quality_scorecard(
        context=CONTEXT,
        evidence=(private,),
        public_only=True,
    )

    assessment = _dimension(public_scorecard, QualityDimension.EXPERT_TASK_QA)
    assert assessment.outcome == QualityDimensionOutcome.UNKNOWN
    assert assessment.evidence == ()
    assert assessment.observed_records == 0
    assert private.evidence_id not in public_scorecard.model_dump_json()


def test_scorecard_identity_is_independent_of_input_evidence_order() -> None:
    evidence = _complete_evidence()

    first = build_environment_quality_scorecard(context=CONTEXT, evidence=evidence)
    second = build_environment_quality_scorecard(
        context=CONTEXT,
        evidence=reversed(evidence),
    )

    assert first.scorecard_id == second.scorecard_id
    assert first.scorecard_content_sha256 == second.scorecard_content_sha256
