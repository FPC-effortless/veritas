"""Offline, evidence-bound trajectory reverification."""

from investigation_world.trajectory.reverify.engine import (
    attach_operational_replay_evidence,
    reverify_trajectory,
)
from investigation_world.trajectory.reverify.models import (
    REPLAY_EVIDENCE_PRIVATE_KEY,
    REPLAY_EVIDENCE_REFERENCE_TYPE,
    REPLAY_EVIDENCE_SCHEMA,
    REVERIFICATION_ENGINE_ID,
    REVERIFICATION_ENGINE_VERSION,
    OperationalReplayEvidence,
    ReverificationOutcome,
    ReverificationStatus,
)
from investigation_world.trajectory.reverify.operational import (
    AuthorizedVerifierRegistry,
    OperationalEvaluatorInput,
    OperationalVerifierBinding,
    current_operational_verifier_binding,
    evaluator_input_from_evidence,
)

__all__ = [
    "REPLAY_EVIDENCE_PRIVATE_KEY",
    "REPLAY_EVIDENCE_REFERENCE_TYPE",
    "REPLAY_EVIDENCE_SCHEMA",
    "REVERIFICATION_ENGINE_ID",
    "REVERIFICATION_ENGINE_VERSION",
    "AuthorizedVerifierRegistry",
    "OperationalEvaluatorInput",
    "OperationalReplayEvidence",
    "OperationalVerifierBinding",
    "ReverificationOutcome",
    "ReverificationStatus",
    "attach_operational_replay_evidence",
    "current_operational_verifier_binding",
    "evaluator_input_from_evidence",
    "reverify_trajectory",
]
