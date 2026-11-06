from __future__ import annotations

from investigation_world.evidence.models import EvidenceOutcome, EvidenceRecord
from investigation_world.qualification.maturity import GateOutcome, MaturityGateEvidence


def maturity_gate_evidence_from_record(
    record: EvidenceRecord,
    *,
    gate: str,
    qualification_policy_version: str,
) -> MaturityGateEvidence:
    """Project one shared evidence record into the existing maturity gate envelope.

    The adapter is intentionally one-way. Maturity remains a view over evidence rather than a second
    evidence authority. ``OBSERVED`` records cannot satisfy or fail a gate until a subsystem has
    classified them under an explicit policy.
    """

    if record.outcome == EvidenceOutcome.OBSERVED:
        raise ValueError("observational evidence must be classified before maturity projection")

    environment_subjects = [item for item in record.subjects if item.kind == "environment"]
    verifier_subjects = [item for item in record.subjects if item.kind == "verifier"]
    if len(environment_subjects) != 1:
        raise ValueError("maturity evidence requires exactly one environment subject")
    if len(verifier_subjects) != 1:
        raise ValueError("maturity evidence requires exactly one verifier subject")

    if record.policy and record.policy.policy_version != qualification_policy_version:
        raise ValueError("shared evidence policy version does not match maturity policy version")

    outcome = GateOutcome(record.outcome.value)
    environment = environment_subjects[0]
    verifier = verifier_subjects[0]
    provenance = {
        "shared_evidence_record_id": record.record_id,
        "shared_evidence_type": record.evidence_type,
        "producer_id": record.producer.producer_id,
        "producer_version": record.producer.producer_version,
        "source_provenance": record.provenance,
    }
    return MaturityGateEvidence(
        gate=gate,
        outcome=outcome,
        evidence_id=record.evidence_id,
        content_sha256=record.evidence_content_sha256,
        environment_content_sha256=environment.content_sha256,
        verifier_content_sha256=verifier.content_sha256,
        qualification_policy_version=qualification_policy_version,
        observed_at=record.observed_at,
        provenance=provenance,
        detail=record.claim,
    )
