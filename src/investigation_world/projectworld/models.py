from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectDomain(StrEnum):
    GENERIC = "generic_project"
    CONSTRUCTION = "construction"
    SOFTWARE = "software_development"
    MANUFACTURING = "manufacturing"
    INFRASTRUCTURE = "infrastructure"
    RESEARCH = "research"


class ProjectPhase(StrEnum):
    INITIATION = "initiation"
    DESIGN = "design"
    PLANNING = "planning"
    PROCUREMENT = "procurement"
    EXECUTION = "execution"
    COMMISSIONING = "commissioning"
    HANDOVER = "handover"
    CLOSED = "closed"


class ProjectActionKind(StrEnum):
    START_WORK = "start_work"
    ADVANCE_TIME = "advance_time"
    PROCURE = "procure"
    CHOOSE_OPTION = "choose_option"
    APPROVE = "approve"
    INSPECT = "inspect"
    RESOLVE_ISSUE = "resolve_issue"


class WorkPackageStatus(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    AWAITING_INSPECTION = "awaiting_inspection"
    AWAITING_APPROVAL = "awaiting_approval"
    REWORK_REQUIRED = "rework_required"
    COMPLETE = "complete"
    CANCELLED = "cancelled"


class ResourceKind(StrEnum):
    LABOR = "labor"
    MATERIAL = "material"
    EQUIPMENT = "equipment"
    CAPITAL = "capital"
    CAPACITY = "capacity"


class ProjectRoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_id: str
    label: str
    allowed_actions: list[ProjectActionKind]
    managed_role_ids: list[str] = Field(default_factory=list)
    can_view_all: bool = False
    visible_role_ids: list[str] = Field(default_factory=list)
    approval_limit: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectResourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: str
    label: str
    kind: ResourceKind
    unit: str
    initial_available: float = Field(default=0.0, ge=0.0)
    unit_cost: float = Field(default=0.0, ge=0.0)
    procurement_lead_days: int = Field(default=0, ge=0)
    consumable: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: str
    description: str
    satisfied_by_work_packages: list[str]
    hard: bool = True
    weight: float = Field(default=1.0, gt=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectWorkPackageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_package_id: str
    name: str
    phase: ProjectPhase
    owner_role_id: str
    dependencies: list[str] = Field(default_factory=list)
    duration_days: int = Field(ge=1)
    direct_cost: float = Field(default=0.0, ge=0.0)
    required_resources: dict[str, float] = Field(default_factory=dict)
    requires_inspection: bool = False
    requires_approval: bool = False
    approval_role_ids: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_approval(self) -> "ProjectWorkPackageSpec":
        if self.requires_approval and not self.approval_role_ids:
            raise ValueError("approval_role_ids are required when requires_approval=True")
        if any(amount <= 0 for amount in self.required_resources.values()):
            raise ValueError("required resource quantities must be positive")
        return self


class ProjectDecisionOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    option_id: str
    label: str
    cost_delta_by_work_package: dict[str, float] = Field(default_factory=dict)
    duration_delta_by_work_package: dict[str, int] = Field(default_factory=dict)
    resource_requirements_by_work_package: dict[str, dict[str, float]] = Field(
        default_factory=dict
    )
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectDecisionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str
    name: str
    owner_role_id: str
    options: list[ProjectDecisionOption]
    required_before_work_packages: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_options(self) -> "ProjectDecisionSpec":
        option_ids = [option.option_id for option in self.options]
        if not option_ids:
            raise ValueError("project decisions require at least one option")
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("decision option IDs must be unique")
        return self


class HiddenDefect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    description: str
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    rework_cost: float = Field(default=0.0, ge=0.0)
    rework_days: int = Field(default=1, ge=1)


class ProjectOracle(BaseModel):
    """Private scenario truth. Never include this object in agent-facing payloads."""

    model_config = ConfigDict(extra="forbid")

    work_package_delay_days: dict[str, int] = Field(default_factory=dict)
    resource_delay_days: dict[str, int] = Field(default_factory=dict)
    latent_defects: dict[str, HiddenDefect] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationalProjectWorldSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_id: str
    project_id: str
    name: str
    domain: ProjectDomain
    budget: float = Field(gt=0.0)
    deadline_days: int = Field(gt=0)
    roles: list[ProjectRoleSpec]
    resources: list[ProjectResourceSpec]
    work_packages: list[ProjectWorkPackageSpec]
    requirements: list[ProjectRequirement] = Field(default_factory=list)
    decisions: list[ProjectDecisionSpec] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_graph(self) -> "OperationalProjectWorldSpec":
        role_ids = [role.role_id for role in self.roles]
        resource_ids = [resource.resource_id for resource in self.resources]
        work_ids = [work.work_package_id for work in self.work_packages]
        decision_ids = [decision.decision_id for decision in self.decisions]
        for label, values in {
            "role": role_ids,
            "resource": resource_ids,
            "work package": work_ids,
            "decision": decision_ids,
        }.items():
            if len(values) != len(set(values)):
                raise ValueError(f"{label} IDs must be unique")

        role_set = set(role_ids)
        resource_set = set(resource_ids)
        work_set = set(work_ids)
        for work in self.work_packages:
            if work.owner_role_id not in role_set:
                raise ValueError(f"unknown owner role: {work.owner_role_id}")
            unknown_dependencies = set(work.dependencies) - work_set
            if unknown_dependencies:
                raise ValueError(
                    f"unknown dependencies for {work.work_package_id}: {sorted(unknown_dependencies)}"
                )
            if work.work_package_id in work.dependencies:
                raise ValueError("work package cannot depend on itself")
            unknown_resources = set(work.required_resources) - resource_set
            if unknown_resources:
                raise ValueError(
                    f"unknown resources for {work.work_package_id}: {sorted(unknown_resources)}"
                )
            unknown_approvers = set(work.approval_role_ids) - role_set
            if unknown_approvers:
                raise ValueError(
                    f"unknown approval roles for {work.work_package_id}: {sorted(unknown_approvers)}"
                )

        requirement_ids = [requirement.requirement_id for requirement in self.requirements]
        if len(requirement_ids) != len(set(requirement_ids)):
            raise ValueError("requirement IDs must be unique")
        for requirement in self.requirements:
            unknown = set(requirement.satisfied_by_work_packages) - work_set
            if unknown:
                raise ValueError(
                    f"unknown requirement work packages for {requirement.requirement_id}: {sorted(unknown)}"
                )

        for decision in self.decisions:
            if decision.owner_role_id not in role_set:
                raise ValueError(f"unknown decision owner role: {decision.owner_role_id}")
            unknown_targets = set(decision.required_before_work_packages) - work_set
            if unknown_targets:
                raise ValueError(
                    f"unknown decision prerequisites for {decision.decision_id}: {sorted(unknown_targets)}"
                )
            for option in decision.options:
                changed_work = (
                    set(option.cost_delta_by_work_package)
                    | set(option.duration_delta_by_work_package)
                    | set(option.resource_requirements_by_work_package)
                )
                unknown = changed_work - work_set
                if unknown:
                    raise ValueError(
                        f"unknown option work packages for {decision.decision_id}: {sorted(unknown)}"
                    )
                for work_id, resources in option.resource_requirements_by_work_package.items():
                    unknown_resources = set(resources) - resource_set
                    if unknown_resources:
                        raise ValueError(
                            f"unknown option resources for {work_id}: {sorted(unknown_resources)}"
                        )
                    if any(amount <= 0 for amount in resources.values()):
                        raise ValueError("decision resource quantities must be positive")

        dependencies = {work.work_package_id: set(work.dependencies) for work in self.work_packages}
        temporary: set[str] = set()
        permanent: set[str] = set()

        def visit(node: str) -> None:
            if node in permanent:
                return
            if node in temporary:
                raise ValueError("work package dependency graph contains a cycle")
            temporary.add(node)
            for dependency in dependencies[node]:
                visit(dependency)
            temporary.remove(node)
            permanent.add(node)

        for work_id in work_ids:
            visit(work_id)
        return self


class ProjectScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec: OperationalProjectWorldSpec
    oracle: ProjectOracle = Field(default_factory=ProjectOracle)
    seed: int = 42

    def public_payload(self) -> dict[str, Any]:
        return {"seed": None, "spec": self.spec.model_dump(mode="json")}


class ProjectIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    work_package_id: str
    description: str
    severity: float = Field(ge=0.0, le=1.0)
    rework_cost: float = Field(ge=0.0)
    rework_days: int = Field(ge=1)
    open: bool = True


class ProcurementOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    resource_id: str
    quantity: float = Field(gt=0.0)
    ordered_day: int = Field(ge=0)
    expected_day: int = Field(ge=0)
    status: str = "ordered"


class ScheduledProjectEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    due_day: int = Field(ge=0)
    event_type: str
    target_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ProjectWorldState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: int = 0
    phase: ProjectPhase = ProjectPhase.INITIATION
    cost_spent: float = 0.0
    work_package_status: dict[str, WorkPackageStatus]
    work_package_started_day: dict[str, int] = Field(default_factory=dict)
    work_package_completed_day: dict[str, int] = Field(default_factory=dict)
    effective_duration_days: dict[str, int]
    effective_direct_cost: dict[str, float]
    effective_required_resources: dict[str, dict[str, float]]
    resource_available: dict[str, float]
    decisions: dict[str, str] = Field(default_factory=dict)
    approvals: dict[str, str] = Field(default_factory=dict)
    issues: dict[str, ProjectIssue] = Field(default_factory=dict)
    procurement_orders: dict[str, ProcurementOrder] = Field(default_factory=dict)
    completed_deliverables: list[str] = Field(default_factory=list)


class ProjectAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    actor_role_id: str
    kind: ProjectActionKind
    target_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProjectJournalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    day: int
    actor_role_id: str
    action: ProjectActionKind
    target_id: str | None = None
    accepted: bool
    message: str
    state_changes: dict[str, Any] = Field(default_factory=dict)
    side_effects: list[str] = Field(default_factory=list)


class ProjectObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    world_id: str
    project_id: str
    role_id: str
    day: int
    phase: ProjectPhase
    budget: float
    cost_spent: float
    deadline_days: int
    work_packages: list[dict[str, Any]]
    resources: dict[str, float]
    decisions: dict[str, str]
    pending_decisions: list[str]
    pending_approvals: list[str]
    issues: list[dict[str, Any]]
    recent_events: list[dict[str, Any]]


class ProjectTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted: bool
    reward: float
    done: bool
    message: str
    observation: ProjectObservation
    info: dict[str, Any] = Field(default_factory=dict)


class ProjectVerificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    completion: float = Field(ge=0.0, le=1.0)
    requirements: float = Field(ge=0.0, le=1.0)
    cost: float = Field(ge=0.0, le=1.0)
    schedule: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)
    authority: float = Field(ge=0.0, le=1.0)
    overall_reward: float = Field(ge=0.0, le=1.0)
    passed: bool
    completed_work_packages: int
    total_work_packages: int
    satisfied_requirements: list[str]
    failed_requirements: list[str]
    open_issue_ids: list[str]
    rejected_actions: int
    budget_overrun: float
    schedule_overrun_days: int
