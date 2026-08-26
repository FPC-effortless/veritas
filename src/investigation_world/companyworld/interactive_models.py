from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.companyworld.models import CompanySystem, CompanyWorldEpisode


class OperationalActionType(StrEnum):
    CREATE_RESHIPMENT = "CREATE_RESHIPMENT"
    ESCALATE_SHIPMENT_EXCEPTION = "ESCALATE_SHIPMENT_EXCEPTION"
    BLOCK_SUPPLIER_INVOICE = "BLOCK_SUPPLIER_INVOICE"
    ESCALATE_INVOICE_EXCEPTION = "ESCALATE_INVOICE_EXCEPTION"
    RESTORE_AUTHORITY_LIMIT = "RESTORE_AUTHORITY_LIMIT"
    ESCALATE_AUTHORITY_REPAIR = "ESCALATE_AUTHORITY_REPAIR"
    EXPEDITE_ORDER = "EXPEDITE_ORDER"
    CONFIRM_FULFILLMENT = "CONFIRM_FULFILLMENT"
    ESCALATE_FULFILLMENT_DELAY = "ESCALATE_FULFILLMENT_DELAY"
    APPROVE_SUPPLIER_INVOICE = "APPROVE_SUPPLIER_INVOICE"
    ROUTE_INVOICE_REVIEW = "ROUTE_INVOICE_REVIEW"
    REQUEST_INVOICE_APPROVAL = "REQUEST_INVOICE_APPROVAL"
    CLOSE_AR_CASE = "CLOSE_AR_CASE"
    OPEN_COLLECTIONS_CASE = "OPEN_COLLECTIONS_CASE"
    CLOSE_PAYMENT_BLOCK_CASE = "CLOSE_PAYMENT_BLOCK_CASE"
    ESCALATE_PAYMENT_BLOCK_RECOVERY = "ESCALATE_PAYMENT_BLOCK_RECOVERY"
    ESCALATE_INCIDENT = "ESCALATE_INCIDENT"
    CLOSE_INCIDENT_REVIEW = "CLOSE_INCIDENT_REVIEW"
    ESCALATE_SAFETY_ACTION = "ESCALATE_SAFETY_ACTION"
    CLOSE_SAFETY_REVIEW = "CLOSE_SAFETY_REVIEW"
    CERTIFY_CASH_CYCLE = "CERTIFY_CASH_CYCLE"
    ESCALATE_CASH_CYCLE_REVIEW = "ESCALATE_CASH_CYCLE_REVIEW"
    CERTIFY_LEDGER_POSTING = "CERTIFY_LEDGER_POSTING"
    ESCALATE_LEDGER_REVIEW = "ESCALATE_LEDGER_REVIEW"
    OPEN_CONTROL_CASE = "OPEN_CONTROL_CASE"
    REQUEST_OPERATIONAL_APPROVAL = "REQUEST_OPERATIONAL_APPROVAL"
    RECONCILE_SYSTEM_STATE = "RECONCILE_SYSTEM_STATE"
    VERIFY_CONTROL_INVARIANTS = "VERIFY_CONTROL_INVARIANTS"
    CLOSE_CONTROL_CASE = "CLOSE_CONTROL_CASE"
    COMPENSATE_LAST_ACTION = "COMPENSATE_LAST_ACTION"
    ESCALATE_CONTROL_FAILURE = "ESCALATE_CONTROL_FAILURE"


class StateValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_type: str
    object_id: str
    field_name: str
    value: Any

    def key(self) -> tuple[str, str, str]:
        return (self.object_type, self.object_id, self.field_name)


class ActionEffectTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field_name: str
    constant_value: Any | None = None
    parameter_name: str | None = None


class ActionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: OperationalActionType
    allowed_roles: list[str]
    cost: int = Field(default=2, ge=0)
    effects: list[ActionEffectTemplate] = Field(default_factory=list)
    description: str = ""


class OperationalAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: OperationalActionType
    target_object_type: str
    target_object_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ActionExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int
    action: OperationalAction
    actor_role: str
    authorized: bool
    applied: bool
    cost: int = 0
    reason: str = ""
    effects: list[StateValue] = Field(default_factory=list)


class InteractiveCompanyWorldTask(BaseModel):
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
    action_policies: list[ActionPolicy]
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractiveOutcomeCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_type: str
    object_id: str
    field_name: str
    expected_value: Any

    def key(self) -> tuple[str, str, str]:
        return (self.object_type, self.object_id, self.field_name)


class InteractiveCompanyWorldOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    expected_action_type: OperationalActionType
    expected_action_parameters: dict[str, Any] = Field(default_factory=dict)
    outcome_conditions: list[InteractiveOutcomeCondition]
    max_applied_actions: int = Field(default=1, ge=1)


class InteractiveCompanyWorldEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    world_id: str
    investigation: CompanyWorldEpisode
    task: InteractiveCompanyWorldTask
    initial_state: list[StateValue]
    oracle: InteractiveCompanyWorldOracle
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "task": self.task.model_dump(mode="json"),
            "investigation": self.investigation.public_payload(),
            "initial_state": [item.model_dump(mode="json") for item in self.initial_state],
            "metadata": self.metadata,
        }


class InteractiveCompanyWorldVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome_score: float = 0.0
    investigation_fact_score: float = 0.0
    evidence_support: float = 0.0
    action_precision: float = 0.0
    authority_score: float = 0.0
    efficiency: float = 0.0
    unauthorized_attempts: int = 0
    extra_applied_actions: int = 0
    overall_reward: float = 0.0
