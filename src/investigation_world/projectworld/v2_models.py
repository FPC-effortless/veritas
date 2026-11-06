from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ProjectType(StrEnum):
    COMMERCIAL = "commercial"
    DATA_CENTER = "data_center"
    HOSPITAL = "hospital"
    LABORATORY = "laboratory"
    EDUCATION = "education"


class DeliveryModel(StrEnum):
    DESIGN_BID_BUILD = "design_bid_build"
    DESIGN_BUILD = "design_build"
    CM_AT_RISK = "cm_at_risk"
    EPC = "epc"


class ContractModel(StrEnum):
    LUMP_SUM = "lump_sum"
    GMP = "guaranteed_maximum_price"
    UNIT_RATE = "unit_rate"
    COST_PLUS = "cost_plus"


class OutcomeDimension(StrEnum):
    TECHNICAL = "technical"
    QUALITY = "quality"
    SAFETY = "safety"
    AUTHORITY = "authority"


class DisturbanceKind(StrEnum):
    RESOURCE_DELAY = "resource_delay"
    DEFECT = "defect"
    WEATHER_STOP = "weather_stop"
    APPROVAL_DELAY = "approval_delay"
    SUPPLIER_FAILURE = "supplier_failure"


class V2ActionKind(StrEnum):
    START_WORK = "start_work"
    ADVANCE_TIME = "advance_time"
    PLACE_PO = "place_po"
    EXPEDITE_PO = "expedite_po"
    SUBSTITUTE_SUPPLIER = "substitute_supplier"
    ADD_CREW = "add_crew"
    AUTHORIZE_OVERTIME = "authorize_overtime"
    INSPECT = "inspect"
    APPROVE = "approve"
    RESOLVE_ISSUE = "resolve_issue"
    RESEQUENCE_WORK = "resequence_work"


class V2WorkStatus(StrEnum):
    BLOCKED = "blocked"
    READY = "ready"
    IN_PROGRESS = "in_progress"
    AWAITING_INSPECTION = "awaiting_inspection"
    AWAITING_APPROVAL = "awaiting_approval"
    REWORK_REQUIRED = "rework_required"
    COMPLETE = "complete"


class POStatus(StrEnum):
    ORDERED = "ordered"
    ACKNOWLEDGED = "acknowledged"
    SHIPPED = "shipped"
    DELAYED = "delayed"
    ARRIVED = "arrived"
    CANCELLED = "cancelled"


class V2RoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    role_id: str
    label: str
    allowed_actions: list[V2ActionKind]
    managed_role_ids: list[str] = Field(default_factory=list)
    visible_role_ids: list[str] = Field(default_factory=list)
    can_view_all: bool = False
    approval_limit: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class V2ResourceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    resource_id: str
    label: str
    unit: str
    initial_available: float = Field(default=0.0, ge=0.0)
    consumable: bool = True
    storage_capacity: float | None = Field(default=None, gt=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SupplierSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    supplier_id: str
    resource_id: str
    capacity_per_order: float = Field(gt=0.0)
    minimum_order_quantity: float = Field(default=1.0, gt=0.0)
    lead_days: int = Field(ge=0)
    unit_cost: float = Field(ge=0.0)
    reliability: float = Field(default=1.0, ge=0.0, le=1.0)
    expedite_days: int = Field(default=0, ge=0)
    expedite_premium_pct: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class V2ContractSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: str
    counterparty_id: str
    model: ContractModel
    work_package_ids: list[str]
    payment_days: int = Field(default=30, ge=0)
    retainage_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class V2WorkPackageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    work_package_id: str
    name: str
    phase: str
    owner_role_id: str
    dependencies: list[str] = Field(default_factory=list)
    duration_days: int = Field(ge=1)
    direct_cost: float = Field(default=0.0, ge=0.0)
    resource_demand: dict[str, float] = Field(default_factory=dict)
    requires_inspection: bool = False
    requires_approval: bool = False
    approval_role_ids: list[str] = Field(default_factory=list)
    deliverables: list[str] = Field(default_factory=list)
    technical_tags: list[str] = Field(default_factory=list)
    safety_critical: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class ApprovalGateSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    gate_id: str
    work_package_id: str
    authorized_role_ids: list[str] = Field(min_length=1)
    max_value: float | None = Field(default=None, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    risk_id: str
    target_id: str
    probability: float = Field(ge=0.0, le=1.0)
    cost_impact: float = Field(default=0.0, ge=0.0)
    schedule_impact_days: int = Field(default=0, ge=0)
    mitigation_action: V2ActionKind | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OutcomeContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_id: str
    dimension: OutcomeDimension
    description: str
    work_package_ids: list[str] = Field(default_factory=list)
    required_deliverables: list[str] = Field(default_factory=list)
    hard: bool = True
    weight: float = Field(default=1.0, gt=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DisturbanceSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    disturbance_id: str
    day: int = Field(ge=0)
    kind: DisturbanceKind
    target_id: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ProjectGrammarSpec(BaseModel):
    """Declarative grammar that determines a concrete project topology."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    project_id: str
    project_type: ProjectType
    delivery_model: DeliveryModel
    jurisdiction: str
    site_conditions: dict[str, Any] = Field(default_factory=dict)
    building_systems: list[str] = Field(default_factory=list)
    stakeholder_graph: list[V2RoleSpec] = Field(default_factory=list)
    contract_structure: list[V2ContractSpec] = Field(default_factory=list)
    work_breakdown_grammar: str = "default"
    resource_network: list[V2ResourceSpec] = Field(default_factory=list)
    supplier_network: list[SupplierSpec] = Field(default_factory=list)
    approval_graph: list[ApprovalGateSpec] = Field(default_factory=list)
    risk_model: list[RiskSpec] = Field(default_factory=list)
    requirement_graph: list[OutcomeContract] = Field(default_factory=list)
    disturbance_process: list[DisturbanceSpec] = Field(default_factory=list)
    budget: float = Field(gt=0.0)
    deadline_days: int = Field(gt=0)
    seed: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompiledProjectSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    world_id: str
    grammar: ProjectGrammarSpec
    roles: list[V2RoleSpec]
    resources: list[V2ResourceSpec]
    suppliers: list[SupplierSpec]
    work_packages: list[V2WorkPackageSpec]
    contracts: list[V2ContractSpec]
    approval_gates: list[ApprovalGateSpec]
    risks: list[RiskSpec]
    outcome_contracts: list[OutcomeContract]
    disturbances: list[DisturbanceSpec]

    @model_validator(mode="after")
    def validate_compiled_graph(self) -> "CompiledProjectSpec":
        role_ids = {item.role_id for item in self.roles}
        resource_ids = {item.resource_id for item in self.resources}
        work_ids = {item.work_package_id for item in self.work_packages}
        supplier_ids = {item.supplier_id for item in self.suppliers}
        for label, values, total in (
            ("role", role_ids, len(self.roles)),
            ("resource", resource_ids, len(self.resources)),
            ("work package", work_ids, len(self.work_packages)),
            ("supplier", supplier_ids, len(self.suppliers)),
        ):
            if len(values) != total:
                raise ValueError(f"duplicate {label} IDs")
        for work in self.work_packages:
            if work.owner_role_id not in role_ids:
                raise ValueError(f"unknown owner role {work.owner_role_id}")
            if set(work.dependencies) - work_ids:
                raise ValueError(f"unknown dependency for {work.work_package_id}")
            if set(work.resource_demand) - resource_ids:
                raise ValueError(f"unknown resource demand for {work.work_package_id}")
            if set(work.approval_role_ids) - role_ids:
                raise ValueError(f"unknown approval role for {work.work_package_id}")
        for supplier in self.suppliers:
            if supplier.resource_id not in resource_ids:
                raise ValueError(f"supplier {supplier.supplier_id} references unknown resource")
        for gate in self.approval_gates:
            if gate.work_package_id not in work_ids or set(gate.authorized_role_ids) - role_ids:
                raise ValueError(f"invalid approval gate {gate.gate_id}")
        for contract in self.contracts:
            if set(contract.work_package_ids) - work_ids:
                raise ValueError(f"contract {contract.contract_id} references unknown work")
        for outcome in self.outcome_contracts:
            if set(outcome.work_package_ids) - work_ids:
                raise ValueError(f"outcome contract {outcome.contract_id} references unknown work")

        dependencies = {item.work_package_id: set(item.dependencies) for item in self.work_packages}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visited:
                return
            if node in visiting:
                raise ValueError("ProjectWorld v2 work graph contains a cycle")
            visiting.add(node)
            for dependency in dependencies[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for work_id in sorted(work_ids):
            visit(work_id)
        return self


class V2ProcurementOrder(BaseModel):
    model_config = ConfigDict(extra="forbid")
    order_id: str
    resource_id: str
    supplier_id: str
    quantity: float = Field(gt=0.0)
    ordered_day: int = Field(ge=0)
    acknowledged_day: int | None = Field(default=None, ge=0)
    shipped_day: int | None = Field(default=None, ge=0)
    expected_day: int = Field(ge=0)
    arrived_day: int | None = Field(default=None, ge=0)
    status: POStatus = POStatus.ORDERED
    unit_cost: float = Field(ge=0.0)
    expedite_premium: float = Field(default=0.0, ge=0.0)


class V2Issue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issue_id: str
    work_package_id: str
    severity: float = Field(ge=0.0, le=1.0)
    description: str
    rework_days: int = Field(ge=1)
    rework_cost: float = Field(ge=0.0)
    rework_resource_demand: dict[str, float] = Field(default_factory=dict)
    open: bool = True
    rework_started_day: int | None = None


class V2ProjectState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day: int = 0
    cost_spent: float = 0.0
    work_status: dict[str, V2WorkStatus]
    work_started_day: dict[str, int] = Field(default_factory=dict)
    work_remaining_days: dict[str, int]
    resource_available: dict[str, float]
    procurement_orders: dict[str, V2ProcurementOrder] = Field(default_factory=dict)
    issues: dict[str, V2Issue] = Field(default_factory=dict)
    completed_deliverables: list[str] = Field(default_factory=list)
    approvals: dict[str, str] = Field(default_factory=dict)
    inspection_passed: list[str] = Field(default_factory=list)
    overtime_authorized: list[str] = Field(default_factory=list)
    disturbance_log: list[str] = Field(default_factory=list)
    authority_violations: int = 0
    safety_violations: int = 0


class V2Action(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    kind: V2ActionKind
    target_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)


class V2Observation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    world_id: str
    project_id: str
    role_id: str
    day: int
    budget: float
    cost_spent: float
    deadline_days: int
    work_packages: list[dict[str, Any]]
    resources: dict[str, float]
    procurement_orders: list[dict[str, Any]]
    issues: list[dict[str, Any]]
    approvals: dict[str, str]
    disturbances: list[str]


class V2Transition(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    accepted: bool
    reward: float
    message: str
    observation: V2Observation
    done: bool
    info: dict[str, Any] = Field(default_factory=dict)


class V2OutcomeReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    technical: float = Field(ge=0.0, le=1.0)
    quality: float = Field(ge=0.0, le=1.0)
    safety: float = Field(ge=0.0, le=1.0)
    authority: float = Field(ge=0.0, le=1.0)
    schedule: float = Field(ge=0.0, le=1.0)
    cost: float = Field(ge=0.0, le=1.0)
    completion: float = Field(ge=0.0, le=1.0)
    overall_reward: float = Field(ge=0.0, le=1.0)
    passed: bool
    failed_contract_ids: list[str] = Field(default_factory=list)
