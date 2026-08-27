from __future__ import annotations

import json

from investigation_world.foundry.models import DistributionSplit, RolloutTrace, TraceEvent
from investigation_world.trajectory import (
    ArtifactIdentity,
    FailureCategory,
    ModelIdentity,
    ProviderCallSummary,
    RolloutTraceAdapterContext,
    TrajectoryReference,
    VerifierIdentity,
    VisibilityClass,
    trajectory_v2_from_rollout_trace,
)


def _trace(
    *,
    events: list[TraceEvent] | None = None,
    termination_reason: str = "submitted",
) -> RolloutTrace:
    return RolloutTrace(
        trace_id="TRACE-LEGACY-001",
        environment_version="companyworld-bundle-7",
        task_id="task-42",
        task_seed=123,
        split=DistributionSplit.IID_TEST,
        capability_tags=["investigation", "evidence"],
        taskset_version="taskset-5",
        harness_version="1",
        runtime_version="runtime-2",
        initial_state_hash="1" * 64,
        events=events
        or [
            TraceEvent(
                step=0,
                event_type="search_system",
                payload={
                    "method": "search_system",
                    "args": ["ERP", "invoice"],
                    "kwargs": {},
                    "result": [{"record_id": "REC-1"}],
                    "success": True,
                    "private_metadata": {"nested": "NESTED-PRIVATE-SECRET"},
                },
                state_hash_before="1" * 64,
                state_hash_after="1" * 64,
                cost=2.0,
            ),
            TraceEvent(
                step=1,
                event_type="submit",
                payload={"method": "submit", "args": [{"answer": "A"}], "success": True},
                state_hash_before="1" * 64,
                state_hash_after="2" * 64,
                cost=1.0,
            ),
        ],
        verifier_components={"outcome": 0.9, "efficiency": 0.7},
        total_reward=0.85,
        final_state_hash="2" * 64,
        termination_reason=termination_reason,
        total_cost=3.0,
        metadata={"private_oracle_hint": "DO-NOT-PUBLISH"},
    )


def _context(**updates) -> RolloutTraceAdapterContext:
    payload = {
        "environment_id": "companyworld",
        "world_id": "cw-world",
        "world_version": "world-v3",
        "model": ModelIdentity(provider="hf", model_id="model-a", snapshot="sha-abc"),
        "harness_id": "companyworld-json-agent",
        "runtime_id": "companyworld-runtime",
        "verifier": VerifierIdentity(verifier_id="companyworld", version="1"),
    }
    payload.update(updates)
    return RolloutTraceAdapterContext(**payload)


def test_rollout_trace_conversion_is_deterministic_and_preserves_source_lineage() -> None:
    trace = _trace()
    context = _context()
    first = trajectory_v2_from_rollout_trace(trace, context=context)
    second = trajectory_v2_from_rollout_trace(trace, context=context)

    assert first == second
    assert first.trajectory_id == second.trajectory_id
    assert first.provenance[0].source_id == trace.trace_id
    assert first.provenance[0].source_digest is not None
    assert first.task.task_id == trace.task_id
    assert first.reset.seed == trace.task_seed
    assert first.original_evaluation.reward == trace.total_reward


def test_model_harness_and_verifier_identities_affect_trajectory_identity() -> None:
    trace = _trace()
    base = trajectory_v2_from_rollout_trace(trace, context=_context())
    model_changed = trajectory_v2_from_rollout_trace(
        trace,
        context=_context(
            model=ModelIdentity(provider="hf", model_id="model-b", snapshot="sha-abc")
        ),
    )
    harness_changed = trajectory_v2_from_rollout_trace(
        trace,
        context=_context(harness_id="alternate-harness"),
    )
    verifier_changed = trajectory_v2_from_rollout_trace(
        trace,
        context=_context(verifier=VerifierIdentity(verifier_id="companyworld", version="2")),
    )

    assert len(
        {
            base.trajectory_id,
            model_changed.trajectory_id,
            harness_changed.trajectory_id,
            verifier_changed.trajectory_id,
        }
    ) == 4


def test_adapter_does_not_infer_failure_attribution_from_termination_reason() -> None:
    trajectory = trajectory_v2_from_rollout_trace(
        _trace(termination_reason="tool_error_or_maybe_provider"),
        context=_context(),
    )
    assert trajectory.failure.category is FailureCategory.UNKNOWN


def test_provider_accounting_is_preserved_when_supplied() -> None:
    context = _context(
        provider_calls=(
            ProviderCallSummary(
                call_index=0,
                provider_id="hf",
                model_id="model-a",
                model_snapshot="sha-abc",
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                cost=0.01,
                duration_s=0.4,
            ),
            ProviderCallSummary(
                call_index=1,
                provider_id="hf",
                model_id="model-a",
                model_snapshot="sha-abc",
                input_tokens=40,
                output_tokens=10,
                total_tokens=50,
                cost=0.02,
                duration_s=0.3,
            ),
        ),
        elapsed_s=2.5,
    )
    trajectory = trajectory_v2_from_rollout_trace(_trace(), context=context)

    assert trajectory.usage.input_tokens == 140
    assert trajectory.usage.output_tokens == 30
    assert trajectory.usage.total_tokens == 170
    assert trajectory.usage.provider_cost == 0.03
    assert trajectory.usage.environment_cost == 3.0
    assert trajectory.usage.total_cost == 3.03
    assert trajectory.usage.elapsed_s == 2.5


def test_private_fields_cannot_enter_public_or_buyer_safe_serialization() -> None:
    private_ref = TrajectoryReference(
        reference_id="PRIVATE-EVIDENCE-SECRET",
        reference_type="evidence",
        visibility=VisibilityClass.EVALUATOR_PRIVATE,
        private_metadata={"locator": "s3://secret-bucket/private"},
    )
    context = _context(
        world_bundle=ArtifactIdentity(
            artifact_id="SECRET-WORLD-BUNDLE-ID",
            version="0.1",
            digest="SECRET-WORLD-BUNDLE-DIGEST",
            visibility=VisibilityClass.EVALUATOR_PRIVATE,
        ),
        evidence_references=(private_ref,),
        private_metadata={"private_contract": "PRIVATE-CONTRACT-VALUE"},
    )
    trajectory = trajectory_v2_from_rollout_trace(_trace(), context=context)
    private_event = trajectory.events[0].model_copy(
        update={"private_payload": {"oracle": "EVENT-PRIVATE-SECRET"}}
    )
    trajectory = type(trajectory).model_validate(
        {
            **trajectory.model_dump(mode="python"),
            "trajectory_id": "",
            "events": (private_event, *trajectory.events[1:]),
        }
    )

    public_text = json.dumps(trajectory.public_payload(), sort_keys=True)
    buyer_text = json.dumps(trajectory.buyer_safe_payload(), sort_keys=True)
    for secret in (
        "DO-NOT-PUBLISH",
        "PRIVATE-EVIDENCE-SECRET",
        "s3://secret-bucket/private",
        "SECRET-WORLD-BUNDLE-ID",
        "SECRET-WORLD-BUNDLE-DIGEST",
        "PRIVATE-CONTRACT-VALUE",
        "EVENT-PRIVATE-SECRET",
        "NESTED-PRIVATE-SECRET",
    ):
        assert secret not in public_text
        assert secret not in buyer_text

    assert "TRACE-LEGACY-001" not in public_text
    assert "TRACE-LEGACY-001" in buyer_text


def test_event_order_change_in_rollout_changes_canonical_trajectory_id() -> None:
    trace = _trace()
    original = trajectory_v2_from_rollout_trace(trace, context=_context())
    reordered = trace.model_copy(update={"events": list(reversed(trace.events))})
    changed = trajectory_v2_from_rollout_trace(reordered, context=_context())
    assert original.trajectory_id != changed.trajectory_id


def test_resource_calls_are_deterministically_derived_from_legacy_events() -> None:
    trajectory = trajectory_v2_from_rollout_trace(_trace(), context=_context())
    assert [item.operation for item in trajectory.resource_calls] == ["search_system", "submit"]
    assert trajectory.resource_calls[0].resource_id == "system:ERP"
    assert trajectory.resource_calls[0].success is True


def test_worldbundle_and_portable_contract_identity_affect_trajectory_identity() -> None:
    trace = _trace()
    base = trajectory_v2_from_rollout_trace(trace, context=_context())
    with_bundle = trajectory_v2_from_rollout_trace(
        trace,
        context=_context(
            world_bundle=ArtifactIdentity(
                artifact_id="WB-1",
                contract="woyengi.worldbundle",
                version="0.1",
                digest="a" * 64,
            )
        ),
    )
    with_contract = trajectory_v2_from_rollout_trace(
        trace,
        context=_context(
            portable_operational_contract=ArtifactIdentity(
                artifact_id="POC-1",
                contract="veritas.portable-operational-contract",
                version="1",
                digest="b" * 64,
            )
        ),
    )

    assert len({base.trajectory_id, with_bundle.trajectory_id, with_contract.trajectory_id}) == 3
