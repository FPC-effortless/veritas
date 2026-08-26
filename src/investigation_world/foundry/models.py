from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


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


class CapabilityContract(BaseModel):
    capability_id: str
    version: str = "1"
    objective: str
    subcapabilities: list[str] = Field(default_factory=list)
    success_conditions: list[str] = Field(default_factory=list)
    failure_conditions: list[str] = Field(default_factory=list)
    hard_invariants: list[str] = Field(default_factory=list)
    transfer_targets: list[str] = Field(default_factory=list)


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
