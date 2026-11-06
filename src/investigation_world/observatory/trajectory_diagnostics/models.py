from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.observatory.execution import ProviderSessionSummary
from investigation_world.observatory.models import CapabilityRun
from investigation_world.trajectory import FailureCategory, ReverificationRecord, TrajectoryV2


class DiagnosticModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttributionEvidence(DiagnosticModel):
    signal: str
    category_probabilities: dict[str, float]
    qualification: str
    direct: bool = False


class FailureAttribution(DiagnosticModel):
    trajectory_id: str
    primary_category: FailureCategory = FailureCategory.UNKNOWN
    category_probabilities: dict[str, float]
    evidence: tuple[AttributionEvidence, ...] = ()
    ambiguous: bool = True
    qualified: bool = True

    @model_validator(mode="after")
    def validate_probabilities(self) -> "FailureAttribution":
        expected = {category.value for category in FailureCategory}
        if set(self.category_probabilities) != expected:
            raise ValueError("failure attribution must cover the complete failure taxonomy")
        total = sum(self.category_probabilities.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError("failure attribution probabilities must sum to one")
        if any(value < 0.0 or value > 1.0 for value in self.category_probabilities.values()):
            raise ValueError("failure attribution probabilities must stay in [0, 1]")
        if self.primary_category == FailureCategory.UNKNOWN and not self.ambiguous:
            raise ValueError("UNKNOWN attribution must remain marked ambiguous")
        return self


class TrajectoryDiagnosticInput(DiagnosticModel):
    trajectory: TrajectoryV2
    capability_run: CapabilityRun | None = None
    provider_session: ProviderSessionSummary | None = None

    @model_validator(mode="after")
    def validate_observatory_binding(self) -> "TrajectoryDiagnosticInput":
        trajectory = self.trajectory
        run = self.capability_run
        if run is not None:
            checks = (
                (trajectory.task.task_id, run.cell.scenario.task_id or run.provenance.task_id, "task"),
                (trajectory.world.world_id, run.cell.world.world_id, "world"),
                (trajectory.model.provider, run.cell.model.provider, "model provider"),
                (trajectory.model.model_id, run.cell.model.model_id, "model id"),
                (trajectory.model.snapshot, run.cell.model.snapshot, "model snapshot"),
                (trajectory.harness.harness_id, run.cell.harness.harness_id, "harness id"),
                (trajectory.harness.version, run.cell.harness.version, "harness version"),
                (trajectory.verifier.verifier_id, run.cell.verifier.verifier_id, "verifier id"),
                (trajectory.verifier.version, run.cell.verifier.version, "verifier version"),
            )
            for canonical, observatory, label in checks:
                if canonical is not None and canonical != observatory:
                    raise ValueError(f"trajectory {label} does not match CapabilityRun")

        provider = self.provider_session
        if provider is not None:
            checks = (
                (trajectory.model.provider, provider.provider_id, "provider"),
                (trajectory.model.model_id, provider.model_id, "model id"),
                (trajectory.model.snapshot, provider.model_snapshot, "model snapshot"),
            )
            for canonical, session, label in checks:
                if canonical is not None and canonical != session:
                    raise ValueError(f"trajectory {label} does not match ProviderSessionSummary")
        return self


class ComparisonKind(StrEnum):
    SAME_MODEL_DIFFERENT_HARNESS = "same_model_different_harness"
    SAME_HARNESS_DIFFERENT_MODEL = "same_harness_different_model"


class ControlledRunComparison(DiagnosticModel):
    comparison_id: str
    kind: ComparisonKind
    control_key: str
    left_trajectory_id: str
    right_trajectory_id: str
    left_variant: str
    right_variant: str
    left_reward: float
    right_reward: float
    reward_delta: float
    left_failure: FailureCategory
    right_failure: FailureCategory
    qualification: str


class ComparisonView(DiagnosticModel):
    kind: ComparisonKind
    rows: tuple[ControlledRunComparison, ...] = ()


class VerifierVersionComparison(DiagnosticModel):
    comparison_id: str
    trajectory_id: str
    verifier_id: str
    baseline_version: str
    candidate_version: str
    baseline_source: Literal["original", "reverification"]
    candidate_source: Literal["original", "reverification"]
    baseline_reward: float
    candidate_reward: float
    reward_delta: float
    component_deltas: dict[str, float] = Field(default_factory=dict)
    qualification: str


class FailureCategoryDistribution(DiagnosticModel):
    trajectory_count: int = Field(ge=0)
    expected_counts: dict[str, float]
    expected_rates: dict[str, float]
    primary_counts: dict[str, int]
    ambiguous_count: int = Field(ge=0)


class CapabilityFailureProfile(DiagnosticModel):
    capability_tag: str
    distribution: FailureCategoryDistribution


class TrajectoryDiagnosticsReport(DiagnosticModel):
    attributions: tuple[FailureAttribution, ...]
    same_model_different_harness: ComparisonView
    same_harness_different_model: ComparisonView
    verifier_version_comparisons: tuple[VerifierVersionComparison, ...]
    failure_distribution: FailureCategoryDistribution
    capability_failure_profiles: tuple[CapabilityFailureProfile, ...]
    consumed_reverification_record_ids: tuple[str, ...]


DiagnosticInput = TrajectoryV2 | TrajectoryDiagnosticInput
ReverificationInput = ReverificationRecord
