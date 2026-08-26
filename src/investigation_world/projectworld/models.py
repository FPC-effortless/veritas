from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectPhase(StrEnum):
    BRIEF = "BRIEF"
    FEASIBILITY = "FEASIBILITY"
    CONCEPT = "CONCEPT"
    DESIGN = "DESIGN"
    PRECONSTRUCTION = "PRECONSTRUCTION"
    PROCUREMENT = "PROCUREMENT"
    CONSTRUCTION = "CONSTRUCTION"
    COMMISSIONING = "COMMISSIONING"
    HANDOVER = "HANDOVER"
    CLOSED = "CLOSED"


class ProjectRole(StrEnum):
    OWNER = "OWNER"
    OWNERS_REP = "OWNERS_REP"
    PROJECT_DIRECTOR = "PROJECT_DIRECTOR"
    PROJECT_MANAGER = "PROJECT_MANAGER"
    ARCHITECT = "ARCHITECT"
    STRUCTURAL_ENGINEER = "STRUCTURAL_ENGINEER"
    MEP_ENGINEER = "MEP_ENGINEER"
    QUANTITY_SURVEYOR = "QUANTITY_SURVEYOR"
    BIM_COORDINATOR = "BIM_COORDINATOR"
    PROCUREMENT_MANAGER = "PROCUREMENT_MANAGER"
    CONTRACT_ADMINISTRATOR = "CONTRACT_ADMINISTRATOR"
    SITE_MANAGER = "SITE_MANAGER"
    SUPERINTENDENT = "SUPERINTENDENT"
    SAFETY_MANAGER = "SAFETY_MANAGER"
    QA_QC_INSPECTOR = "QA_QC_INSPECTOR"
    SUBCONTRACTOR = "SUBCONTRACTOR"
    COMMISSIONING_MANAGER = "COMMISSIONING_MANAGER"


class ProjectActionType(StrEnum):
    RECORD_REQUIREMENT = "RECORD_REQUIREMENT"
    SUBMIT_DESIGN = "SUBMIT_DESIGN"
    REVIEW_DESIGN = "REVIEW_DESIGN"
    APPROVE_DESIGN = "APPROVE_DESIGN"
    REJECT_DESIGN = "REJECT_DESIGN"
    ISSUE_RFI = "ISSUE_RFI"
    RESPOND_RFI = "RESPOND_RFI"
    SUBMIT_SUBMITTAL = "SUBMIT_SUBMITTAL"
    REVIEW_SUBMITTAL = "REVIEW_SUBMITTAL"
    APPROVE_SUBMITTAL = "APPROVE_SUBMITTAL"
    CREATE_WORK_PACKAGE = "CREATE_WORK_PACKAGE"
    RELEASE_WORK_PACKAGE = "RELEASE_WORK_PACKAGE"
    PROCURE_PACKAGE = "PROCURE_PACKAGE"
    EXPEDITE_PACKAGE = "EXPEDITE_PACKAGE"
    START_ACTIVITY = "START_ACTIVITY"
    COMPLETE_ACTIVITY = "COMPLETE_ACTIVITY"
    PAUSE_ACTIVITY = "PAUSE_ACTIVITY"
    UPDATE_SCHEDULE = "UPDATE_SCHEDULE"
    COMMIT_RESOURCE = "COMMIT_RESOURCE"
    RELEASE_RESOURCE = "RELEASE_RESOURCE"
    RECORD_PROGRESS = "RECORD_PROGRESS"
    RAISE_RISK = "RAISE_RISK"
    MITIGATE_RISK = "MITIGATE_RISK"
    RECORD_SAFETY_OBSERVATION = "RECORD_SAFETY_OBSERVATION"
    STOP_WORK = "STOP_WORK"
    INSPECT_WORK = "INSPECT_WORK"
    ACCEPT_WORK = "ACCEPT_WORK"
    REJECT_WORK = "REJECT_WORK"
    CREATE_CHANGE_ORDER = "CREATE_CHANGE_ORDER"
    APPROVE_CHANGE_ORDER = "APPROVE_CHANGE_ORDER"
    REJECT_CHANGE_ORDER = "REJECT_CHANGE_ORDER"
    CERTIFY_PAYMENT = "CERTIFY_PAYMENT"
    ISSUE_HANDOFF = "ISSUE_HANDOFF"
    ACCEPT_HANDOFF = "ACCEPT_HANDOFF"
    COMMISSION_SYSTEM = "COMMISSION_SYSTEM"
    ACCEPT_PROJECT = "ACCEPT_PROJECT"
    ADVANCE_PHASE = "ADVANCE_PHASE"
    REQUEST_APPROVAL = "REQUEST_APPROVAL"
    COMPENSATE_ACTION = "COMPENSATE_ACTION"


class ConditionOperator(StrEnum):
    EQ = "EQ"
    NE = "NE"
    LTE = "LTE"
    GTE = "GTE"
    LT = "LT"
    GT = "GT"
    IN = "IN"
    NOT_IN = "NOT_IN"
    EXISTS = "EXISTS"


class VerificationDimension(StrEnum):
    REQUIREMENTS = "requirements"
    QUALITY = "quality"
    SCHEDULE = "schedule"
    COST = "cost"
    SAFETY = "safety"
    COORDINATION = "coordination"
    AUTHORITY = "authority"
    PROCESS = "process"
    EVIDENCE = "evidence"
    HANDOVER = "handover"


class ProjectStateValue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_type: str
    object_id: str
    field_name: str
    value: Any
    namespace: str = "project"
    source_ids: list[str] = Field(default_factory=list)

    def key(self) -> tuple[str, str, str]:
        return self.object_type, self.object_id, self.field_name


class ProjectCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_type: str
    object_id: str
    field_name: str
    operator: ConditionOperator = ConditionOperator.EQ
    expected_value: Any = None

    def key(self) -> tuple[str, str, str]:
        return self.object_type, self.object_id, self.field_name


class ProjectEffectTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_type: str | None = None
    object_id: str | None = None
    field_name: str
    namespace: str = "project"
    constant_value: Any | None = None
    parameter_name: str | None = None

    @model_validator(mode="after")
    def validate_value_source(self):
        if self.constant_value is None and self.parameter_name is None:
            raise ValueError("effect requires constant_value or parameter_name")
        return self


class DelayedProjectEffect(ProjectEffectTemplate):
    delay_ticks: int = Field(default=1, ge=1)


class ProjectRolePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ProjectRole
    readable_namespaces: list[str] = Field(default_factory=lambda: ["project"])
    writable_namespaces: list[str] = Field(default_factory=lambda: ["project"])
    direct_authority_limit: float = Field(default=0.0, ge=0.0)
    can_delegate: bool = False
    can_approve: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectActionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: ProjectActionType
    allowed_roles: list[ProjectRole]
    allowed_phases: list[ProjectPhase]
    allowed_object_types: list[str] = Field(default_factory=list)
    cost: int = Field(default=1, ge=0)
    prerequisites: list[ProjectCondition] = Field(default_factory=list)
    effects: list[ProjectEffectTemplate] = Field(default_factory=list)
    delayed_effects: list[DelayedProjectEffect] = Field(default_factory=list)
    required_evidence_types: list[str] = Field(default_factory=list)
    financial_parameter: str | None = None
    irreversible: bool = False
    resource_gated: bool = False
    description: str = ""


class ProjectAction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action_type: ProjectActionType
    target_object_type: str
    target_object_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)


class ProjectActivity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    activity_id: str
    name: str
    phase: ProjectPhase
    work_package_id: str | None = None
    predecessor_ids: list[str] = Field(default_factory=list)
    duration_ticks: int = Field(default=1, ge=1)
    resource_demands: dict[str, int] = Field(default_factory=dict)
    planned_cost: float = Field(default=0.0, ge=0.0)
    critical: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectResource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    resource_id: str
    resource_type: str
    capacity: int = Field(default=1, ge=1)
    unit_cost_per_tick: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectEvidenceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    evidence_id: str
    evidence_type: str
    title: str
    text: str = ""
    namespace: str = "project"
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    source_ids: list[str] = Field(default_factory=list)
    authoritative: bool = False


class ProjectOutcomeCondition(ProjectCondition):
    dimension: VerificationDimension
    weight: float = Field(default=1.0, gt=0.0)
    critical: bool = False


class ProjectExogenousEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str
    due_tick: int = Field(ge=0)
    label: str
    effects: list[ProjectStateValue]
    hidden_until_due: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    world_id: str
    objective: str
    initial_phase: ProjectPhase
    available_roles: list[ProjectRole]
    role_policies: list[ProjectRolePolicy]
    action_policies: list[ProjectActionPolicy]
    max_actions: int = Field(default=100, ge=1)
    max_ticks: int = Field(default=100, ge=1)
    budget_limit: float = Field(default=0.0, ge=0.0)
    constraints: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_roles(self):
        policy_roles = {policy.role for policy in self.role_policies}
        missing = set(self.available_roles) - policy_roles
        if missing:
            raise ValueError(f"missing role policies for: {sorted(item.value for item in missing)}")
        return self


class ProjectOracle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_id: str
    outcome_conditions: list[ProjectOutcomeCondition]
    hidden_events: list[ProjectExogenousEvent] = Field(default_factory=list)
    dimension_weights: dict[VerificationDimension, float] = Field(default_factory=dict)
    maximum_rework_events: int = Field(default=0, ge=0)
    maximum_unauthorized_attempts: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationalProjectEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    world_id: str
    domain: str
    task: ProjectTask
    initial_state: list[ProjectStateValue]
    activities: list[ProjectActivity] = Field(default_factory=list)
    resources: list[ProjectResource] = Field(default_factory=list)
    evidence: list[ProjectEvidenceRecord] = Field(default_factory=list)
    oracle: ProjectOracle
    metadata: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "domain": self.domain,
            "task": self.task.model_dump(mode="json"),
            "initial_state": [item.model_dump(mode="json") for item in self.initial_state],
            "activities": [item.model_dump(mode="json") for item in self.activities],
            "resources": [item.model_dump(mode="json") for item in self.resources],
            "metadata": self.metadata,
        }


class ScheduledProjectEffect(BaseModel):
    model_config = ConfigDict(extra="forbid")
    due_tick: int = Field(ge=0)
    source_sequence: int = Field(ge=1)
    state: ProjectStateValue


class ProjectActionExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int = Field(ge=1)
    tick: int = Field(ge=0)
    actor_role: ProjectRole
    action: ProjectAction
    authorized: bool
    prerequisites_met: bool
    evidence_sufficient: bool
    resource_feasible: bool
    applied: bool
    cost: int = Field(default=0, ge=0)
    financial_impact: float = 0.0
    reason: str = ""
    irreversible: bool = False
    effects: list[ProjectStateValue] = Field(default_factory=list)
    scheduled_effects: list[ScheduledProjectEffect] = Field(default_factory=list)


class ProjectSystemEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tick: int = Field(ge=0)
    event_type: Literal["scheduled_effect", "exogenous_event", "resource_cost"]
    event_id: str
    effects: list[ProjectStateValue] = Field(default_factory=list)
    detail: str = ""


class ProjectObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: ProjectRole
    tick: int
    phase: ProjectPhase
    state: list[ProjectStateValue]
    visible_evidence: list[ProjectEvidenceRecord]
    resource_usage: dict[str, int]
    committed_cost: float
    remaining_budget: float | None


class OperationalProjectVerificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dimension_scores: dict[VerificationDimension, float] = Field(default_factory=dict)
    outcome_score: float = 0.0
    authority_score: float = 0.0
    process_score: float = 0.0
    evidence_score: float = 0.0
    budget_score: float = 0.0
    schedule_score: float = 0.0
    unauthorized_attempts: int = 0
    prerequisite_violations: int = 0
    resource_conflicts: int = 0
    evidence_failures: int = 0
    rework_events: int = 0
    irreversible_errors: int = 0
    ticks_used: int = 0
    committed_cost: float = 0.0
    overall_reward: float = 0.0
