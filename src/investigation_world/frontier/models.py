from __future__ import annotations

import hashlib
import json
import math
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CALCULATION_VERSION = "frontier-qualification-v2"


def stable_content_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class GateStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class FrontierStatus(StrEnum):
    FRONTIER_QUALIFIED = "FRONTIER_QUALIFIED"
    NOT_YET_FRONTIER_QUALIFIED = "NOT_YET_FRONTIER_QUALIFIED"


class FrontierQualificationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1"
    calculation_version: str = CALCULATION_VERSION
    policy_id: str = ""

    # "Frontier" is a policy declaration, not an implementation constant.
    strong_model_tiers: tuple[str, ...] = ("strong", "frontier")
    tier_order: tuple[str, ...] = ("weak", "medium", "strong", "frontier")

    non_saturation_floor: float = Field(default=0.10, ge=0.0, lt=1.0)
    non_saturation_ceiling: float = Field(default=0.90, gt=0.0, le=1.0)
    capability_separation_min_effect: float = Field(default=0.15, ge=0.0, le=1.0)
    capability_separation_min_confidence_gap: float = Field(default=0.0, ge=-1.0, le=1.0)
    harness_sensitivity_min_effect: float = Field(default=0.05, ge=0.0, le=1.0)

    minimum_failure_categories: int = Field(default=3, ge=1)
    maximum_failure_category_share: float = Field(default=0.80, gt=0.0, le=1.0)
    parser_failure_labels: tuple[str, ...] = ("parser", "parse", "structured_output_parse")
    infrastructure_failure_labels: tuple[str, ...] = (
        "infrastructure",
        "infra",
        "runtime",
        "transport",
    )

    minimum_effective_diversity: float = Field(default=4.0, ge=1.0)
    maximum_largest_cluster_share: float = Field(default=0.50, gt=0.0, le=1.0)
    maximum_near_duplicate_share: float = Field(default=0.30, ge=0.0, le=1.0)
    minimum_source_normalized_entropy: float = Field(default=0.50, ge=0.0, le=1.0)
    maximum_dimension_concentration: float = Field(default=0.80, gt=0.0, le=1.0)
    minimum_required_diversity_dimensions: int = Field(default=4, ge=1, le=8)

    required_generalization_evidence: tuple[str, ...] = (
        "random_held_out",
        "source_disjoint",
    )
    required_training_transfer_kinds: tuple[str, ...] = ("within_family_transfer",)
    require_training_on_strong_tier: bool = True
    require_control_benchmark: bool = True

    @model_validator(mode="after")
    def validate_and_set_id(self) -> "FrontierQualificationPolicy":
        if self.non_saturation_floor >= self.non_saturation_ceiling:
            raise ValueError("non_saturation_floor must be lower than non_saturation_ceiling")
        if not self.strong_model_tiers:
            raise ValueError("strong_model_tiers must be declared explicitly")
        allowed_generalization = {
            "random_held_out", "source_disjoint", "grammar_disjoint",
            "component_disjoint", "compositional_ood_transfer",
        }
        unknown_generalization = set(self.required_generalization_evidence) - allowed_generalization
        if unknown_generalization:
            raise ValueError(
                f"unknown generalization evidence kinds: {sorted(unknown_generalization)}"
            )
        allowed_training = {
            "within_family_transfer", "cross_family_transfer", "external_benchmark_transfer"
        }
        unknown_training = set(self.required_training_transfer_kinds) - allowed_training
        if unknown_training:
            raise ValueError(f"unknown training transfer kinds: {sorted(unknown_training)}")
        payload = self.model_dump(mode="json", exclude={"policy_id"})
        expected = f"FRPOL-{stable_content_hash(payload)[:24].upper()}"
        if self.policy_id and self.policy_id != expected:
            raise ValueError("policy_id does not match immutable policy contents")
        object.__setattr__(self, "policy_id", expected)
        return self


class FrontierCalibrationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1"
    calculation_version: str = CALCULATION_VERSION
    observation_id: str = ""

    benchmark_name: str | None = None
    benchmark_version: str | None = None
    candidate_id: str | None = None
    panel_id: str | None = None
    qualification_report_id: str | None = None
    evidence_manifest_id: str | None = None
    release_manifest_id: str | None = None

    model_identity: str
    model_snapshot: str | None = None
    harness_identity: str
    tier: str
    metric_name: str = "score"
    score: float = Field(ge=0.0, le=1.0)
    sample_size: int | None = Field(default=None, ge=1)
    successes: int | None = Field(default=None, ge=0)
    score_stddev: float | None = Field(default=None, ge=0.0)
    seed: int | str | None = None
    configuration: dict[str, Any] = Field(default_factory=dict)
    comparison_group_id: str | None = None
    failure_mode_counts: dict[str, int] = Field(default_factory=dict)
    input_artifact_hash: str | None = None

    @model_validator(mode="after")
    def validate_and_set_id(self) -> "FrontierCalibrationObservation":
        if self.successes is not None:
            if self.sample_size is None:
                raise ValueError("sample_size is required when successes is supplied")
            if self.successes > self.sample_size:
                raise ValueError("successes cannot exceed sample_size")
        if any(v < 0 for v in self.failure_mode_counts.values()):
            raise ValueError("failure_mode_counts cannot contain negative counts")
        payload = self.model_dump(mode="json", exclude={"observation_id"})
        expected = f"FROBS-{stable_content_hash(payload)[:24].upper()}"
        if self.observation_id and self.observation_id != expected:
            raise ValueError("observation_id does not match immutable contents")
        object.__setattr__(self, "observation_id", expected)
        return self


class PairedCapabilityComparison(BaseModel):
    """Buyer-safe paired weak/strong outcome aggregate for the same task panel.

    The four cells are sufficient to estimate the paired accuracy difference without
    publishing scenario IDs, labels, or predictions. Re-running the same deterministic
    panel does not increase this object's sample size.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1"
    calculation_version: str = CALCULATION_VERSION
    comparison_id: str = ""

    benchmark_name: str | None = None
    benchmark_version: str | None = None
    candidate_id: str | None = None
    panel_id: str | None = None

    weak_observation_id: str
    strong_observation_id: str
    both_correct: int = Field(ge=0)
    weak_only_correct: int = Field(ge=0)
    strong_only_correct: int = Field(ge=0)
    both_wrong: int = Field(ge=0)
    input_artifact_hashes: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_and_set_id(self) -> "PairedCapabilityComparison":
        total = (
            self.both_correct
            + self.weak_only_correct
            + self.strong_only_correct
            + self.both_wrong
        )
        if total <= 0:
            raise ValueError("paired capability comparison requires at least one paired case")
        if self.weak_observation_id == self.strong_observation_id:
            raise ValueError("weak and strong observation IDs must differ")
        payload = self.model_dump(mode="json", exclude={"comparison_id"})
        expected = f"FRPAIR-{stable_content_hash(payload)[:24].upper()}"
        if self.comparison_id and self.comparison_id != expected:
            raise ValueError("comparison_id does not match immutable contents")
        object.__setattr__(self, "comparison_id", expected)
        return self


class DiversityDimensionMetric(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    available: bool
    category_count: int = 0
    entropy: float = 0.0
    normalized_entropy: float = 0.0
    effective_number: float = 0.0
    largest_category_share: float = 0.0


class TaskDiversityReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1"
    calculation_version: str = CALCULATION_VERSION
    report_id: str = ""

    benchmark_name: str | None = None
    benchmark_version: str | None = None
    candidate_id: str | None = None
    panel_id: str | None = None
    qualification_report_id: str | None = None
    evidence_manifest_id: str | None = None
    release_manifest_id: str | None = None
    input_artifact_hashes: dict[str, str] = Field(default_factory=dict)

    raw_task_count: int = Field(ge=0)
    effective_diversity: float = Field(ge=0.0)
    effective_diversity_method: str
    cluster_count: int = Field(ge=0)
    largest_cluster_share: float = Field(ge=0.0, le=1.0)
    source_concentration: float = Field(ge=0.0, le=1.0)
    duplicate_share: float = Field(ge=0.0, le=1.0)
    near_duplicate_share: float = Field(ge=0.0, le=1.0)
    near_duplicate_component_sizes: list[int] = Field(default_factory=list)
    dimensions: dict[str, DiversityDimensionMetric] = Field(default_factory=dict)
    split_overlap: dict[str, Any] = Field(default_factory=dict)
    compositional_disjointness: dict[str, Any] = Field(default_factory=dict)
    semantic_cluster_backend: str = "lexical-structural-simhash-v1"

    @model_validator(mode="after")
    def validate_and_set_id(self) -> "TaskDiversityReport":
        payload = self.model_dump(mode="json", exclude={"report_id"})
        expected = f"FRDIV-{stable_content_hash(payload)[:24].upper()}"
        if self.report_id and self.report_id != expected:
            raise ValueError("report_id does not match immutable report contents")
        object.__setattr__(self, "report_id", expected)
        return self


class FrontierUtilityGateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    status: GateStatus
    observed: Any = None
    required: Any = None
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)


GeneralizationKind = Literal[
    "random_held_out",
    "source_disjoint",
    "grammar_disjoint",
    "component_disjoint",
    "compositional_ood_transfer",
]


class GeneralizationEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    random_held_out: GateStatus = GateStatus.UNKNOWN
    source_disjoint: GateStatus = GateStatus.UNKNOWN
    grammar_disjoint: GateStatus = GateStatus.UNKNOWN
    component_disjoint: GateStatus = GateStatus.UNKNOWN
    compositional_ood_transfer: GateStatus = GateStatus.UNKNOWN
    evidence_ids: dict[str, list[str]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)


class TrainingValueEvidenceSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    within_family_transfer: GateStatus = GateStatus.UNKNOWN
    cross_family_transfer: GateStatus = GateStatus.UNKNOWN
    external_benchmark_transfer: GateStatus = GateStatus.UNKNOWN
    control_benchmark_preservation: GateStatus = GateStatus.UNKNOWN
    model_identity: str | None = None
    model_tier: str | None = None
    evidence_ids: dict[str, list[str]] = Field(default_factory=dict)
    notes: dict[str, str] = Field(default_factory=dict)


class FrontierQualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: str = "1"
    calculation_version: str = CALCULATION_VERSION
    report_id: str = ""

    benchmark_name: str | None = None
    benchmark_version: str | None = None
    candidate_id: str | None = None
    panel_id: str | None = None
    qualification_report_id: str | None = None
    evidence_manifest_id: str | None = None
    release_manifest_id: str | None = None
    input_artifact_hashes: dict[str, str] = Field(default_factory=dict)

    scientific_qualification_observed: bool
    scientifically_qualified: bool | None = None
    scientific_qualification_detail: str

    policy: FrontierQualificationPolicy
    gates: list[FrontierUtilityGateResult]
    generalization: GeneralizationEvidenceSummary
    training_value: TrainingValueEvidenceSummary
    frontier_status: FrontierStatus
    frontier_qualified: bool
    buyer_safe: bool = True

    @model_validator(mode="after")
    def validate_and_set_id(self) -> "FrontierQualificationReport":
        # This layer may only consume scientific qualification; it cannot upgrade/downgrade it.
        if self.frontier_qualified:
            if self.scientifically_qualified is not True:
                raise ValueError("frontier qualification requires an explicit scientific PASS")
            if any(g.status is not GateStatus.PASS for g in self.gates):
                raise ValueError("frontier qualification requires every utility gate to PASS")
        if (
            self.frontier_status == FrontierStatus.FRONTIER_QUALIFIED
            and not self.frontier_qualified
        ):
            raise ValueError("frontier_status and frontier_qualified disagree")
        if (
            self.frontier_status == FrontierStatus.NOT_YET_FRONTIER_QUALIFIED
            and self.frontier_qualified
        ):
            raise ValueError("frontier_status and frontier_qualified disagree")
        payload = self.model_dump(mode="json", exclude={"report_id"})
        expected = f"FRQ-{stable_content_hash(payload)[:24].upper()}"
        if self.report_id and self.report_id != expected:
            raise ValueError("report_id does not match immutable report contents")
        object.__setattr__(self, "report_id", expected)
        return self


def entropy_metrics(counts: dict[str, int]) -> DiversityDimensionMetric:
    positive = [count for count in counts.values() if count > 0]
    total = sum(positive)
    if total == 0:
        return DiversityDimensionMetric(available=False)
    probabilities = [count / total for count in positive]
    entropy = -sum(p * math.log(p) for p in probabilities)
    category_count = len(positive)
    normalized = 0.0 if category_count == 1 else entropy / math.log(category_count)
    return DiversityDimensionMetric(
        available=True,
        category_count=category_count,
        entropy=round(entropy, 8),
        normalized_entropy=round(normalized, 8),
        effective_number=round(math.exp(entropy), 8),
        largest_category_share=round(max(probabilities), 8),
    )
