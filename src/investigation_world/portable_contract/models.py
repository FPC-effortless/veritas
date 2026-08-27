from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.portable_contract.identity import (
    canonical_json_bytes,
    content_id,
)


class PortableVisibility(StrEnum):
    PUBLIC = "public"
    EVALUATOR_PRIVATE = "evaluator_private"


class InteractionMode(StrEnum):
    RETRIEVAL = "retrieval"
    ACTION = "action"
    SUBMISSION = "submission"


class FrozenContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class PortableProvenance(FrozenContractModel):
    source_model: str
    source_commit: str
    source_model_git_blob_sha1: str
    source_runtime_git_blob_sha1: str
    source_verifier_git_blob_sha1: str
    compiler: str
    compiler_version: str


class PortableTaskIdentity(FrozenContractModel):
    episode_id: str
    world_id: str
    task_id: str
    domain: str


class PortableStateAssertion(FrozenContractModel):
    object_id: str
    field_name: str
    expected_value: Any
    tolerance: float | None = Field(default=None, ge=0.0)
    comparison: str


class PortableInvariant(FrozenContractModel):
    invariant_id: str
    description: str
    assertion: PortableStateAssertion
    severity: str
    scope: str
    trajectory_wide: bool

    @model_validator(mode="after")
    def validate_scope(self) -> "PortableInvariant":
        if self.scope not in {"final", "always"}:
            raise ValueError(f"unsupported invariant scope: {self.scope}")
        if self.trajectory_wide != (self.scope == "always"):
            raise ValueError("trajectory_wide must exactly reflect invariant scope")
        return self


class PortableStateContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.PUBLIC
    observation_schema: dict[str, Any]
    state_snapshot_agent_visible: bool = False
    hidden_state_updates_agent_visible: bool = False


class PortableResourceLimit(FrozenContractModel):
    resource: str
    unit: str
    maximum: int = Field(ge=0)
    exhaustion_rule: str


class PortableResourceCharge(FrozenContractModel):
    resource: str
    unit: str
    amount: int = Field(ge=0)


class PortableBudgetContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    limits: tuple[PortableResourceLimit, ...]

    @model_validator(mode="after")
    def validate_units(self) -> "PortableBudgetContract":
        seen: dict[str, str] = {}
        for limit in self.limits:
            previous = seen.get(limit.resource)
            if previous is not None:
                if previous != limit.unit:
                    raise ValueError(
                        "budget resource cannot merge incompatible units: "
                        f"{limit.resource} has {previous!r} and {limit.unit!r}"
                    )
                raise ValueError(f"duplicate budget resource: {limit.resource}")
            seen[limit.resource] = limit.unit
        return self


class PortableActionDefinition(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.PUBLIC
    name: str
    kind: str
    system: str
    description: str
    parameter_names: tuple[str, ...]
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    cost: int = Field(ge=0)
    charges: tuple[PortableResourceCharge, ...]
    interaction_mode: InteractionMode = InteractionMode.ACTION
    missing_parameter_behavior: str = "raise_value_error"
    additional_parameters_allowed: bool = True


class PortableEvidenceRecord(FrozenContractModel):
    record_id: str
    system: str
    record_type: str
    object_id: str
    fields: dict[str, Any]
    related_object_ids: tuple[str, ...]
    searchable_text: str
    observed_at: str | None
    valid_from: str | None
    valid_to: str | None
    source_authority: str
    confidence: float
    freshness: str
    provenance_ids: tuple[str, ...]


class PortableEvidenceContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.PUBLIC
    records: tuple[PortableEvidenceRecord, ...]


class PortableSearchContract(FrozenContractModel):
    tokenization: str = "whitespace_casefold"
    match_rule: str = "all_non_empty_terms_must_match"
    score_rule: str = "sum_term_occurrence_counts"
    ordering: tuple[str, ...] = ("score_desc", "record_id_asc")
    minimum_limit: int = 1
    maximum_limit: int = 100
    empty_query_behavior: str = "return_empty"


class PortableRuntimeOperation(FrozenContractModel):
    name: str
    interaction_mode: InteractionMode
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    charges: tuple[PortableResourceCharge, ...] = ()
    permission_failure_behavior: str | None = None
    permission_check_precedes_open_check: bool = False
    missing_resource_behavior: str | None = None


class PortableTerminationContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.PUBLIC
    terminal_operation: str = "submit"
    closes_after_evaluation: bool = True
    post_terminal_behavior: str = "raise_value_error_episode_already_submitted"
    budget_exhaustion_behavior: str = (
        "raise_value_error_investigation_budget_exhausted_without_closing"
    )


class PortableRuntimeContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.PUBLIC
    stateful: bool = True
    deterministic_reset: bool = True
    interaction_modes: tuple[InteractionMode, ...]
    builtin_operations: tuple[PortableRuntimeOperation, ...]
    search: PortableSearchContract
    termination: PortableTerminationContract


class PortableTransitionContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    declaration_index: int = Field(ge=0)
    action_name: str
    required_parameters: dict[str, Any]
    required_state: tuple[PortableStateAssertion, ...]
    required_prior_actions: tuple[str, ...]
    set_state: dict[str, Any]
    observable_result: dict[str, Any]
    blocked_observable_result: dict[str, Any]
    emitted_side_effects: tuple[str, ...]
    forbidden: bool
    consequence_severity: float = Field(ge=0.0, le=1.0)
    parameter_match_rule: str = "required_parameter_subset_exact_equality"
    selection_rule: str = "first_matching_transition_in_declaration_order"
    prior_action_rule: str = "ordered_subsequence_of_successful_unblocked_actions"
    failed_precondition_default_result: dict[str, Any] = Field(
        default_factory=lambda: {
            "accepted": False,
            "reason": "precondition_failed",
        }
    )


class PortableProcessContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    required_actions: tuple[str, ...]
    forbidden_actions: tuple[str, ...]
    required_action_order: tuple[str, ...]
    required_action_counts: dict[str, int]
    effective_event_rule: str = "effect_applied_and_not_blocked"


class SemanticStateProjection(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    initial_state: dict[str, Any]
    target_assertions: tuple[PortableStateAssertion, ...]
    invariants: tuple[PortableInvariant, ...]
    state_key_rule: str = "object_id_dot_field_name"


class PortableRewardComponent(FrozenContractModel):
    name: str
    weight: float = Field(ge=0.0, le=1.0)


class PortableRewardContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    components: tuple[PortableRewardComponent, ...]
    aggregate_rule: str = "weighted_sum_clamped_0_1"
    output_round_decimal_places: int = 6

    @model_validator(mode="after")
    def validate_weights(self) -> "PortableRewardContract":
        total = sum(component.weight for component in self.components)
        if abs(total - 1.0) > 1e-12:
            raise ValueError(f"reward component weights must sum to 1.0, got {total}")
        names = [component.name for component in self.components]
        if len(names) != len(set(names)):
            raise ValueError("reward component names must be unique")
        return self


class PortableEvaluatorBinding(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    entrypoint: str
    semantics_id: str
    source_git_blob_sha1: str
    deterministic: bool
    reward: PortableRewardContract


class PortablePrivateContract(FrozenContractModel):
    visibility: PortableVisibility = PortableVisibility.EVALUATOR_PRIVATE
    oracle_task_id: str
    semantic_state: SemanticStateProjection
    transitions: tuple[PortableTransitionContract, ...]
    transition_selection_rule: str = "first_matching_transition_in_declaration_order"
    unmatched_transition_result: dict[str, Any] = Field(
        default_factory=lambda: {
            "accepted": False,
            "reason": "invalid_parameters",
        }
    )
    unmatched_transition_blocked_reason: str = "no_matching_transition"
    action_without_transition_behavior: str = "successful_noop_effect_applied"
    process: PortableProcessContract
    required_evidence_ids: tuple[str, ...]
    budgets: PortableBudgetContract
    reset_identity: str
    evaluator: PortableEvaluatorBinding
    oracle_metadata: dict[str, Any]

    @model_validator(mode="after")
    def validate_transition_order(self) -> "PortablePrivateContract":
        indices = [transition.declaration_index for transition in self.transitions]
        if indices != list(range(len(indices))):
            raise ValueError("transition declaration_index values must be contiguous and ordered")
        return self


class PortablePublicContract(FrozenContractModel):
    schema_version: str
    public_id: str = ""
    visibility: PortableVisibility = PortableVisibility.PUBLIC
    identity: PortableTaskIdentity
    provenance: PortableProvenance
    objective: str
    role: str
    permitted_systems: tuple[str, ...]
    constraints: tuple[str, ...]
    success_description: str
    task_metadata: dict[str, Any]
    episode_metadata: dict[str, Any]
    state: PortableStateContract
    actions: tuple[PortableActionDefinition, ...]
    evidence: PortableEvidenceContract
    runtime: PortableRuntimeContract

    @model_validator(mode="after")
    def bind_public_identity(self) -> "PortablePublicContract":
        payload = self.model_dump(mode="python", exclude={"public_id"})
        expected = content_id("poc-public-v1", payload)
        if self.public_id and self.public_id != expected:
            raise ValueError("public_id does not match public contract content")
        object.__setattr__(self, "public_id", expected)
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="python"))


class PortableOperationalContract(FrozenContractModel):
    schema_version: str
    contract_id: str = ""
    public: PortablePublicContract
    private: PortablePrivateContract

    @model_validator(mode="after")
    def validate_and_bind_contract(self) -> "PortableOperationalContract":
        if self.public.schema_version != self.schema_version:
            raise ValueError("public and full contract schema versions must match")
        if self.private.oracle_task_id != self.public.identity.task_id:
            raise ValueError("public task identity and private oracle task identity must match")

        action_names = [action.name for action in self.public.actions]
        if len(action_names) != len(set(action_names)):
            raise ValueError("portable public action names must be unique")
        action_name_set = set(action_names)
        transition_actions = {transition.action_name for transition in self.private.transitions}
        if not transition_actions.issubset(action_name_set):
            raise ValueError("private transitions reference unknown public actions")

        process_actions = (
            set(self.private.process.required_actions)
            | set(self.private.process.forbidden_actions)
            | set(self.private.process.required_action_order)
            | set(self.private.process.required_action_counts)
        )
        if not process_actions.issubset(action_name_set):
            raise ValueError("private process rules reference unknown public actions")

        evidence_ids = {record.record_id for record in self.public.evidence.records}
        if not set(self.private.required_evidence_ids).issubset(evidence_ids):
            raise ValueError("private evidence requirements reference unknown public evidence")

        limits = {
            (limit.resource, limit.unit)
            for limit in self.private.budgets.limits
        }
        all_charges = [
            charge
            for action in self.public.actions
            for charge in action.charges
        ] + [
            charge
            for operation in self.public.runtime.builtin_operations
            for charge in operation.charges
        ]
        if any((charge.resource, charge.unit) not in limits for charge in all_charges):
            raise ValueError("runtime charge references an undeclared budget resource/unit")

        expected_reset = content_id(
            "poc-reset-v1",
            {
                "identity": self.public.identity.model_dump(mode="python"),
                "initial_state": self.private.semantic_state.initial_state,
            },
        )
        if self.private.reset_identity != expected_reset:
            raise ValueError("reset_identity does not match deterministic initial state")

        payload = self.model_dump(mode="python", exclude={"contract_id"})
        expected = content_id("poc-v1", payload)
        if self.contract_id and self.contract_id != expected:
            raise ValueError("contract_id does not match portable contract content")
        object.__setattr__(self, "contract_id", expected)
        return self

    def canonical_bytes(self) -> bytes:
        return canonical_json_bytes(self.model_dump(mode="python"))

    def public_bytes(self) -> bytes:
        return self.public.canonical_bytes()
