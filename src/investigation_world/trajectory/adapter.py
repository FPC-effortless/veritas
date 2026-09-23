from __future__ import annotations

import copy
from typing import Protocol
from typing import TYPE_CHECKING
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
from investigation_world.trajectory.reverify.operational import (
    current_operational_verifier_binding,
)

if TYPE_CHECKING:
    from investigation_world.operational.models import ActionEvent
    from investigation_world.operational.runtime import OperationalRuntime

ROLLOUT_TRACE_ADAPTER_ID = "veritas.rollout-trace-to-trajectory-v2"
ROLLOUT_TRACE_ADAPTER_VERSION = "1"
OPERATIONAL_RUNTIME_ADAPTER_ID = "veritas.operational-runtime-to-trajectory-v2"
OPERATIONAL_RUNTIME_ADAPTER_VERSION = "1"


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


class _ResourceCallEvent(Protocol):
    """The event shape ``_resource_call`` reads.

    ``TraceEvent`` (foundry) and ``TrajectoryEvent`` (trajectory) both carry the four members this
    helper reads, so one definition serves both adapters instead of a second typed helper.
    """

    @property
    def payload(self) -> dict[str, Any]:
        ...

    @property
    def step(self) -> int:
        ...

    @property
    def event_type(self) -> str:
        ...

    @property
    def cost(self) -> float | None:
        ...


def _resource_call(index: int, event: _ResourceCallEvent) -> ResourceCallSummary:
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


class OperationalRuntimeAdapterContext(CanonicalModel):
    """Identity and accounting facts that ``OperationalRuntime`` cannot supply.

    Mirrors :class:`RolloutTraceAdapterContext`: ``None`` means *unknown*, not a default claim.
    Everything an ``ActionEvent`` cannot represent stays here, so the adapter never infers
    model/agent/harness identity, provider accounting, reset identity, or failure attribution.

    Two fields are mandatory because the runtime does not retain them after ``submit()`` and
    because ``TrajectoryV2`` requires an ``original_evaluation``:

    - ``breakdown`` — the ``VerificationBreakdown`` returned by ``runtime.submit(...)``. The
      adapter never re-scores, so the caller supplies the single evaluation the runtime already
      performed (see the note on ``submission`` below for why it must carry both).
    - ``submission`` — the ``EpisodeSubmission`` the caller passed to ``submit(...)``. The
      reverification engine requires exactly one ``submit`` event whose payload *is* this
      submission, so the adapter emits it from this context rather than inventing one; the
      runtime's own ``submit()`` does not record an ``ActionEvent``.

    ``verifier`` is the one mandatory *identity* case. ``TrajectoryV2.validate_trajectory``
    requires ``original_evaluation.verifier == trajectory.verifier``; when the caller does not
    name a verifier, the adapter uses the statically authorized operational binding
    (:func:`current_operational_verifier_binding`) instead of inventing one.

    State-digest scopes default to :attr:`StateDigestScope.SEMANTIC`, not the legacy adapter's
    ``PUBLIC_SEMANTIC``: operational state is seeded from ``episode.oracle.initial_state``,
    which is private-by-construction. ``initial_state_digest``/``final_state_digest`` override
    the computed digest outright and win over ``scope``, so a caller that already holds the
    exact digest the reverification engine requires can pass it through verbatim.
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
    verifier: VerifierIdentity | None = None
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
    breakdown: Any = None
    submission: Any = None
    initial_state_digest: str | None = None
    final_state_digest: str | None = None
    initial_state_scope: StateDigestScope = StateDigestScope.SEMANTIC
    final_state_scope: StateDigestScope = StateDigestScope.SEMANTIC
    provenance: tuple[ProvenanceRecord, ...] = ()
    public_metadata: dict[str, Any] = Field(default_factory=dict)
    private_metadata: dict[str, Any] = Field(default_factory=dict)
    visibility: VisibilityClass = VisibilityClass.PUBLIC


_REWARD_COMPONENTS = (
    "outcome",
    "state",
    "constraints",
    "side_effects",
    "process",
    "efficiency",
    "evidence",
)


def _operational_state_digest(
    runtime: OperationalRuntime,
    *,
    supplied: str | None,
    scope: StateDigestScope,
) -> StateDigest:
    """Digest the harness-visible operational state at its recorded value.

    ``runtime.state_snapshot()`` is documented harness-visible-but-not-agent-facing, and the
    state is seeded from the episode's private oracle. The digest is therefore emitted at the
    caller-chosen scope (``SEMANTIC`` by default) rather than silently downgraded to the legacy
    adapter's ``PUBLIC_SEMANTIC``; a supplied digest always wins.
    """

    if supplied is not None:
        return StateDigest(digest=supplied, scope=scope)
    return StateDigest(digest=canonical_hash(runtime.state_snapshot()), scope=scope)


def _operational_event(event: ActionEvent) -> TrajectoryEvent:
    """Project one ``ActionEvent`` onto the payload shape ``_decode_operational_act`` decodes.

    ``reverify/engine.py`` recovers ``(action_name, parameters)`` from a ``method == "act"`` event
    whose ``args`` carries the action name and whose ``kwargs`` carries the parameters. That is
    the only form emitted; no second action vocabulary exists.

    Verifier-only fields (``state_changes``, ``side_effects``, ``forbidden``,
    ``consequence_severity``, ``blocked_reason``) never enter the public payload. They are kept
    in ``private_payload``, which ``public_payload()``/``buyer_safe_payload()`` drop, so the same
    discipline the legacy adapter applies via its context's ``private_metadata`` applies here.
    """

    success = bool(event.effect_applied and not event.blocked)
    private: dict[str, Any] = {
        "sequence": event.sequence,
        "kind": event.kind.value,
        "system": event.system,
        "state_changes": copy.deepcopy(event.state_changes),
        "side_effects": copy.deepcopy(event.side_effects),
        "forbidden": event.forbidden,
        "consequence_severity": event.consequence_severity,
        "effect_applied": event.effect_applied,
        "blocked": event.blocked,
    }
    if event.blocked_reason is not None:
        private["blocked_reason"] = event.blocked_reason
    return TrajectoryEvent(
        step=event.sequence - 1,
        event_type="act",
        payload={
            "method": "act",
            "action_name": event.action_name,
            "args": [event.action_name],
            "kwargs": copy.deepcopy(event.parameters),
            "success": success,
        },
        cost=float(event.cost),
        private_payload=private,
        visibility=VisibilityClass.PUBLIC,
    )


def _submit_event(submission: Any, step: int, cost: float | None) -> TrajectoryEvent:
    """Emit the single ``submit`` event the reverification engine requires.

    ``_decode_submission`` accepts ``args = [<submission dict>]`` — a *mapping*, not the model
    object, because it re-validates through ``EpisodeSubmission.model_validate``. The payload is
    therefore the caller's submission serialized with ``model_dump(mode="json")``; the adapter
    never synthesizes one.
    """

    return TrajectoryEvent(
        step=step,
        event_type="submit",
        payload={
            "method": "submit",
            "args": [
                copy.deepcopy(
                    submission.model_dump(mode="json")
                    if hasattr(submission, "model_dump")
                    else submission
                )
            ],
            "kwargs": {},
            "success": True,
        },
        cost=cost,
        visibility=VisibilityClass.PUBLIC,
    )


def trajectory_v2_from_operational_runtime(
    runtime: OperationalRuntime,
    *,
    context: OperationalRuntimeAdapterContext | None = None,
) -> TrajectoryV2:
    """Deterministically record a submitted ``OperationalRuntime`` as a ``TrajectoryV2``.

    Pure record conversion over already-recorded state: it never re-runs, re-scores, or forks
    the runtime, and it never calls ``submit()`` on the caller's runtime. The runtime must
    already be closed (``runtime.closed``), because ``TrajectoryV2`` requires an
    ``original_evaluation`` and only a submitted runtime has one.

    The evaluation and the submission are taken from ``OperationalRuntimeAdapterContext`` rather
    than derived: ``OperationalRuntime.submit()`` returns its ``VerificationBreakdown`` without
    retaining it, so the caller supplies the object it already holds. Re-scoring to recover them
    would violate the no-re-scoring rule, so that is never done.

    Facts unavailable from the runtime remain explicitly unknown unless the context names them.
    The verifier identity is the exception: when the context does not supply one, the authorized
    operational binding is used, and ``TrajectoryV2`` then enforces
    ``original_evaluation.verifier == trajectory.verifier``.
    """

    if not runtime.closed:
        raise ValueError("operational runtime must be submitted before trajectory adaptation")
    ctx = context or OperationalRuntimeAdapterContext()
    episode = runtime.episode
    acted = tuple(_operational_event(event) for event in runtime.events)
    events = (
        (*acted, _submit_event(ctx.submission, len(acted), 0.0))
        if ctx.submission is not None
        else acted
    )
    resource_calls = (
        ctx.resource_calls
        if ctx.resource_calls is not None
        else tuple(_resource_call(index, event) for index, event in enumerate(events))
    )
    verifier = ctx.verifier
    if verifier is None:
        verifier = current_operational_verifier_binding().identity
    breakdown = _breakdown(ctx, runtime)
    source_provenance = ProvenanceRecord(
        source_kind="operational.episode_execution",
        source_id=episode.episode_id,
        source_version=None,
        source_digest=canonical_hash(episode.model_dump(mode="json")),
        adapter_id=OPERATIONAL_RUNTIME_ADAPTER_ID,
        adapter_version=OPERATIONAL_RUNTIME_ADAPTER_VERSION,
        visibility=VisibilityClass.BUYER_SAFE,
        private_metadata={
            "operational_episode_metadata": copy.deepcopy(episode.metadata),
            "operational_breakdown": copy.deepcopy(breakdown.model_dump(mode="json")),
        },
    )
    return TrajectoryV2(
        world=WorldIdentity(
            environment_id=ctx.environment_id,
            environment_version=ctx.world_version,
            world_id=ctx.world_id if ctx.world_id is not None else episode.world_id,
            world_version=ctx.world_version,
            world_bundle=ctx.world_bundle,
            portable_operational_contract=ctx.portable_operational_contract,
        ),
        task=TaskIdentity(
            task_id=episode.task.task_id,
            taskset_version=None,
            split=None,
        ),
        model=ctx.model,
        agent=ctx.agent,
        harness=HarnessIdentity(harness_id=ctx.harness_id, version=None),
        runtime=RuntimeIdentity(runtime_id=ctx.runtime_id, version=None),
        verifier=verifier,
        reset=ResetIdentity(
            seed=None,
            reset_id=ctx.reset_id,
            reset_index=ctx.reset_index,
        ),
        initial_state=_operational_state_digest(
            runtime,
            supplied=ctx.initial_state_digest,
            scope=ctx.initial_state_scope,
        ),
        events=events,
        provider_calls=ctx.provider_calls,
        resource_calls=resource_calls,
        observation_references=ctx.observation_references,
        evidence_references=ctx.evidence_references,
        usage=UsageTotals(
            environment_cost=float(runtime.budget.spent),
            elapsed_s=ctx.elapsed_s,
        ),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={name: float(getattr(breakdown, name)) for name in _REWARD_COMPONENTS},
            reward=float(breakdown.overall_reward),
        ),
        termination=TerminationRecord(
            reason="episode_submitted",
            terminated=ctx.terminated if ctx.terminated is not None else True,
            truncated=ctx.truncated,
        ),
        final_state=_operational_state_digest(
            runtime,
            supplied=ctx.final_state_digest,
            scope=ctx.final_state_scope,
        ),
        failure=ctx.failure,
        capability_tags=(),
        provenance=(source_provenance, *ctx.provenance),
        visibility=ctx.visibility,
        public_metadata=copy.deepcopy(ctx.public_metadata),
        private_metadata=copy.deepcopy(ctx.private_metadata),
    )


def _breakdown(context: OperationalRuntimeAdapterContext, runtime: OperationalRuntime) -> Any:
    """Resolve the evaluation a submitted runtime already produced.

    ``OperationalRuntime.submit()`` returns the ``VerificationBreakdown`` without retaining it, so
    the caller supplies it in the context. It is the single evaluation the runtime performed;
    nothing is re-scored here.

    ``NativeOperationalRuntime`` is not special-cased. It records its native-artifact assertions
    in ``episode.oracle.target_state`` and extends ``process_violations`` before scoring, so the
    breakdown the caller holds already describes the episode the recorded events describe. The
    adapter consumes ``runtime.events`` and that one breakdown generically, so both runtimes map
    through the same code path.
    """

    if context.breakdown is not None:
        return context.breakdown
    raise ValueError(
        "operational trajectory adaptation requires the VerificationBreakdown returned by "
        "runtime.submit() in OperationalRuntimeAdapterContext.breakdown"
    )
