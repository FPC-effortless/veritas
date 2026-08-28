"""Observatory diagnostics over canonical TrajectoryV2 records."""

from .engine import (
    build_trajectory_diagnostics,
    capability_conditioned_failure_profiles,
    compare_same_harness_different_model,
    compare_same_model_different_harness,
    compare_same_trajectory_verifier_versions,
    diagnose_failure,
    failure_category_distribution,
)
from .models import (
    AttributionEvidence,
    CapabilityFailureProfile,
    ComparisonKind,
    ComparisonView,
    ControlledRunComparison,
    FailureAttribution,
    FailureCategoryDistribution,
    TrajectoryDiagnosticInput,
    TrajectoryDiagnosticsReport,
    VerifierVersionComparison,
)

__all__ = [
    "AttributionEvidence",
    "CapabilityFailureProfile",
    "ComparisonKind",
    "ComparisonView",
    "ControlledRunComparison",
    "FailureAttribution",
    "FailureCategoryDistribution",
    "TrajectoryDiagnosticInput",
    "TrajectoryDiagnosticsReport",
    "VerifierVersionComparison",
    "build_trajectory_diagnostics",
    "capability_conditioned_failure_profiles",
    "compare_same_harness_different_model",
    "compare_same_model_different_harness",
    "compare_same_trajectory_verifier_versions",
    "diagnose_failure",
    "failure_category_distribution",
]
