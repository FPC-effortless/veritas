from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompanySystem(StrEnum):
    ERP = "ERP"
    WMS = "WMS"
    AP_WORKFLOW = "AP_WORKFLOW"
    AUTH_SERVICE = "AUTH_SERVICE"
    EMAIL = "EMAIL"
    LEDGER = "LEDGER"
    PROCESS = "PROCESS"


class CompanyWorldRecord(BaseModel):
    """Agent-visible record projected from one enterprise system."""

    model_config = ConfigDict(extra="forbid")
    record_id: str
    system: CompanySystem
    record_type: str
    object_type: str
    object_id: str
    fields: dict[str, Any] = Field(default_factory=dict)
    source_file: str
    observed_at: datetime | None = None
    related_object_ids: list[str] = Field(default_factory=list)


class OperationalFactTarget(BaseModel):
    """Verifier-only operational fact expected from an investigation."""

    model_config = ConfigDict(extra="forbid")
    object_type: str
    object_id: str
    field_name: str
    expected_value: Any
    supporting_record_ids: list[str] = Field(default_factory=list)

    def key(self) -> tuple[str, str, str]:
        return (self.object_type, self.object_id, self.field_name)


class CompanyWorldTask(BaseModel):
    """Public task definition; contains no evaluator truth."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    world_id: str
    task_type: str
    objective: str
    target_object_type: str
    target_object_id: str
    permitted_systems: list[CompanySystem]
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyWorldOracle(BaseModel):
    """Private task oracle. Never expose through agent-facing APIs."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    answer_class: str
    expected_resolution: str
    answerable: bool = True
    answerability_reason: str = ""
    facts: list[OperationalFactTarget] = Field(default_factory=list)
    hidden_error_id: str | None = None
    hidden_cause: str | None = None


class CompanyWorldEpisode(BaseModel):
    """Compiled operational investigation episode with public records and private oracle."""

    model_config = ConfigDict(extra="forbid")
    episode_id: str
    world_id: str
    task: CompanyWorldTask
    records: list[CompanyWorldRecord]
    oracle: CompanyWorldOracle
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "task": self.task.model_dump(mode="json"),
            "records": [record.model_dump(mode="json") for record in self.records],
            "metadata": self.metadata,
        }


class CompanyWorldValidationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    world_id: str | None = None
    required_files_present: bool = False
    source_validation_passed: bool = False
    task_oracle_ids_match: bool = False
    public_projection_leakage_count: int = 0
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.errors


class CompanyWorldVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fact_score: float = 0.0
    fact_precision: float = 0.0
    fact_recall: float = 0.0
    evidence_support: float = 0.0
    calibration: float = 0.0
    abstention: float = 0.0
    efficiency: float = 0.0
    false_fact_count: int = 0
    unresolved_fact_count: int = 0
    overall_reward: float = 0.0
