"""Executable Gold-10 flagship pilot bound to the frozen CASE-001 manifest."""

from .models import (
    EpistemicClaim,
    EpistemicClaimKind,
    EvidenceRecord,
    Gold10Score,
    Gold10Submission,
    Gold10Task,
    InstitutionalFinding,
    PilotContract,
)
from .quality import build_pilot_gate_report
from .registry import Gold10PilotError, build_task, build_taskset, load_pilot_contract
from .replay import (
    build_reference_experiences,
    reference_submission,
    traceable_experience,
)
from .verifier import evidence_target_statement, score_submission, score_submission_json

__all__ = [
    "EpistemicClaim",
    "EpistemicClaimKind",
    "EvidenceRecord",
    "Gold10PilotError",
    "Gold10Score",
    "Gold10Submission",
    "Gold10Task",
    "InstitutionalFinding",
    "PilotContract",
    "build_pilot_gate_report",
    "build_reference_experiences",
    "build_task",
    "build_taskset",
    "evidence_target_statement",
    "load_pilot_contract",
    "reference_submission",
    "score_submission",
    "score_submission_json",
    "traceable_experience",
]
