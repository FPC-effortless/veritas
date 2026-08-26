from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class WorldDomain(StrEnum):
    FINANCIAL_SPREADSHEET = "financial_spreadsheet"
    ENTERPRISE_OPERATIONS = "enterprise_operations"
    DEVOPS_INCIDENT_RESPONSE = "devops_incident_response"
    INVESTIGATION_OSINT = "investigation_osint"
    GIS_OPERATIONS = "gis_operations"


class ActionKind(StrEnum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    COMMUNICATE = "communicate"
    ESCALATE = "escalate"
    SUBMIT = "submit"


class VerificationDimension(StrEnum):
    OUTCOME = "outcome"
    STATE = "state"
    CONSTRAINTS = "constraints"
    SIDE_EFFECTS = "side_effects"
    PROCESS = "process"
    EFFICIENCY = "efficiency"
    EVIDENCE = "evidence"


class OperationalRecord(BaseModel):
    """One agent-visible record projected from a domain system."""

    model_config = ConfigDict(extra="forbid")
    record_id: str
    system: str
    record_type: str
    object_id: str
    fields: dict[str, Any] = Field(default_factory=dict)
    related_object_ids: list[str] = Field(default_factory=list)
    searchable_text: str = ""


class StateAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_id: str
    field_name: str
    expected_value: Any
    tolerance: float | None = Field(default=None, ge=0.0)

    def key(self) -> str:
        return f"{self.object_id}.{self.field_name}"


class OperationalInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invariant_id: str
    description: str
    assertion: StateAssertion
    severity: Literal["low", "medium", "high", "critical"] = "high"


class PublicActionSpec(BaseModel):
    """Agent-visible action contract. Hidden effects live in the oracle."""

    model_config = ConfigDict(extra="forbid")
    name: str
    kind: ActionKind
    system: str
    description: str
    parameter_names: list[str] = Field(default_factory=list)
    cost: int = Field(default=1, ge=0)


class TaskContract(BaseModel):
    """Public, capability-neutral task contract shared by all Veritas worlds."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    world_id: str
    domain: WorldDomain
    objective: str
    role: str
    permitted_systems: list[str]
    available_actions: list[PublicActionSpec]
    constraints: list[str] = Field(default_factory=list)
    success_description: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class HiddenActionEffect(BaseModel):
    """Verifier-only deterministic effect for an executable action."""

    model_config = ConfigDict(extra="forbid")
    action_name: str
    required_parameters: dict[str, Any] = Field(default_factory=dict)
    set_state: dict[str, Any] = Field(default_factory=dict)
    emitted_side_effects: list[str] = Field(default_factory=list)
    forbidden: bool = False
    consequence_severity: float = Field(default=0.0, ge=0.0, le=1.0)


class HiddenOracle(BaseModel):
    """Private evaluator state. Never include this object in an agent payload."""

    model_config = ConfigDict(extra="forbid")
    task_id: str
    initial_state: dict[str, Any]
    target_state: list[StateAssertion] = Field(default_factory=list)
    invariants: list[OperationalInvariant] = Field(default_factory=list)
    required_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    required_evidence_ids: list[str] = Field(default_factory=list)
    action_effects: list[HiddenActionEffect] = Field(default_factory=list)
    max_cost: int = Field(default=40, ge=1)
    max_tool_calls: int = Field(default=30, ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OperationalEpisode(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode_id: str
    world_id: str
    task: TaskContract
    records: list[OperationalRecord]
    oracle: HiddenOracle
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_episode(self) -> "OperationalEpisode":
        if self.oracle.task_id != self.task.task_id:
            raise ValueError("task/oracle IDs must match")
        if self.task.world_id != self.world_id:
            raise ValueError("task/world IDs must match")

        action_names = [action.name for action in self.task.available_actions]
        if len(action_names) != len(set(action_names)):
            raise ValueError("public action names must be unique")
        public_actions = {action.name: action for action in self.task.available_actions}
        public_action_names = set(public_actions)
        permitted_systems = set(self.task.permitted_systems)
        invalid_action_systems = sorted(
            {
                action.system
                for action in self.task.available_actions
                if action.system not in permitted_systems
            }
        )
        if invalid_action_systems:
            raise ValueError(
                f"public actions reference non-permitted systems: {invalid_action_systems}"
            )

        required_actions = set(self.oracle.required_actions)
        forbidden_actions = set(self.oracle.forbidden_actions)
        unknown_oracle_actions = (required_actions | forbidden_actions) - public_action_names
        if unknown_oracle_actions:
            raise ValueError(
                f"oracle action constraints reference unknown actions: {sorted(unknown_oracle_actions)}"
            )
        contradictory_actions = required_actions & forbidden_actions
        if contradictory_actions:
            raise ValueError(
                f"actions cannot be both required and forbidden: {sorted(contradictory_actions)}"
            )

        for effect in self.oracle.action_effects:
            action = public_actions.get(effect.action_name)
            if action is None:
                raise ValueError(
                    f"oracle action effect references unknown action: {effect.action_name}"
                )
            unknown_parameters = set(effect.required_parameters) - set(action.parameter_names)
            if unknown_parameters:
                raise ValueError(
                    "oracle action effect references undeclared parameters for "
                    f"{effect.action_name}: {sorted(unknown_parameters)}"
                )

        record_ids = [record.record_id for record in self.records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("operational record IDs must be unique within an episode")
        unknown_evidence = set(self.oracle.required_evidence_ids) - set(record_ids)
        if unknown_evidence:
            raise ValueError(
                f"oracle requires evidence not present in episode records: {sorted(unknown_evidence)}"
            )

        invariant_ids = [invariant.invariant_id for invariant in self.oracle.invariants]
        if len(invariant_ids) != len(set(invariant_ids)):
            raise ValueError("invariant IDs must be unique within an episode")
        return self

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "task": self.task.model_dump(mode="json"),
            "records": [record.model_dump(mode="json") for record in self.records],
            "metadata": self.metadata,
        }


class ActionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sequence: int
    action_name: str
    kind: ActionKind
    system: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    cost: int = 0
    state_changes: dict[str, Any] = Field(default_factory=dict)
    side_effects: list[str] = Field(default_factory=list)
    forbidden: bool = False
    consequence_severity: float = 0.0


class EpisodeSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")
    conclusion: str = ""
    claimed_state: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class VerificationBreakdown(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: float = 0.0
    state: float = 0.0
    constraints: float = 0.0
    side_effects: float = 0.0
    process: float = 0.0
    efficiency: float = 0.0
    evidence: float = 0.0
    overall_reward: float = 0.0
    target_assertions_met: int = 0
    target_assertions_total: int = 0
    invariant_violations: list[str] = Field(default_factory=list)
    missing_required_actions: list[str] = Field(default_factory=list)
    forbidden_actions_taken: list[str] = Field(default_factory=list)
    missing_evidence_ids: list[str] = Field(default_factory=list)
    tool_calls: int = 0
    cost_spent: int = 0


class OperationalSuiteManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite_id: str
    version: str
    domains: list[WorldDomain]
    world_ids: list[str]
    task_ids: list[str]
    seed: int
    metadata: dict[str, Any] = Field(default_factory=dict)
