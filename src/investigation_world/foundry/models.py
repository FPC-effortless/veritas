from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator


class DistributionSplit(StrEnum):
    TRAIN = "train"
    IID_TEST = "iid_test"
    OOD = "ood"
    ADVERSARIAL = "adversarial"


class MutationKind(StrEnum):
    REORDER_RECORDS = "reorder_records"
    INJECT_DISTRACTOR = "inject_distractor"
    REDACT_OPTIONAL_FIELD = "redact_optional_field"
    TIGHTEN_BUDGET = "tighten_budget"
    TOOL_FAILURE = "tool_failure"
    PERMISSION_CHANGE = "permission_change"


class DifficultyVector(BaseModel):
    entities: int = Field(default=1, ge=0)
    tools: int = Field(default=1, ge=0)
    steps: int = Field(default=1, ge=0)
    distractors: int = Field(default=0, ge=0)
    missing_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    conflict_probability: float = Field(default=0.0, ge=0.0, le=1.0)
    dependency_depth: int = Field(default=1, ge=0)
    budget_ratio: float = Field(default=1.0, gt=0.0)
    stochasticity: float = Field(default=0.0, ge=0.0, le=1.0)
    adversarial_pressure: float = Field(default=0.0, ge=0.0, le=1.0)


CAPABILITY_CONTRACT_DIGEST_LENGTH = 20
"""Hex characters retained from the sha256 digest of a contract payload.

Truncation to 80 bits is deliberate and best-effort, not a collision guarantee;
it matches the `CGRAPH-...` scheme used for `CapabilityGraph.graph_id`.
"""

CAPABILITY_CONTRACT_DIGEST_PREFIX = "CCONTRACT"


class CapabilityContract(BaseModel):
    capability_id: str
    version: str = "1"
    objective: str
    subcapabilities: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)
    hard_invariants: list[str] = Field(default_factory=list)
    transfer_targets: list[str] = Field(default_factory=list)
    content_digest: str = ""

    @model_validator(mode="after")
    def validate_content_digest(self) -> "CapabilityContract":
        expected = capability_contract_digest(self)
        if self.content_digest and self.content_digest != expected:
            raise ValueError(
                "content_digest does not match capability contract contents"
            )
        # `CapabilityContract` is not frozen, so a plain attribute assignment is safe
        # here and does not need the `object.__setattr__` escape hatch used by the
        # frozen `CapabilityGraph`/`MaturityPolicy` models.
        self.content_digest = expected
        return self


def capability_contract_digest_payload(contract: CapabilityContract) -> dict[str, Any]:
    """Deterministic content payload for a capability contract.

    Covers every content-bearing field of the declaration and deliberately excludes
    `content_digest` itself, so the identifier never feeds its own computation.
    The contract is a public declaration; this payload carries no private scenario
    identifier, hidden label, oracle row, or decrypted bundle.
    """
    return {
        "capability_id": contract.capability_id,
        "version": contract.version,
        "objective": contract.objective,
        "subcapabilities": list(contract.subcapabilities),
        "success_conditions": list(contract.success_conditions),
        "failure_conditions": list(contract.failure_conditions),
        "hard_invariants": list(contract.hard_invariants),
        "transfer_targets": list(contract.transfer_targets),
    }


def capability_contract_digest(contract: CapabilityContract) -> str:
    """Content-derived identifier for a capability contract.

    Deterministic across processes, Python versions, and insertion order: the payload
    is canonicalized by `stable_hash` (sorted-keys JSON, `default=str`).
    """
    digest = stable_hash(capability_contract_digest_payload(contract))
    return (
        f"{CAPABILITY_CONTRACT_DIGEST_PREFIX}-"
        f"{digest[:CAPABILITY_CONTRACT_DIGEST_LENGTH].upper()}"
    )


class MutationLineage(BaseModel):
    mutation_id: str
    kind: MutationKind
    parent_task_id: str
    seed: int
    parameters: dict[str, Any] = Field(default_factory=dict)


class FoundryTaskMetadata(BaseModel):
    task_id: str
    split: DistributionSplit
    capability_tags: list[str]
    difficulty: DifficultyVector
    seed: int
    taskset_version: str
    harness_version: str = "unspecified"
    runtime_version: str
    parent_task_id: str | None = None
    mutation_lineage: list[MutationLineage] = Field(default_factory=list)
    generator_parameters: dict[str, Any] = Field(default_factory=dict)


class TraceEvent(BaseModel):
    step: int = Field(ge=0)
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    state_hash_before: str | None = None
    state_hash_after: str | None = None
    cost: float = Field(default=0.0, ge=0.0)


class RolloutTrace(BaseModel):
    trace_id: str
    environment_version: str
    task_id: str
    task_seed: int
    split: DistributionSplit
    capability_tags: list[str] = Field(default_factory=list)
    taskset_version: str
    harness_version: str
    runtime_version: str
    initial_state_hash: str
    events: list[TraceEvent] = Field(default_factory=list)
    verifier_components: dict[str, float] = Field(default_factory=dict)
    total_reward: float = 0.0
    final_state_hash: str | None = None
    termination_reason: str = "unknown"
    total_cost: float = Field(default=0.0, ge=0.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class StateSnapshot(BaseModel):
    trace_id: str
    step: int = Field(ge=0)
    state_hash: str
    state_payload: dict[str, Any] | None = None


class CounterfactualBranch(BaseModel):
    branch_id: str
    parent_trace_id: str
    branch_step: int = Field(ge=0)
    snapshot_hash: str
    alternate_action: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


def stable_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()
