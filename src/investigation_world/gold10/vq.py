from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from investigation_world.evidence import (
    EvidenceArtifactRef,
    EvidenceOutcome,
    EvidenceProducerRef,
    EvidenceRecord,
    EvidenceSubjectRef,
    EvidenceVisibility,
)
from investigation_world.qualification.quality_scorecard import (
    QualityScorecardContext,
    build_environment_quality_scorecard,
)
from investigation_world.trajectory import canonical_hash

from .models import PilotContract

_OBSERVED_AT = datetime(2026, 9, 4, tzinfo=timezone.utc)
_PRODUCER_VERSION = "1.0"


def _producer() -> EvidenceProducerRef:
    payload = {
        "producer_id": "veritas.gold10.pilot-gates",
        "producer_version": _PRODUCER_VERSION,
    }
    return EvidenceProducerRef(
        producer_id=payload["producer_id"],
        producer_version=payload["producer_version"],
        content_sha256=canonical_hash(payload),
    )


def _observed_evidence(
    *,
    evidence_type: str,
    claim: str,
    subject: EvidenceSubjectRef,
    artifact_id: str,
    payload: dict[str, Any],
) -> EvidenceRecord:
    payload_sha256 = canonical_hash(payload)
    return EvidenceRecord(
        evidence_type=evidence_type,
        outcome=EvidenceOutcome.OBSERVED,
        visibility=EvidenceVisibility.PUBLIC,
        claim=claim,
        subjects=(subject,),
        producer=_producer(),
        artifacts=(
            EvidenceArtifactRef(
                artifact_id=artifact_id,
                role="pilot_gate_observation",
                content_sha256=payload_sha256,
                media_type="application/json",
            ),
        ),
        observed_at=_OBSERVED_AT,
        provenance={
            "source": "ROADMAP-001 executable pilot gate report",
            "authority_ceiling": "observation_only_not_qualification",
        },
    )


def build_canonical_vq_scorecard(
    *,
    contract: PilotContract,
    taskset_rebuild_sha256: str,
    coverage: dict[str, Any],
    exploit: dict[str, Any],
    reference: dict[str, Any],
) -> dict[str, Any]:
    """Project Gold-10 pilot observations into the canonical VQ scorecard.

    ROADMAP-001 is not a qualification authority. Evidence produced here is therefore
    OBSERVED rather than PASS, so canonical dimensions remain UNKNOWN until an
    authorized qualification lane supplies qualifying evidence.
    """

    environment = EvidenceSubjectRef(
        kind="environment",
        subject_id=contract.world_id,
        version=contract.world_version,
        content_sha256=taskset_rebuild_sha256,
    )
    verifier_payload = {
        "verifier_id": contract.verifier_id,
        "verifier_version": contract.verifier_version,
        "unqualified_reward_ceiling": contract.unqualified_reward_ceiling,
        "exploit_policy": exploit["policy"],
        "exploit_probe_pass": {
            name: bool(result["passed"])
            for name, result in exploit["probes"].items()
        },
    }
    verifier = EvidenceSubjectRef(
        kind="verifier",
        subject_id=contract.verifier_id,
        version=contract.verifier_version,
        content_sha256=canonical_hash(verifier_payload),
    )
    context = QualityScorecardContext(
        environment=environment,
        verifier=verifier,
        portable_contract=None,
    )

    evidence = (
        _observed_evidence(
            evidence_type="qualification.reward_hack_resistance",
            claim="Gold-10 pilot exploit probes were executed deterministically.",
            subject=verifier,
            artifact_id="gold10-exploit-shortcut-report",
            payload=exploit,
        ),
        _observed_evidence(
            evidence_type="qualification.reset_determinism",
            claim="Gold-10 taskset rebuild identity is deterministic for identical inputs.",
            subject=environment,
            artifact_id="gold10-taskset-rebuild-identity",
            payload={"taskset_rebuild_sha256": taskset_rebuild_sha256},
        ),
        _observed_evidence(
            evidence_type="qualification.task_ambiguity",
            claim="Gold-10 preserves an explicit calibration case and uncertainty surface.",
            subject=environment,
            artifact_id="gold10-calibration-coverage",
            payload={
                "calibration_cases": coverage["calibration_cases"],
                "task_structure": coverage["task_structure"],
            },
        ),
        _observed_evidence(
            evidence_type="qualification.structural_diversity",
            claim="Gold-10 pilot structural coverage was measured without scalar promotion.",
            subject=environment,
            artifact_id="gold10-coverage-report",
            payload=coverage,
        ),
        _observed_evidence(
            evidence_type="qualification.reproducibility",
            claim="Gold-10 reference submissions and taskset reconstruction are reproducible.",
            subject=environment,
            artifact_id="gold10-reference-solvability",
            payload=reference,
        ),
        _observed_evidence(
            evidence_type="qualification.provenance_completeness",
            claim="Gold-10 executable tasks remain bound to the frozen CASE-001 manifest.",
            subject=environment,
            artifact_id="gold10-manifest-binding",
            payload={
                "taskset_rebuild_sha256": taskset_rebuild_sha256,
                "pilot_id": contract.pilot_id,
            },
        ),
    )
    scorecard = build_environment_quality_scorecard(
        context=context,
        evidence=evidence,
    )
    return {
        "scorecard": scorecard.model_dump(mode="json"),
        "failed_dimensions": [item.value for item in scorecard.failed_dimensions],
        "unknown_dimensions": [item.value for item in scorecard.unknown_dimensions],
        "complete": scorecard.complete,
        "evidence_outcome_ceiling": "OBSERVED",
        "qualification_authority": {
            "scientific": False,
            "frontier": False,
            "training_value": False,
            "commercial": False,
        },
        "interpretation": (
            "This is the canonical multidimensional VQ projection. ROADMAP-001 evidence "
            "is observational only, so missing or unqualified dimensions remain UNKNOWN."
        ),
    }
