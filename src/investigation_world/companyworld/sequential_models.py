from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.companyworld.interactive_models import (
    ActionEffectTemplate,
    InteractiveCompanyWorldEpisode,
    InteractiveOutcomeCondition,
    OperationalAction,
    OperationalActionType,
    StateValue,
)
from investigation_world.companyworld.models import CompanySystem


class StateCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_type: str
    object_id: str
    field_name: str
    expected_value: Any

    def key(self) -> tuple[str, str, str]:
        return (self.object_type, self.object_id, self.field_name)


class DelayedEffectTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_name: str
    delay_ticks: int = Field(default=1, ge=1)
    constant_value: Any | None = None
    parameter_name: str | None = None


class SequentialActionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: OperationalActionType
    allowed_roles: list[str]
    cost: int = Field(default=2, ge=0)
    stage: str
    description: str = ""
    prerequisites: list[StateCondition] = Field(default_factory=list)
    effects: list[ActionEffectTemplate] = Field(default_factory=list)
    delayed_effects: list[DelayedEffectTemplate] = Field(default_factory=list)
    delegatable_with_approval: bool = False
    compensation_action: bool = False


class ScheduledStateEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_tick: int = Field(ge=1)
    source_sequence: int = Field(ge=1)
    state: StateValue


class SequentialActionExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int = Field(ge=1)
    tick: int = Field(ge=0)
    action: OperationalAction
    actor_role: str
    authorized: bool
    prerequisites_met: bool
    applied: bool
    cost: int = 0
    stage: str = ""
    reason: str = ""
    effects: list[StateValue] = Field(default_factory=list)
    scheduled_effects: list[ScheduledStateEffect] = Field(default_factory=list)


class SequentialSystemEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tick: int = Field(ge=0)
    source_sequence: int = Field(ge=1)
    effects: list[StateValue] = Field(default_factory=list)


class SequentialCompanyWorldTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    world_id: str
    task_type: str
    objective: str
    target_object_type: str
    target_object_id: str
    actor_role: str
    permitted_systems: list[CompanySystem]
    available_actions: list[OperationalActionType]
    action_policies: list[SequentialActionPolicy]
    max_actions: int = Field(default=10, ge=1)
    max_ticks: int = Field(default=8, ge=1)
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SequentialCompanyWorldOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    remediation_action_type: OperationalActionType
    remediation_action_parameters: dict[str, Any] = Field(default_factory=dict)
    domain_outcome_conditions: list[InteractiveOutcomeCondition]
    control_outcome_conditions: list[InteractiveOutcomeCondition]
    approval_required: bool = False
    max_applied_actions: int = Field(default=7, ge=1)
    max_ticks: int = Field(default=8, ge=1)


class SequentialCompanyWorldEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    world_id: str
    interactive: InteractiveCompanyWorldEpisode
    task: SequentialCompanyWorldTask
    initial_state: list[StateValue]
    oracle: SequentialCompanyWorldOracle
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "interactive": self.interactive.public_payload(),
            "task": self.task.model_dump(mode="json"),
            "initial_state": [item.model_dump(mode="json") for item in self.initial_state],
            "metadata": self.metadata,
        }


class SequentialCompanyWorldVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain_outcome_score: float = 0.0
    control_state_score: float = 0.0
    investigation_fact_score: float = 0.0
    evidence_support: float = 0.0
    authority_score: float = 0.0
    sequence_efficiency: float = 0.0
    unauthorized_attempts: int = 0
    prerequisite_violations: int = 0
    extra_applied_actions: int = 0
    ticks_used: int = 0
    overall_reward: float = 0.0
