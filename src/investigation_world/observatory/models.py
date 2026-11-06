from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import DistributionSplit, stable_hash


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorldKind(StrEnum):
    INVESTIGATION = "investigation"
    OPERATIONAL = "operational"
    SOFTWARE = "software"
    RESEARCH = "research"
    OTHER = "other"


class ScenarioPool(StrEnum):
    ANCHOR = "anchor"
    ROTATION = "rotation"
    SEQUESTERED = "sequestered"


class WorldRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    world_id: str
    version: str
    kind: WorldKind = WorldKind.INVESTIGATION


class ScenarioRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    seed: int
    pool: ScenarioPool = ScenarioPool.ROTATION
    split: DistributionSplit | None = None
    task_id: str | None = None


class ModelSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    provider: str
    model_id: str
    snapshot: str = "unspecified"
    endpoint: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)


class HarnessSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    harness_id: str
    version: str
    config: dict[str, Any] = Field(default_factory=dict)


class VerifierSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    verifier_id: str
    version: str
    config: dict[str, Any] = Field(default_factory=dict)


class ExecutionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    time_limit_s: float | None = Field(default=None, gt=0.0)
    token_budget: int | None = Field(default=None, ge=1)
    tool_call_budget: int | None = Field(default=None, ge=1)
    cost_budget: float | None = Field(default=None, ge=0.0)
    parameters: dict[str, Any] = Field(default_factory=dict)


class LongitudinalCell(BaseModel):
    """One reproducible world x model x harness x seed x time-snapshot observation."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    world: WorldRef
    scenario: ScenarioRef
    model: ModelSpec
    harness: HarnessSpec
    verifier: VerifierSpec
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    time_snapshot: str
    cell_id: str = ""

    def identity_payload(self) -> dict[str, Any]:
        return {
            "world": self.world.model_dump(mode="json"),
            "scenario": self.scenario.model_dump(mode="json"),
            "model": self.model.model_dump(mode="json"),
            "harness": self.harness.model_dump(mode="json"),
            "verifier": self.verifier.model_dump(mode="json"),
            "execution": self.execution.model_dump(mode="json"),
            "time_snapshot": self.time_snapshot,
        }

    def longitudinal_payload(self) -> dict[str, Any]:
        model = self.model.model_dump(mode="json")
        model.pop("snapshot", None)
        return {
            "world": self.world.model_dump(mode="json"),
            "scenario": self.scenario.model_dump(mode="json"),
            "model": model,
            "harness": self.harness.model_dump(mode="json"),
            "verifier": self.verifier.model_dump(mode="json"),
            "execution": self.execution.model_dump(mode="json"),
        }

    @property
    def longitudinal_key(self) -> str:
        return f"LONG-{stable_hash(self.longitudinal_payload())[:20].upper()}"

    @model_validator(mode="after")
    def validate_cell_id(self) -> "LongitudinalCell":
        expected = f"CELL-{stable_hash(self.identity_payload())[:20].upper()}"
        if self.cell_id and self.cell_id != expected:
            raise ValueError("cell_id does not match the cell identity")
        object.__setattr__(self, "cell_id", expected)
        return self


class CapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    dimensions: dict[str, float] = Field(default_factory=dict)


class BehavioralFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    total_steps: int = Field(default=0, ge=0)
    total_cost: float = Field(default=0.0, ge=0.0)
    unique_event_types: int = Field(default=0, ge=0)
    event_counts: dict[str, int] = Field(default_factory=dict)
    tool_mix: dict[str, float] = Field(default_factory=dict)
    state_change_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    verification_events: int = Field(default=0, ge=0)
    recovery_events: int = Field(default=0, ge=0)
    failure_signals: int = Field(default=0, ge=0)
    mean_step_cost: float = Field(default=0.0, ge=0.0)


class RunProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    trace_id: str
    environment_version: str
    task_id: str
    taskset_version: str
    runtime_version: str
    harness_version: str


class CapabilityRun(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    run_id: str = ""
    cell: LongitudinalCell
    provenance: RunProvenance
    capability: CapabilityProfile
    behavior: BehavioralFingerprint
    total_reward: float = 0.0
    total_cost: float = Field(default=0.0, ge=0.0)
    termination_reason: str = "unknown"
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_run_id(self) -> "CapabilityRun":
        expected = f"RUN-{stable_hash([self.cell.cell_id, self.provenance.trace_id])[:20].upper()}"
        if self.run_id and self.run_id != expected:
            raise ValueError("run_id does not match cell and trace identity")
        object.__setattr__(self, "run_id", expected)
        return self


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    experiment_id: str = ""
    name: str
    hypothesis: str | None = None
    cell_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_experiment_id(self) -> "ExperimentSpec":
        expected = f"EXP-{stable_hash([self.name, sorted(self.cell_ids), self.metadata])[:20].upper()}"
        if self.experiment_id and self.experiment_id != expected:
            raise ValueError("experiment_id does not match experiment identity")
        object.__setattr__(self, "experiment_id", expected)
        return self


class DimensionDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    baseline: float
    current: float
    delta: float
    relative_delta: float | None = None


class CapabilityDriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    longitudinal_key: str
    baseline_run_id: str
    current_run_id: str
    baseline_snapshot: str
    current_snapshot: str
    reward_delta: float
    cost_delta: float
    step_delta: int
    dimensions: dict[str, DimensionDelta] = Field(default_factory=dict)
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


class CellMatrixSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    worlds: list[WorldRef] = Field(min_length=1)
    scenarios: list[ScenarioRef] = Field(min_length=1)
    models: list[ModelSpec] = Field(min_length=1)
    harnesses: list[HarnessSpec] = Field(min_length=1)
    verifiers: list[VerifierSpec] = Field(min_length=1)
    executions: list[ExecutionSpec] = Field(
        default_factory=lambda: [ExecutionSpec()],
        min_length=1,
    )
    time_snapshots: list[str] = Field(min_length=1)
