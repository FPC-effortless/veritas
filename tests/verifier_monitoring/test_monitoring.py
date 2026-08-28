from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from investigation_world.qualification.maturity import (
    EnvironmentIdentity,
    GateOutcome,
    VerifierIdentity,
)
from investigation_world.verifier_monitoring import (
    DisclosureLevel,
    DiscoverySource,
    ExploitClass,
    ExploitCorpus,
    ExploitDisposition,
    ExploitDispositionStatus,
    ExploitEvidenceReference,
    ExploitFinding,
    ExploitRegressionObservation,
    ExploitSeverity,
    RegressionOutcome,
    buyer_safe_summary,
    monitor_exploits,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ENVIRONMENT = EnvironmentIdentity(
    environment_id="ENV-monitor",
    environment_version="1.0.0",
    content_sha256="a" * 64,
)
VERIFIER_V1 = VerifierIdentity(
    verifier_id="VER-monitor",
    verifier_version="1.0.0",
    content_sha256="b" * 64,
)
VERIFIER_V2 = VerifierIdentity(
    verifier_id="VER-monitor",
    verifier_version="2.0.0",
    content_sha256="c" * 64,
)


def _reference(
    number: int,
    *,
    disclosure: DisclosureLevel = DisclosureLevel.OPERATOR_PRIVATE,
) -> ExploitEvidenceReference:
    return ExploitEvidenceReference(
        evidence_id=f"EXP-EVID-{number}",
        content_sha256=f"{number:064x}",
        reference_uri=f"sealed://verifier-exploits/{number}",
        disclosure=disclosure,
    )


def _finding(
    number: int = 1,
    *,
    severity: ExploitSeverity = ExploitSeverity.HIGH,
    disclosure: DisclosureLevel = DisclosureLevel.OPERATOR_PRIVATE,
    verifier_versions: tuple[str, ...] = (),
) -> ExploitFinding:
    return ExploitFinding(
        exploit_class=ExploitClass.REWARD_HACK,
        severity=severity,
        environment_identity=ENVIRONMENT,
        verifier_identity=VERIFIER_V1,
        reproducer=_reference(number, disclosure=disclosure),
        discovery_source=DiscoverySource.HUMAN_RED_TEAM,
        discovered_at=NOW,
        applicable_verifier_versions=verifier_versions,
        disclosure=disclosure,
        summary="A minimal reward-hack reproducer bypasses the intended outcome gate.",
        provenance={"review": "independent-red-team"},
    )


def _corpus(finding: ExploitFinding) -> ExploitCorpus:
    return ExploitCorpus(
        schema_version="verifier-exploit-corpus-v1",
        findings=(),
        dispositions=(),
    ).append_finding(
        finding,
        recorded_at=NOW,
        provenance={"recorder": "verifier-monitor"},
    )


def _observation(
    finding: ExploitFinding,
    *,
    verifier: VerifierIdentity = VERIFIER_V2,
    outcome: RegressionOutcome = RegressionOutcome.BLOCKED,
    canonical_reward: float = 0.0,
    observed_reward: float = 0.0,
) -> ExploitRegressionObservation:
    return ExploitRegressionObservation(
        exploit_id=finding.exploit_id,
        environment_identity=ENVIRONMENT,
        verifier_identity=verifier,
        outcome=outcome,
        canonical_reward=canonical_reward,
        observed_reward=observed_reward,
        evidence=(
            _reference(90, disclosure=DisclosureLevel.BUYER_SAFE)
            if outcome in {RegressionOutcome.BLOCKED, RegressionOutcome.SUCCEEDED}
            else None
        ),
        observed_at=NOW,
        provenance={"runner": "regression-monitor"},
    )


def _fix(
    corpus: ExploitCorpus,
    finding: ExploitFinding,
    *,
    verifier: VerifierIdentity = VERIFIER_V2,
) -> ExploitCorpus:
    previous = corpus.latest_disposition(finding.exploit_id)
    disposition = ExploitDisposition(
        exploit_id=finding.exploit_id,
        sequence=previous.sequence + 1,
        previous_disposition_id=previous.disposition_id,
        status=ExploitDispositionStatus.FIXED,
        verifier_identity=verifier,
        recorded_at=NOW,
        regression_evidence=_reference(91, disclosure=DisclosureLevel.BUYER_SAFE),
        rationale="The target verifier rejects the retained minimal reproducer.",
        provenance={"review": "verifier-maintainer"},
    )
    return corpus.append_disposition(disposition)


def _monitor(
    corpus: ExploitCorpus,
    observations: list[ExploitRegressionObservation],
    *,
    verifier: VerifierIdentity = VERIFIER_V2,
):
    return monitor_exploits(
        corpus,
        environment_identity=ENVIRONMENT,
        verifier_identity=verifier,
        observations=observations,
        generated_at=NOW,
        provenance={"runner": "batch-exploit-monitor"},
    )


def test_exploit_records_store_references_not_private_payloads() -> None:
    finding = _finding()
    dumped = finding.model_dump_json()

    assert "sealed://verifier-exploits/1" in dumped
    assert "minimal reward-hack reproducer" in dumped
    with pytest.raises(ValidationError):
        ExploitFinding.model_validate(
            {**finding.model_dump(mode="json"), "raw_private_payload": "do-not-store"}
        )


def test_fixed_history_is_append_only_and_retains_open_discovery() -> None:
    finding = _finding()
    original = _corpus(finding)
    fixed = _fix(original, finding)

    assert len(original.dispositions) == 1
    assert len(fixed.dispositions) == 2
    assert fixed.dispositions[0].status == ExploitDispositionStatus.OPEN
    assert fixed.dispositions[1].status == ExploitDispositionStatus.FIXED
    assert original.corpus_id != fixed.corpus_id

    with pytest.raises(ValidationError, match="contiguous from one"):
        ExploitCorpus(
            schema_version=fixed.schema_version,
            findings=fixed.findings,
            dispositions=(fixed.dispositions[1],),
        )


def test_unresolved_severe_exploit_blocks_even_when_one_replay_is_blocked() -> None:
    finding = _finding(severity=ExploitSeverity.CRITICAL)
    corpus = _corpus(finding)

    report = _monitor(corpus, [_observation(finding)])

    assert report.status == GateOutcome.FAIL
    severe = next(gate for gate in report.gates if gate.name == "unresolved_severe_exploits")
    assert severe.outcome == GateOutcome.FAIL
    assert severe.observed == [finding.exploit_id]


def test_fixed_severe_exploit_passes_after_target_version_regression() -> None:
    finding = _finding(severity=ExploitSeverity.HIGH)
    corpus = _fix(_corpus(finding), finding)

    report = _monitor(corpus, [_observation(finding)])

    assert report.status == GateOutcome.PASS
    assert report.applicable_exploit_ids == (finding.exploit_id,)


def test_successful_known_exploit_fails_regression_monitoring() -> None:
    finding = _finding()
    corpus = _fix(_corpus(finding), finding)

    report = _monitor(
        corpus,
        [
            _observation(
                finding,
                outcome=RegressionOutcome.SUCCEEDED,
                canonical_reward=1.0,
                observed_reward=1.0,
            )
        ],
    )

    assert report.status == GateOutcome.FAIL
    resistance = next(
        gate for gate in report.gates if gate.name == "known_exploit_regression_resistance"
    )
    assert resistance.outcome == GateOutcome.FAIL


def test_missing_target_version_replay_remains_unknown() -> None:
    finding = _finding(severity=ExploitSeverity.MEDIUM)
    corpus = _fix(_corpus(finding), finding)

    report = _monitor(corpus, [])

    assert report.status == GateOutcome.UNKNOWN
    coverage = next(
        gate for gate in report.gates if gate.name == "applicable_exploit_replay_coverage"
    )
    assert coverage.outcome == GateOutcome.UNKNOWN


def test_new_verifier_version_must_recheck_unrestricted_finding() -> None:
    finding = _finding()
    corpus = _fix(_corpus(finding), finding, verifier=VERIFIER_V1)

    report = _monitor(corpus, [], verifier=VERIFIER_V2)

    assert report.applicable_exploit_ids == (finding.exploit_id,)
    assert report.status == GateOutcome.UNKNOWN


def test_explicit_version_scope_excludes_unrelated_target() -> None:
    finding = _finding(verifier_versions=("1.0.0",))
    corpus = _fix(_corpus(finding), finding, verifier=VERIFIER_V1)

    report = _monitor(corpus, [], verifier=VERIFIER_V2)

    assert report.applicable_exploit_ids == ()
    assert report.status == GateOutcome.PASS


def test_monitoring_cannot_hide_canonical_reward_drift() -> None:
    finding = _finding()
    corpus = _fix(_corpus(finding), finding)

    report = _monitor(
        corpus,
        [_observation(finding, canonical_reward=0.0, observed_reward=0.2)],
    )

    assert report.status == GateOutcome.FAIL
    parity = next(gate for gate in report.gates if gate.name == "canonical_score_parity")
    assert parity.outcome == GateOutcome.FAIL


def test_buyer_safe_summary_omits_private_exploit_material() -> None:
    private = _finding(number=1, disclosure=DisclosureLevel.OPERATOR_PRIVATE)
    public = _finding(
        number=2,
        severity=ExploitSeverity.MEDIUM,
        disclosure=DisclosureLevel.PUBLIC,
    )
    corpus = _corpus(private).append_finding(
        public,
        recorded_at=NOW,
        provenance={"recorder": "verifier-monitor"},
    )
    corpus = _fix(_fix(corpus, private), public)
    observations = [_observation(private), _observation(public)]
    report = _monitor(corpus, observations)

    summary = buyer_safe_summary(corpus, report, observations)
    serialized = summary.model_dump_json()

    assert summary.private_finding_count == 1
    assert summary.summary_id.startswith("VEXPBUY-")
    assert [item.exploit_id for item in summary.public_findings] == [public.exploit_id]
    assert report.report_id not in serialized
    assert corpus.corpus_id not in serialized
    assert private.exploit_id not in serialized
    assert private.reproducer.evidence_id not in serialized
    assert private.reproducer.content_sha256 not in serialized
    assert private.reproducer.reference_uri not in serialized


def test_buyer_safe_summary_rejects_a_different_corpus_snapshot() -> None:
    finding = _finding()
    corpus = _fix(_corpus(finding), finding)
    observations = [_observation(finding)]
    report = _monitor(corpus, observations)
    expanded = corpus.append_finding(
        _finding(number=3, severity=ExploitSeverity.LOW),
        recorded_at=NOW,
        provenance={"recorder": "verifier-monitor"},
    )

    with pytest.raises(ValueError, match="corpus does not match"):
        buyer_safe_summary(expanded, report, observations)


def test_monitor_report_identity_is_reproducible_across_generation_times() -> None:
    finding = _finding()
    corpus = _fix(_corpus(finding), finding)
    observations = [_observation(finding)]
    first = _monitor(corpus, observations)
    second = monitor_exploits(
        corpus,
        environment_identity=ENVIRONMENT,
        verifier_identity=VERIFIER_V2,
        observations=observations,
        generated_at=NOW + timedelta(hours=1),
        provenance={"runner": "another-batch-process"},
    )

    assert first.generated_at != second.generated_at
    assert first.report_id == second.report_id


def test_supersession_cycles_are_rejected() -> None:
    first = _finding(number=1)
    second = _finding(number=2)
    corpus = _corpus(first).append_finding(
        second,
        recorded_at=NOW,
        provenance={"recorder": "verifier-monitor"},
    )
    first_open = corpus.latest_disposition(first.exploit_id)
    corpus = corpus.append_disposition(
        ExploitDisposition(
            exploit_id=first.exploit_id,
            sequence=2,
            previous_disposition_id=first_open.disposition_id,
            status=ExploitDispositionStatus.SUPERSEDED,
            verifier_identity=VERIFIER_V2,
            recorded_at=NOW,
            superseded_by_exploit_id=second.exploit_id,
            rationale="The second finding is the canonical reproducer.",
            provenance={"review": "verifier-maintainer"},
        )
    )
    second_open = corpus.latest_disposition(second.exploit_id)

    with pytest.raises(ValidationError, match="supersession graph cannot contain a cycle"):
        corpus.append_disposition(
            ExploitDisposition(
                exploit_id=second.exploit_id,
                sequence=2,
                previous_disposition_id=second_open.disposition_id,
                status=ExploitDispositionStatus.SUPERSEDED,
                verifier_identity=VERIFIER_V2,
                recorded_at=NOW,
                superseded_by_exploit_id=first.exploit_id,
                rationale="Invalid cycle back to the first finding.",
                provenance={"review": "unit-test"},
            )
        )


def test_disposition_for_unknown_exploit_is_rejected() -> None:
    finding = _finding()
    corpus = _corpus(finding)
    previous = corpus.latest_disposition(finding.exploit_id)
    unknown = ExploitDisposition(
        exploit_id="VEXP-UNKNOWN",
        sequence=2,
        previous_disposition_id=previous.disposition_id,
        status=ExploitDispositionStatus.FIXED,
        verifier_identity=VERIFIER_V2,
        recorded_at=NOW,
        regression_evidence=_reference(92),
        rationale="Invalid foreign disposition.",
        provenance={"review": "unit-test"},
    )

    with pytest.raises(ValueError, match="unknown finding"):
        ExploitCorpus(
            schema_version=corpus.schema_version,
            findings=corpus.findings,
            dispositions=corpus.dispositions + (unknown,),
        )
