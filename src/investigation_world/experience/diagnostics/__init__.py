"""Evidence-bounded diagnostic producers, not causal or training qualification."""

from .producers import (
    DiagnosticObservation,
    DiagnosticReport,
    FailureFamilyCandidate,
    buyer_safe_diagnostics,
    diagnose_experience,
    failure_family_candidates,
    reference_action_divergence,
)

__all__ = [
    "DiagnosticObservation",
    "DiagnosticReport",
    "FailureFamilyCandidate",
    "buyer_safe_diagnostics",
    "diagnose_experience",
    "failure_family_candidates",
    "reference_action_divergence",
]
