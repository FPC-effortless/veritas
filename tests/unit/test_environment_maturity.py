from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigation_world.qualification import (
    DEFAULT_MATURITY_POLICY,
    EnvironmentIdentity,
    EnvironmentMaturity,
    GateOutcome,
    MaturityGateEvidence,
    MaturityHistory,
    MaturityRecord,
    VerifierIdentity,
    assess_environment_maturity,
)

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)
ENVIRONMENT = EnvironmentIdentity(
    environment_id="ENV-example",
    environment_version="1.2.3",
    content_sha256="a" * 64,
)
VERIFIER = VerifierIdentity(
    verifier_id="VER-example",
    verifier_version="4.5.6",
    content_sha256="b" * 64,
)


def _evidence(
    gate: str,
    outcome: GateOutcome = GateOutcome.PASS,
    *,
    digest_character: str = "c",
) -> MaturityGateEvidence:
    return MaturityGateEvidence(
        gate=gate,
        outcome=outcome,
        evidence_id=f"EVID-{gate}" if outcome != GateOutcome.UNKNOWN else None,
        content_sha256=digest_character * 64 if outcome != GateOutcome.UNKNOWN else None,
        environment_content_sha256=ENVIRONMENT.content_sha256,
        verifier_content_sha256=VERIFIER.content_sha256,
        qualification_policy_version=DEFAULT_MATURITY_POLICY.policy_version,
        observed_at=NOW,
        provenance={"runner": "unit-test"},
    )


def _assess(
    evidence: list[MaturityGateEvidence],
    *,
    target: EnvironmentMaturity = EnvironmentMaturity.COMMERCIAL_RELEASE,
    previous: MaturityRecord | None = None,
    evaluated_at: datetime = NOW,
) -> MaturityRecord:
    return assess_environment_maturity(
        environment_identity=ENVIRONMENT,
        verifier_identity=VERIFIER,
        evidence=evidence,
        provenance={"runner": "unit-test", "suite": "maturity"},
        target_status=target,
        previous_record=previous,
        evaluated_at=evaluated_at,
    )


def test_missing_evidence_is_unknown_and_never_passes() -> None:
    record = _assess([])

    assert record.status == EnvironmentMaturity.DRAFT
    assert record.completed_evidence == ()
    assert record.failed_gates == ()
    assert record.unknown_gates == record.required_evidence


def test_all_lower_transition_gates_are_required() -> None:
    frontier_only = [
        _evidence(gate)
        for gate in DEFAULT_MATURITY_POLICY.requirements[
            EnvironmentMaturity.FRONTIER_QUALIFIED
        ]
    ]

    record = _assess(frontier_only)

    assert record.status == EnvironmentMaturity.DRAFT
    assert "environment_contract_valid" in record.unknown_gates
    assert "frontier_non_saturation" not in record.unknown_gates


def test_transition_reaches_only_the_highest_contiguous_passed_stage() -> None:
    executable = [
        _evidence(gate)
        for gate in DEFAULT_MATURITY_POLICY.requirements[EnvironmentMaturity.EXECUTABLE]
    ]
    verifier = [
        _evidence(gate)
        for gate in DEFAULT_MATURITY_POLICY.requirements[
            EnvironmentMaturity.VERIFIER_VALIDATED
        ]
    ]
    verifier[-1] = _evidence(verifier[-1].gate, GateOutcome.FAIL)

    record = _assess(executable + verifier)

    assert record.status == EnvironmentMaturity.EXECUTABLE
    assert record.failed_gates == ("reward_hack_resistance",)
    assert record.evaluated_evidence[-1].outcome == GateOutcome.FAIL
    assert record.evaluated_evidence[-1].evidence_id == "EVID-reward_hack_resistance"
    assert record.completed_evidence[0].gate == "environment_contract_valid"


def test_failed_evidence_identity_changes_the_qualification_identity() -> None:
    first = _assess(
        [_evidence("environment_contract_valid", GateOutcome.FAIL)],
        target=EnvironmentMaturity.EXECUTABLE,
    )
    second = _assess(
        [
            _evidence(
                "environment_contract_valid",
                GateOutcome.FAIL,
                digest_character="d",
            )
        ],
        target=EnvironmentMaturity.EXECUTABLE,
    )

    assert first.status == second.status == EnvironmentMaturity.DRAFT
    assert first.qualification_identity != second.qualification_identity


def test_evidence_is_bound_to_environment_verifier_and_policy_versions() -> None:
    mismatched = _evidence("environment_contract_valid").model_copy(
        update={"environment_content_sha256": "d" * 64}
    )

    with pytest.raises(ValueError, match="different environment version"):
        _assess([mismatched])


def test_qualification_identity_is_reproducible_across_record_timestamps() -> None:
    evidence = [
        _evidence(gate)
        for gate in DEFAULT_MATURITY_POLICY.required_through(
            EnvironmentMaturity.VERIFIER_VALIDATED
        )
    ]
    first = _assess(
        evidence,
        target=EnvironmentMaturity.VERIFIER_VALIDATED,
        evaluated_at=datetime(2026, 8, 28, 1, tzinfo=timezone.utc),
    )
    second = _assess(
        evidence,
        target=EnvironmentMaturity.VERIFIER_VALIDATED,
        evaluated_at=datetime(2026, 8, 28, 2, tzinfo=timezone.utc),
    )

    assert first.status == EnvironmentMaturity.VERIFIER_VALIDATED
    assert first.qualification_identity == second.qualification_identity
    assert first.record_id != second.record_id


def test_record_rejects_a_status_claim_above_its_evidence() -> None:
    record = _assess([])
    payload = record.model_dump(mode="json")
    payload["status"] = EnvironmentMaturity.COMMERCIAL_RELEASE.value
    payload["record_id"] = ""

    with pytest.raises(ValidationError, match="does not match evidence-derived status"):
        MaturityRecord.model_validate(payload)


def test_requalification_history_preserves_prior_status_and_identity() -> None:
    first = _assess(
        [
            _evidence(gate)
            for gate in DEFAULT_MATURITY_POLICY.required_through(
                EnvironmentMaturity.EXECUTABLE
            )
        ],
        target=EnvironmentMaturity.EXECUTABLE,
    )
    second = _assess(
        [
            _evidence(gate)
            for gate in DEFAULT_MATURITY_POLICY.required_through(
                EnvironmentMaturity.VERIFIER_VALIDATED
            )
        ],
        target=EnvironmentMaturity.VERIFIER_VALIDATED,
        previous=first,
        evaluated_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
    )
    history = MaturityHistory(environment_id=ENVIRONMENT.environment_id, records=(first, second))

    assert history.records[0].status == EnvironmentMaturity.EXECUTABLE
    assert history.records[1].status == EnvironmentMaturity.VERIFIER_VALIDATED
    assert history.records[1].previous_record_id == history.records[0].record_id
    assert history.records[0].qualification_identity != history.records[1].qualification_identity


def test_record_round_trip_retains_content_addressed_identity() -> None:
    original = _assess([], target=EnvironmentMaturity.EXECUTABLE)
    restored = MaturityRecord.model_validate_json(original.model_dump_json())

    assert restored == original
