from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.companyworld.models import CompanySystem
from investigation_world.companyworld.sequential_models import (
    SequentialCompanyWorldEpisode,
    SequentialCompanyWorldVerificationResult,
)


class DynamicFailureMode(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    PARTIAL = "PARTIAL"


class DynamicSystemFailureWindow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system: CompanySystem
    start_tick: int = Field(ge=0)
    end_tick: int = Field(ge=0)
    mode: DynamicFailureMode

    def active(self, tick: int) -> bool:
        return self.start_tick <= tick <= self.end_tick


class DynamicCaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    sequential: SequentialCompanyWorldEpisode
    deadline_tick: int = Field(ge=1)
    priority_weight: float = Field(gt=0)
    shared_resource: str
    irreversible_remediation: bool = False
    role_roster: list[str]
    late_penalty: float = Field(default=0.15, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "sequential": self.sequential.public_payload(),
            "deadline_tick": self.deadline_tick,
            "priority_weight": self.priority_weight,
            "shared_resource": self.shared_resource,
            "irreversible_remediation": self.irreversible_remediation,
            "role_roster": list(self.role_roster),
            "late_penalty": self.late_penalty,
            "metadata": self.metadata,
        }


class DynamicCaseOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    approval_outcome: str = "APPROVED"
    failure_windows: list[DynamicSystemFailureWindow] = Field(default_factory=list)


class DynamicScenarioTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    world_id: str
    objective: str
    max_ticks: int = Field(default=6, ge=1)
    total_budget: int = Field(default=120, ge=1)
    shared_resource_capacities: dict[str, int]
    system_failure_risk: dict[str, float]
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DynamicScenarioOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    case_oracles: list[DynamicCaseOracle]
    coupled_deadline_threshold: int = Field(default=2, ge=1)
    coupled_deadline_penalty: float = Field(default=0.15, ge=0.0, le=1.0)


class DynamicCompanyWorldScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str
    world_id: str
    task: DynamicScenarioTask
    cases: list[DynamicCaseSpec]
    oracle: DynamicScenarioOracle
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "world_id": self.world_id,
            "task": self.task.model_dump(mode="json"),
            "cases": [case.public_payload() for case in self.cases],
            "metadata": self.metadata,
        }


class DynamicToolObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    tick: int
    system: CompanySystem
    ok: bool
    degraded: bool = False
    error: str = ""
    retry_after_tick: int | None = None
    records: list[dict[str, Any]] = Field(default_factory=list)


class DynamicHandoff(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    tick: int
    from_role: str
    to_role: str
    applied: bool
    reason: str = ""


class DynamicResourceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    tick: int
    resource: str
    event: str
    applied: bool
    reason: str = ""


class DynamicConsequenceEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str | None = None
    tick: int
    event: str
    penalty: float = Field(ge=0.0)
    detail: str = ""


class DynamicCaseVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    case_id: str
    sequential: SequentialCompanyWorldVerificationResult
    deadline_met: bool
    approval_recovered: bool


class DynamicCompanyWorldVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    weighted_case_reward: float = 0.0
    case_success_rate: float = 0.0
    deadline_score: float = 0.0
    resource_discipline: float = 0.0
    uncertainty_recovery: float = 0.0
    budget_efficiency: float = 0.0
    deadline_misses: int = 0
    resource_conflicts: int = 0
    tool_failures_observed: int = 0
    handoffs: int = 0
    irreversible_compensation_attempts: int = 0
    coupled_consequence_applied: bool = False
    case_results: list[DynamicCaseVerification] = Field(default_factory=list)
    overall_reward: float = 0.0
