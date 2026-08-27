from __future__ import annotations

import copy
from typing import Any

from pydantic import Field

from investigation_world.foundry.models import RolloutTrace, TraceEvent
from investigation_world.trajectory.models import (
    AgentIdentity,
    ArtifactIdentity,
    CanonicalModel,
    EvaluationRecord,
    FailureClassification,
    HarnessIdentity,
    ModelIdentity,
    ProviderCallSummary,
    ProvenanceRecord,
    ResetIdentity,
    ResourceCallSummary,
    RuntimeIdentity,
    StateDigest,
    StateDigestScope,
    TaskIdentity,
    TerminationRecord,
    TrajectoryEvent,
    TrajectoryReference,
    TrajectoryV2,
    UsageTotals,
    VerifierIdentity,
    VisibilityClass,
    WorldIdentity,
    canonical_hash,
)

ROLLOUT_TRACE_ADAPTER_ID = "veritas.rollout-trace-to-trajectory-v2"
ROLLOUT_TRACE_ADAPTER_VERSION = "1"


class RolloutTraceAdapterContext(CanonicalModel):
    """Identity and accounting facts that are not representable in legacy RolloutTrace.

    ``None`` means unknown, not a default claim. Consumers such as Observatory should supply
    the identities they already know rather than encoding them into RolloutTrace metadata.
    """

    environment_id: str | None = None
    world_id: str | None = None
    world_version: str | None = None
    world_bundle: ArtifactIdentity | None = None
    portable_operational_contract: ArtifactIdentity | None = None
    model: ModelIdentity = Field(default_factory=ModelIdentity)
    agent: AgentIdentity = Field(default_factory=AgentIdentity)
    harness_id: str | None = None
    runtime_id: str | None = None
    verifier: VerifierIdentity = Field(default_factory=VerifierIdentity)
    reset_id: str | None = None
    reset_index: int | None = Field(default=None, ge=0)
    provider_calls: tuple[ProviderCallSummary, ...] = ()
    resource_calls: tuple[ResourceCallSummary, ...] | None = None
    observation_references: tuple[TrajectoryReference, ...] = ()
    evidence_references: tuple[TrajectoryReference, ...] = ()
    elapsed_s: float | None = Field(default=None, ge=0.0)
    terminated: bool | None = None
    truncated: bool | None = None
    failure: FailureClassification = Field(default_factory=FailureClassification)
    initial_state_scope: StateDigestScope = StateDigestScope.PUBLIC_SEMANTIC
    final_state_scope: StateDigestScope = StateDigestScope.PUBLIC_SEMANTIC
    provenance: tuple[ProvenanceRecord, ...] = ()
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)
    visibility: VisibilityClass = VisibilityClass.PUBLIC


def _state_digest(value: str | None, scope: StateDigestScope) -> StateDigest | None:
    if value is None:
        return None
    return StateDigest(digest=value, scope=scope)


def _event(event: TraceEvent) -> TrajectoryEvent:
    return TrajectoryEvent(
        step=event.step,
        event_type=event.event_type,
        payload=copy.deepcopy(event.payload),
        state_before=_state_digest(event.state_hash_before, StateDigestScope.PUBLIC_SEMANTIC),
        state_after=_state_digest(event.state_hash_after, StateDigestScope.PUBLIC_SEMANTIC),
        cost=event.cost,
        visibility=VisibilityClass.PUBLIC,
    )


def _resource_id(payload: dict[str, Any]) -> str | None:
    kwargs = payload.get("kwargs")
    if isinstance(kwargs, dict):
        for key in ("system", "record_id", "document_id", "case_id", "target_id", "resource_id"):
            value = kwargs.get(key)
            if value is not None:
                return f"{key}:{value}"
    args = payload.get("args")
    method = payload.get("method")
    if isinstance(args, list) and args:
        first = args[0]
        if method in {"open_record", "open_document", "case_status"}:
            return f"target:{first}"
        if method == "search_system":
            return f"system:{first}"
    return None


def _resource_call(index: int, event: TraceEvent) -> ResourceCallSummary:
    method = event.payload.get("method")
    operation = method if isinstance(method, str) and method else event.event_type
    success = event.payload.get("success")
    return ResourceCallSummary(
        call_index=index,
        resource_id=_resource_id(event.payload),
        operation=operation,
        success=success if isinstance(success, bool) else None,
        cost=event.cost,
        public_metadata={"source_event_step": event.step, "event_type": event.event_type},
    )


def _sum_complete(values: list[int | float | None]) -> int | float | None:
    if not values or any(value is None for value in values):
        return None
    return sum(value for value in values if value is not None)


def _usage(trace: RolloutTrace, context: RolloutTraceAdapterContext) -> UsageTotals:
    calls = context.provider_calls
    input_tokens = _sum_complete([item.input_tokens for item in calls])
    output_tokens = _sum_complete([item.output_tokens for item in calls])
    total_tokens = _sum_complete([item.total_tokens for item in calls])
    provider_cost = _sum_complete([item.cost for item in calls])
    resolved_total_tokens = int(total_tokens) if total_tokens is not None else None
    if resolved_total_tokens is None and input_tokens is not None and output_tokens is not None:
        resolved_total_tokens = int(input_tokens + output_tokens)
    if not calls:
        total_cost = trace.total_cost
    elif provider_cost is None:
        total_cost = None
    else:
        total_cost = trace.total_cost + float(provider_cost)
    return UsageTotals(
        input_tokens=int(input_tokens) if input_tokens is not None else None,
        output_tokens=int(output_tokens) if output_tokens is not None else None,
        total_tokens=resolved_total_tokens,
        provider_cost=float(provider_cost) if provider_cost is not None else None,
        environment_cost=trace.total_cost,
        total_cost=total_cost,
        elapsed_s=context.elapsed_s,
    )


def trajectory_v2_from_rollout_trace(
    trace: RolloutTrace,
    *,
    context: RolloutTraceAdapterContext | None = None,
) -> TrajectoryV2:
    """Deterministically adapt a legacy Foundry ``RolloutTrace`` into ``TrajectoryV2``.

    Legacy trace metadata is retained as evaluator/internal provenance metadata rather than being
    promoted to a buyer-safe field. Facts unavailable in ``RolloutTrace`` remain explicitly
    unknown unless supplied in ``RolloutTraceAdapterContext``.
    """

    ctx = context or RolloutTraceAdapterContext()
    events = tuple(_event(event) for event in trace.events)
    resource_calls = (
        ctx.resource_calls
        if ctx.resource_calls is not None
        else tuple(_resource_call(index, event) for index, event in enumerate(trace.events))
    )
    source_provenance = ProvenanceRecord(
        source_kind="foundry.rollout_trace",
        source_id=trace.trace_id,
        source_version=None,
        source_digest=canonical_hash(trace.model_dump(mode="json")),
        adapter_id=ROLLOUT_TRACE_ADAPTER_ID,
        adapter_version=ROLLOUT_TRACE_ADAPTER_VERSION,
        visibility=VisibilityClass.BUYER_SAFE,
        private_metadata={"rollout_trace_metadata": copy.deepcopy(trace.metadata)},
    )
    verifier = ctx.verifier
    return TrajectoryV2(
        world=WorldIdentity(
            environment_id=ctx.environment_id,
            environment_version=trace.environment_version,
            world_id=ctx.world_id,
            world_version=ctx.world_version,
            world_bundle=ctx.world_bundle,
            portable_operational_contract=ctx.portable_operational_contract,
        ),
        task=TaskIdentity(
            task_id=trace.task_id,
            taskset_version=trace.taskset_version,
            split=trace.split.value,
        ),
        model=ctx.model,
        agent=ctx.agent,
        harness=HarnessIdentity(harness_id=ctx.harness_id, version=trace.harness_version),
        runtime=RuntimeIdentity(runtime_id=ctx.runtime_id, version=trace.runtime_version),
        verifier=verifier,
        reset=ResetIdentity(
            seed=trace.task_seed,
            reset_id=ctx.reset_id,
            reset_index=ctx.reset_index,
        ),
        initial_state=StateDigest(digest=trace.initial_state_hash, scope=ctx.initial_state_scope),
        events=events,
        provider_calls=ctx.provider_calls,
        resource_calls=resource_calls,
        observation_references=ctx.observation_references,
        evidence_references=ctx.evidence_references,
        usage=_usage(trace, ctx),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores=dict(sorted(trace.verifier_components.items())),
            reward=trace.total_reward,
        ),
        termination=TerminationRecord(
            reason=trace.termination_reason,
            terminated=ctx.terminated,
            truncated=ctx.truncated,
        ),
        final_state=_state_digest(trace.final_state_hash, ctx.final_state_scope),
        failure=ctx.failure,
        capability_tags=tuple(trace.capability_tags),
        provenance=(source_provenance, *ctx.provenance),
        visibility=ctx.visibility,
        public_metadata=copy.deepcopy(ctx.public_metadata),
        private_metadata=copy.deepcopy(ctx.private_metadata),
    )
