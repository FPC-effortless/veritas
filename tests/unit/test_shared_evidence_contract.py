from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidencePolicyRef,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
    serialize_evidence_record,
    serialize_public_evidence,
)
from investigation_world.evidence.maturity import maturity_gate_evidence_from_record
from investigation_world.qualification.maturity import GateOutcome

NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


def _record(
    *,
    outcome: EvidenceOutcome = EvidenceOutcome.PASS,
    visibility: EvidenceVisibility = EvidenceVisibility.PUBLIC,
    claim: str = "Verifier replay is deterministic.",
    provenance: dict[str, str] | None = None,
    observed_at: datetime = NOW,
) -> EvidenceRecord:
    return EvidenceRecord(
        evidence_type="qualification.verifier_replay",
        outcome=outcome,
        visibility=visibility,
        claim=claim,
        subjects=(
            EvidenceSubjectRef(
                kind="verifier",
                subject_id="VER-test",
                version="1.0.0",
                content_sha256="b" * 64,
            ),
            EvidenceSubjectRef(
                kind="environment",
                subject_id="ENV-test",
                version="1.0.0",
                content_sha256="a" * 64,
            ),
        ),
        producer=EvidenceProducerRef(
            producer_id="verifier-qualification-suite",
            producer_version="1.0.0",
            content_sha256="c" * 64,
        ),
        policy=EvidencePolicyRef(
            policy_id="MPOL-test",
            policy_version="veritas-environment-maturity-v1",
            content_sha256="d" * 64,
        ),
        artifacts=(
            EvidenceArtifactRef(
                artifact_id="VQREPORT-test",
                role="qualification_report",
                content_sha256="e" * 64,
                media_type="application/json",
            ),
        ),
        observed_at=observed_at,
        provenance=provenance or {"runner": "unit-test"},
    )


def test_shared_evidence_identity_is_content_addressed_and_canonical() -> None:
    first = _record()
    second = EvidenceRecord(
        evidence_type=first.evidence_type,
        outcome=first.outcome,
        visibility=first.visibility,
        claim=first.claim,
        subjects=tuple(reversed(first.subjects)),
        producer=first.producer,
        policy=first.policy,
        artifacts=first.artifacts,
        observed_at=first.observed_at,
        provenance=first.provenance,
    )

    assert first.evidence_id == second.evidence_id
    assert first.evidence_content_sha256 == second.evidence_content_sha256
    assert first.record_id == second.record_id
    assert serialize_evidence_record(first) == serialize_evidence_record(second)


def test_observation_metadata_changes_record_not_semantic_evidence_identity() -> None:
    first = _record()
    second = _record(
        observed_at=datetime(2026, 8, 29, tzinfo=timezone.utc),
        provenance={"runner": "independent-review"},
    )

    assert first.evidence_id == second.evidence_id
    assert first.evidence_content_sha256 == second.evidence_content_sha256
    assert first.record_id != second.record_id


def test_semantic_change_changes_evidence_identity() -> None:
    passing = _record(outcome=EvidenceOutcome.PASS)
    failing = _record(outcome=EvidenceOutcome.FAIL)

    assert passing.evidence_id != failing.evidence_id
    assert passing.evidence_content_sha256 != failing.evidence_content_sha256


def test_invalid_or_stale_content_identity_fails_closed() -> None:
    record = _record()

    with pytest.raises(ValueError, match="evidence ID does not match"):
        record.model_copy(update={"evidence_id": "EVID-000000000000000000000000"}).model_validate(
            record.model_dump(mode="json")
            | {"evidence_id": "EVID-000000000000000000000000"}
        )


def test_private_and_sealed_evidence_are_absent_from_public_serialization() -> None:
    public = _record(claim="buyer-safe evidence")
    private = _record(
        visibility=EvidenceVisibility.OPERATOR_PRIVATE,
        claim="OPERATOR_PRIVATE_MARKER",
    )
    sealed = _record(visibility=EvidenceVisibility.SEALED, claim="SEALED_MARKER")

    payload = serialize_public_evidence((private, public, sealed)).decode("utf-8")

    assert "buyer-safe evidence" in payload
    assert "OPERATOR_PRIVATE_MARKER" not in payload
    assert "SEALED_MARKER" not in payload
    assert private.evidence_id not in payload
    assert sealed.evidence_id not in payload


def test_public_serialization_is_deterministic_independent_of_input_order() -> None:
    first = _record(claim="first")
    second = _record(claim="second")

    left = serialize_public_evidence((first, second))
    right = serialize_public_evidence((second, first))

    assert left == right
    assert json.loads(left)["schema_version"] == "veritas.shared-evidence.v1"


def test_observed_evidence_cannot_be_promoted_to_maturity_gate() -> None:
    record = _record(outcome=EvidenceOutcome.OBSERVED)

    with pytest.raises(ValueError, match="must be classified"):
        maturity_gate_evidence_from_record(
            record,
            gate="verifier_qualification",
            qualification_policy_version="veritas-environment-maturity-v1",
        )


def test_classified_shared_evidence_projects_losslessly_to_maturity_gate() -> None:
    record = _record(outcome=EvidenceOutcome.FAIL)

    evidence = maturity_gate_evidence_from_record(
        record,
        gate="verifier_qualification",
        qualification_policy_version="veritas-environment-maturity-v1",
    )

    assert evidence.outcome == GateOutcome.FAIL
    assert evidence.evidence_id == record.evidence_id
    assert evidence.content_sha256 == record.evidence_content_sha256
    assert evidence.environment_content_sha256 == "a" * 64
    assert evidence.verifier_content_sha256 == "b" * 64
    assert evidence.provenance["shared_evidence_record_id"] == record.record_id


def test_policy_mismatch_cannot_be_silently_reinterpreted() -> None:
    record = _record()

    with pytest.raises(ValueError, match="policy version"):
        maturity_gate_evidence_from_record(
            record,
            gate="verifier_qualification",
            qualification_policy_version="different-policy-v2",
        )
