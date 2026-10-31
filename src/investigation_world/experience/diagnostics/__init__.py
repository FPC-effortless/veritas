"""Evidence-bounded diagnostic producers, not causal or training qualification."""

from .interventions import (
    CapabilityFailureCandidate,
    InterventionDiagnostic,
    diagnose_counterfactual,
    intervention_failure_families,
)
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
    "CapabilityFailureCandidate",
    "InterventionDiagnostic",
    "diagnose_counterfactual",
    "intervention_failure_families",
    "DiagnosticObservation",
    "DiagnosticReport",
    "FailureFamilyCandidate",
    "buyer_safe_diagnostics",
    "diagnose_experience",
    "failure_family_candidates",
    "reference_action_divergence",
]
