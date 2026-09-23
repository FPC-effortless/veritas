from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import (
    CAPABILITY_CONTRACT_DIGEST_LENGTH,
    CAPABILITY_CONTRACT_DIGEST_PREFIX,
)

_CAPABILITY_CONTRACT_DIGEST_PATTERN = re.compile(
    r"^"
    + re.escape(CAPABILITY_CONTRACT_DIGEST_PREFIX)
    + r"-[0-9A-F]{" + str(CAPABILITY_CONTRACT_DIGEST_LENGTH) + r"}$"
)
"""Exact format of the G-01 digest a binding may carry.

`CapabilityContract.content_digest` is `CCONTRACT-` plus 20 uppercase hex characters
(80 bits of sha256). A binding's digest must be one of those, produced by
`capability_contract_digest`, never hand-written.
"""


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


class AssertionComparison(StrEnum):
    EQUAL = "equal"
    NOT_EQUAL = "not_equal"
    LESS_THAN = "less_than"
    LESS_THAN_OR_EQUAL = "less_than_or_equal"
    GREATER_THAN = "greater_than"
    GREATER_THAN_OR_EQUAL = "greater_than_or_equal"
    CONTAINS = "contains"
    IN = "in"


class OperationalEntity(BaseModel):
    """Persistent entity shared across one or more operational domains."""

    model_config = ConfigDict(extra="forbid")
    entity_id: str
    entity_type: str
    label: str = ""
    domains: list[WorldDomain] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class OperationalRelation(BaseModel):
    """Typed relationship connecting persistent operational entities."""

    model_config = ConfigDict(extra="forbid")
    relation_id: str
    source_entity_id: str
    relation_type: str
    target_entity_id: str
    domains: list[WorldDomain] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)


class OperationalRecord(BaseModel):
    """One agent-visible record projected from a domain system.

    Temporal/provenance fields make stale, conflicting and authority-weighted
    evidence first-class without exposing evaluator truth.
    """

    model_config = ConfigDict(extra="forbid")
    record_id: str
    system: str
    record_type: str
    object_id: str
    fields: dict[str, Any] = Field(default_factory=dict)
    related_object_ids: list[str] = Field(default_factory=list)
    searchable_text: str = ""
    observed_at: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
    source_authority: Literal["low", "medium", "high", "authoritative"] = "medium"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    freshness: Literal["current", "recent", "stale", "historical", "unknown"] = "unknown"
    provenance_ids: list[str] = Field(default_factory=list)


class StateAssertion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    object_id: str
    field_name: str
    expected_value: Any
    tolerance: float | None = Field(default=None, ge=0.0)
    comparison: AssertionComparison = AssertionComparison.EQUAL

    def key(self) -> str:
        return f"{self.object_id}.{self.field_name}"


class OperationalInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invariant_id: str
    description: str
    assertion: StateAssertion
    severity: Literal["low", "medium", "high", "critical"] = "high"
    scope: Literal["final", "always"] = "final"


def episode_contract_terms(episode: OperationalEpisode | HiddenOracle) -> tuple[str, ...]:
    """Reference keys on an episode that a contract coverage check can name.

    Coverage, not equivalence. `CapabilityContract.success_conditions`/`hard_invariants` are
    free-form prose `list[str]`; `HiddenOracle.target_state` is `list[StateAssertion]` and
    `invariants` is `list[OperationalInvariant]`. The two sides are not mechanically equatable,
    and a plausible-looking string match between prose and structured assertions would be a
    check that passes vacuously and fails silently. So the only decidable coverage question is
    an existence check: is each episode-side reference key named by the contract's prose?

    These keys are identifiers (`invariant_id`, `object_id.field_name`), not oracle values, so
    enumerating them leaks no private state. Value-level comparison between a success condition
    and a `StateAssertion` is never performed or implied, and no contract or oracle content is
    altered.
    """
    oracle = episode.oracle if isinstance(episode, OperationalEpisode) else episode
    terms: list[str] = [invariant.invariant_id for invariant in oracle.invariants]
    terms.extend(assertion.key() for assertion in oracle.target_state)
    return tuple(dict.fromkeys(terms))


def capability_binding_from_contract(
    contract: Any,
    episode: OperationalEpisode | HiddenOracle | None = None,
    *,
    coverage_terms: tuple[str, ...] | None = None,
) -> CapabilityBinding:
    """Build a binding from a `CapabilityContract`, failing closed on identity mismatch.

    The digest is always recomputed from the contract's own content and compared to the
    contract's declared digest: a mismatch raises `ValueError` and is never silently accepted,
    mirroring `CapabilityContract.validate_content_digest`. This is the explicit constructor
    path required by the Work Contract.

    When an `episode` is supplied, the advisory coverage findings are recorded on the returned
    binding as `binding_gaps` (see `episode_contract_terms`). `episode` accepts the
    `OperationalEpisode` being constructed, or its `HiddenOracle` directly, so a catalog can run
    the real check without needing a fully constructed episode first. Gaps are a deliverable
    finding for a downstream lane (G-07/G-09/G-12), never a failure and never a reason to weaken
    an oracle or a catalog. `coverage_terms` overrides the term universe used by that check; by
    default it is the contract's own `success_conditions` plus `hard_invariants`.

    The contract argument is typed loosely on purpose: `operational/**` does not import
    `foundry/**` types, so the caller supplies any object exposing the eight content-bearing
    contract fields plus `content_digest`.
    """
    from investigation_world.foundry.models import (
        CapabilityContract,
        capability_contract_digest,
    )

    if not isinstance(contract, CapabilityContract):
        raise ValueError("capability binding requires a real CapabilityContract object")
    derived = capability_contract_digest(contract)
    if contract.content_digest != derived:
        raise ValueError(
            "capability binding content_digest does not match capability contract contents"
        )

    gaps: list[str] = []
    if episode is not None:
        oracle = episode.oracle if isinstance(episode, OperationalEpisode) else episode
        terms = set(
            coverage_terms
            if coverage_terms is not None
            else [*contract.success_conditions, *contract.hard_invariants]
        )
        for reference in episode_contract_terms(oracle):
            if reference not in terms:
                gaps.append(
                    f"{reference} is not named by the {contract.capability_id} contract"
                )
    return CapabilityBinding(
        capability_id=contract.capability_id,
        content_digest=derived,
        binding_gaps=tuple(gaps),
    )


class CapabilityBinding(BaseModel):
    """Reference from an episode or world to the `CapabilityContract` it was built to exercise.

    Declaration metadata only: the binding carries the G-01 capability identity
    (`capability_id` + `content_digest`) and never participates in execution, verification,
    scoring, qualification, or release decisions. It references an identity computed by
    `investigation_world.foundry.models.capability_contract_digest`; it mints no identity of
    its own, so there is exactly one capability identity scheme in the repository.

    The payload is public declaration content, mirroring `CapabilityContract`: it holds no
    private scenario identifier, hidden label, oracle row, or decrypted bundle, and it must
    never be populated from `HiddenOracle` state.

    `binding_gaps` records contract↔oracle coverage findings. It is advisory, not a failure:
    the coverage check is an existence check only (see `OperationalEpisode.validate_episode`)
    and a recorded gap is a deliverable finding for a downstream lane (G-07/G-09/G-12), never a
    reason to weaken an oracle or a catalog. Adding a gap never changes any digest: the field is
    excluded from the binding's own identity payload, which covers exactly the two identity
    fields, so findings can accumulate without churning episode identity.
    """

    model_config = ConfigDict(extra="forbid")

    capability_id: str
    content_digest: str
    binding_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_capability_binding(self) -> "CapabilityBinding":
        if not self.capability_id.strip():
            raise ValueError("capability binding requires a non-empty capability_id")
        if not _CAPABILITY_CONTRACT_DIGEST_PATTERN.match(self.content_digest):
            raise ValueError(
                "capability binding content_digest must be a well-formed "
                f"{CAPABILITY_CONTRACT_DIGEST_PREFIX}-<hex> value computed by "
                "capability_contract_digest, not a hand-written string"
            )
        return self


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
    """Verifier-only transition plus the system-observable response to that transition.

    Effects can now depend on prior state and prior actions. Failed preconditions
    produce an observable system response without mutating hidden ground truth.
    """

    model_config = ConfigDict(extra="forbid")
    action_name: str
    required_parameters: dict[str, Any] = Field(default_factory=dict)
    required_state: list[StateAssertion] = Field(default_factory=list)
    required_prior_actions: list[str] = Field(default_factory=list)
    set_state: dict[str, Any] = Field(default_factory=dict)
    observable_result: dict[str, Any] = Field(default_factory=dict)
    blocked_observable_result: dict[str, Any] = Field(default_factory=dict)
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
    required_action_order: list[str] = Field(default_factory=list)
    required_action_counts: dict[str, int] = Field(default_factory=dict)
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
    capability: CapabilityBinding | None = None

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
        ordered_actions = set(self.oracle.required_action_order)
        counted_actions = set(self.oracle.required_action_counts)
        forbidden_actions = set(self.oracle.forbidden_actions)
        unknown_oracle_actions = (
            required_actions | ordered_actions | counted_actions | forbidden_actions
        ) - public_action_names
        if unknown_oracle_actions:
            raise ValueError(
                f"oracle action constraints reference unknown actions: {sorted(unknown_oracle_actions)}"
            )
        contradictory_actions = (required_actions | counted_actions) & forbidden_actions
        if contradictory_actions:
            raise ValueError(
                f"actions cannot be both required and forbidden: {sorted(contradictory_actions)}"
            )
        if any(count < 1 for count in self.oracle.required_action_counts.values()):
            raise ValueError("required action counts must be >= 1")

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
            unknown_prerequisites = set(effect.required_prior_actions) - public_action_names
            if unknown_prerequisites:
                raise ValueError(
                    "oracle action effect references unknown prior actions for "
                    f"{effect.action_name}: {sorted(unknown_prerequisites)}"
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
        # `capability` needs no extra check here. It is declaration metadata, and
        # `CapabilityBinding.validate_capability_binding` already fails closed on both identity
        # conditions: a non-empty `capability_id` and a well-formed G-01 `content_digest`. The
        # advisory contract↔oracle coverage check is recorded as `binding_gaps` at the explicit
        # construction site (`capability_binding_from_contract`), not re-run here: re-running it
        # could only either raise on a gap this lane is required to record, or duplicate a
        # result already carried on the binding. See `docs/experience/operational-capability-binding.md`.
        return self

    def public_payload(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "world_id": self.world_id,
            "task": self.task.model_dump(mode="json"),
            "records": [record.model_dump(mode="json") for record in self.records],
            "metadata": self.metadata,
            "capability": (
                self.capability.model_dump(mode="json") if self.capability is not None else None
            ),
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
    effect_applied: bool = True
    blocked: bool = False
    blocked_reason: str | None = None


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
    process_violations: list[str] = Field(default_factory=list)


class OperationalSuiteManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    suite_id: str
    version: str
    domains: list[WorldDomain]
    world_ids: list[str]
    task_ids: list[str]
    seed: int
    metadata: dict[str, Any] = Field(default_factory=dict)
