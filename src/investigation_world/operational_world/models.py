from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from random import Random
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RegionGroup(StrEnum):
    GLOBAL = "global"
    AFRICA = "africa"
    EUROPE = "europe"
    NORTH_AMERICA = "north_america"
    LATIN_AMERICA = "latin_america"
    MIDDLE_EAST = "middle_east"
    SOUTH_ASIA = "south_asia"
    EAST_ASIA_PACIFIC = "east_asia_pacific"


class CompanySizeBand(StrEnum):
    MICRO = "micro"
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"
    ENTERPRISE = "enterprise"


class IndustryFamily(StrEnum):
    GENERIC = "generic"
    MANUFACTURING = "manufacturing"
    WHOLESALE_DISTRIBUTION = "wholesale_distribution"
    RETAIL = "retail"
    LOGISTICS = "logistics"
    CONSTRUCTION = "construction"
    ENERGY = "energy"
    TELECOM = "telecom"
    TECHNOLOGY = "technology"
    PROFESSIONAL_SERVICES = "professional_services"
    FINANCIAL_SERVICES = "financial_services"


class ScenarioKind(StrEnum):
    DUPLICATE_INVOICE = "duplicate_invoice"
    APPROVAL_BYPASS = "approval_bypass"
    SHELL_VENDOR_CONFLICT = "shell_vendor_conflict"
    PHANTOM_RECEIPT = "phantom_receipt"
    SPLIT_PURCHASE_ORDERS = "split_purchase_orders"


class QuantileDistribution(BaseModel):
    """Compact empirical distribution used by the compiler.

    Values are stored as robust quantiles rather than assuming normality. Sampling is
    deterministic for a supplied Random instance and uses piecewise-linear interpolation.
    """

    model_config = ConfigDict(extra="forbid")

    minimum: float
    p10: float
    p50: float
    p90: float
    maximum: float
    unit: str = ""
    observation_count: int = Field(default=0, ge=0)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_order(self) -> "QuantileDistribution":
        values = [self.minimum, self.p10, self.p50, self.p90, self.maximum]
        if values != sorted(values):
            raise ValueError("quantile values must be monotonically non-decreasing")
        return self

    def sample(self, rng: Random) -> float:
        points = (
            (0.0, self.minimum),
            (0.1, self.p10),
            (0.5, self.p50),
            (0.9, self.p90),
            (1.0, self.maximum),
        )
        q = rng.random()
        for (q0, v0), (q1, v1) in zip(points, points[1:], strict=True):
            if q <= q1:
                if q1 == q0:
                    return v1
                ratio = (q - q0) / (q1 - q0)
                return v0 + ratio * (v1 - v0)
        return self.maximum


class WeightedCategory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weights: dict[str, float]
    observation_count: int = Field(default=0, ge=0)
    source_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_weights(self) -> "WeightedCategory":
        if not self.weights or any(value < 0 for value in self.weights.values()):
            raise ValueError("categorical weights must be non-empty and non-negative")
        if sum(self.weights.values()) <= 0:
            raise ValueError("categorical weights must sum to a positive value")
        return self

    def sample(self, rng: Random) -> str:
        total = sum(self.weights.values())
        target = rng.random() * total
        running = 0.0
        for key, weight in self.weights.items():
            running += weight
            if running >= target:
                return key
        return next(reversed(self.weights))


class CalibrationProfile(BaseModel):
    """Fused empirical priors used to compile a world.

    `state` distinguishes measured profiles from bootstrap priors so experiments cannot
    accidentally present estimated defaults as empirically measured statistics. `size_scope`
    makes the applicability of a source explicit: some evidence is genuinely size-conditioned
    (for example public-company finance), while legal-form or jurisdiction shape may be
    size-agnostic and should not be duplicated into fake size-specific measurements.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: str
    version: str = "1"
    region: RegionGroup = RegionGroup.GLOBAL
    industry: IndustryFamily = IndustryFamily.GENERIC
    size_band: CompanySizeBand = CompanySizeBand.MEDIUM
    size_scope: Literal["exact", "agnostic"] = "exact"
    source_ids: list[str] = Field(default_factory=list)
    distributions: dict[str, QuantileDistribution] = Field(default_factory=dict)
    categories: dict[str, WeightedCategory] = Field(default_factory=dict)
    empirical_observation_count: int = Field(default=0, ge=0)
    state: Literal["bootstrap_prior", "empirical", "hybrid"] = "bootstrap_prior"
    notes: list[str] = Field(default_factory=list)

    def applies_to_size(self, size_band: CompanySizeBand) -> bool:
        return self.size_scope == "agnostic" or self.size_band == size_band

    def sample(self, metric: str, rng: Random) -> float:
        if metric not in self.distributions:
            raise KeyError(f"missing calibration metric: {metric}")
        return self.distributions[metric].sample(rng)

    def sample_category(self, metric: str, rng: Random) -> str:
        if metric not in self.categories:
            raise KeyError(f"missing calibration category: {metric}")
        return self.categories[metric].sample(rng)


class OperationalWorldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed: int
    region: RegionGroup = RegionGroup.GLOBAL
    country_code: str | None = None
    industry: IndustryFamily = IndustryFamily.GENERIC
    size_band: CompanySizeBand = CompanySizeBand.MEDIUM
    employee_count: int | None = Field(default=None, ge=8, le=100_000)
    simulation_days: int = Field(default=120, ge=7, le=3650)
    scenario_types: list[ScenarioKind] = Field(default_factory=list)
    systems: list[str] = Field(
        default_factory=lambda: [
            "ERP",
            "WMS",
            "AP_WORKFLOW",
            "AUTH_SERVICE",
            "EMAIL",
            "LEDGER",
            "PROCESS",
            "TREASURY",
        ]
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationalEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entity_id: str
    entity_type: str
    name: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class OperationalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    timestamp: datetime
    actor_id: str | None = None
    object_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
    caused_by: list[str] = Field(default_factory=list)


class OperationalRecord(BaseModel):
    """Agent-visible projection of one or more canonical events."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    system: str
    record_type: str
    object_type: str
    object_id: str
    observed_at: datetime
    fields: dict[str, Any] = Field(default_factory=dict)
    related_object_ids: list[str] = Field(default_factory=list)
    source_event_ids: list[str] = Field(default_factory=list)


class GroundTruthFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    object_type: str
    object_id: str
    field_name: str
    expected_value: Any
    supporting_record_ids: list[str] = Field(default_factory=list)


class GroundTruthFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_id: str
    scenario_type: ScenarioKind
    summary: str
    affected_object_ids: list[str] = Field(default_factory=list)
    facts: list[GroundTruthFact] = Field(default_factory=list)
    causal_event_ids: list[str] = Field(default_factory=list)


class CompiledOperationalWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_id: str
    spec: OperationalWorldSpec
    calibration: CalibrationProfile
    entities: dict[str, OperationalEntity] = Field(default_factory=dict)
    events: list[OperationalEvent] = Field(default_factory=list)
    records: list[OperationalRecord] = Field(default_factory=list)
    ground_truth: list[GroundTruthFinding] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        """Safe world projection. Hidden scenario truth is intentionally excluded."""
        spec_payload = self.spec.model_dump(mode="json")
        # Scenario labels are evaluator-only. Exposing them would turn anomaly discovery
        # into classification from leaked compiler configuration.
        spec_payload.pop("scenario_types", None)
        return {
            "world_id": self.world_id,
            "spec": spec_payload,
            "calibration": {
                "profile_id": self.calibration.profile_id,
                "version": self.calibration.version,
                "region": self.calibration.region,
                "industry": self.calibration.industry,
                "size_band": self.calibration.size_band,
                "size_scope": self.calibration.size_scope,
                "source_ids": self.calibration.source_ids,
                "state": self.calibration.state,
            },
            "entities": {
                key: value.model_dump(mode="json") for key, value in self.entities.items()
            },
            "records": [record.model_dump(mode="json") for record in self.records],
            "metadata": self.metadata,
        }
