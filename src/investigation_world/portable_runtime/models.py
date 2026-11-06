from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PortableRuntimeFailureCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    INVALID_ACTION = "invalid_action"
    INVALID_ACTION_INPUT = "invalid_action_input"
    INVALID_OPERATION = "invalid_operation"
    INVALID_OPERATION_INPUT = "invalid_operation_input"
    ACTION_REJECTED = "action_rejected"
    PRECONDITION_REJECTED = "precondition_rejected"
    BUDGET_EXHAUSTED = "budget_exhausted"
    RESOURCE_NOT_FOUND = "resource_not_found"
    EPISODE_TERMINATED = "episode_terminated"
    EPISODE_TRUNCATED = "episode_truncated"
    INVALID_SUBMISSION = "invalid_submission"
    CONTRACT_SCHEMA_UNSUPPORTED = "contract_schema_unsupported"
    OUTPUT_SCHEMA_VIOLATION = "output_schema_violation"
    INTERNAL_RUNTIME_ERROR = "internal_runtime_error"


class PortableInvocationKind(StrEnum):
    ACTION = "action"
    OPERATION = "operation"


class PortableStepRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: PortableInvocationKind = PortableInvocationKind.ACTION
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class PortableSubmission(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conclusion: str = ""
    claimed_state: dict[str, Any] = Field(default_factory=dict)
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class PortableFailureStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: PortableRuntimeFailureCode
    message: str
    operation: str | None = None
    action_name: str | None = None
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class PortableBudgetResourceStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resource: str
    unit: str
    maximum: int = Field(ge=0)
    used: int = Field(ge=0)
    remaining: int = Field(ge=0)
    exhausted: bool = False


class PortableBudgetStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    resources: tuple[PortableBudgetResourceStatus, ...]
    exhausted: bool = False
    exhausted_resources: tuple[str, ...] = ()


class PortableRewardComponents(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    outcome: float = Field(ge=0.0, le=1.0)
    state: float = Field(ge=0.0, le=1.0)
    constraints: float = Field(ge=0.0, le=1.0)
    side_effects: float = Field(ge=0.0, le=1.0)
    process: float = Field(ge=0.0, le=1.0)
    efficiency: float = Field(ge=0.0, le=1.0)
    evidence: float = Field(ge=0.0, le=1.0)


class PortableResetResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: dict[str, Any]
    state_digest: str
    budget_status: PortableBudgetStatus


class PortableStepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    observation: Any = None
    reward: float | None = Field(default=None, ge=0.0, le=1.0)
    reward_components: PortableRewardComponents | None = None
    terminated: bool
    truncated: bool
    state_digest: str
    budget_status: PortableBudgetStatus
    failure: PortableFailureStatus | None = None
