from __future__ import annotations

import pytest

from investigation_world.observatory.execution import ProviderSessionSummary
from investigation_world.observatory.models import (
    BehavioralFingerprint,
    CapabilityProfile,
    CapabilityRun,
    HarnessSpec,
    LongitudinalCell,
    ModelSpec,
    RunProvenance,
    ScenarioRef,
    VerifierSpec,
    WorldRef,
)
from investigation_world.observatory.trajectory_diagnostics import (
    TrajectoryDiagnosticInput,
    diagnose_failure,
)
from investigation_world.trajectory import (
    EvaluationRecord,
    FailureCategory,
    FailureClassification,
    HarnessIdentity,
    ModelIdentity,
    ProviderCallSummary,
    ResourceCallSummary,
    RuntimeIdentity,
    StateDigest,
    TaskIdentity,
    TerminationRecord,
    TrajectoryV2,
    VerifierIdentity,
    WorldIdentity,
)


def _trajectory(
    *,
    failure: FailureClassification | None = None,
    provider_failed: bool = False,
    resource_failed: bool = False,
    termination: TerminationRecord | None = None,
    reward: float = 0.2,
) -> TrajectoryV2:
    verifier = VerifierIdentity(verifier_id="operational", version="7")
    return TrajectoryV2(
        world=WorldIdentity(
            environment_id="env",
            environment_version="2",
            world_id="world",
            world_version="5",
        ),
        task=TaskIdentity(task_id="task-1", taskset_version="set-3", split="iid_test"),
        model=ModelIdentity(provider="test", model_id="model", snapshot="snap-1"),
        harness=HarnessIdentity(harness_id="harness-a", version="1"),
        runtime=RuntimeIdentity(runtime_id="runtime", version="1"),
        verifier=verifier,
        initial_state=StateDigest(digest="a" * 64),
        provider_calls=(
            ProviderCallSummary(call_index=0, success=False),
        )
        if provider_failed
        else (),
        resource_calls=(
            ResourceCallSummary(call_index=0, operation="search", success=False),
        )
        if resource_failed
        else (),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={"outcome": reward},
            reward=reward,
        ),
        termination=termination or TerminationRecord(reason="completed", terminated=True),
        failure=failure or FailureClassification(),
    )


def _capability_run() -> CapabilityRun:
    cell = LongitudinalCell(
        world=WorldRef(world_id="world", version="5"),
        scenario=ScenarioRef(scenario_id="scenario-1", seed=17, task_id="task-1"),
        model=ModelSpec(provider="test", model_id="model", snapshot="snap-1"),
        harness=HarnessSpec(harness_id="harness-a", version="1"),
        verifier=VerifierSpec(verifier_id="operational", version="7"),
        time_snapshot="2026-08-28",
    )
    return CapabilityRun(
        cell=cell,
        provenance=RunProvenance(
            trace_id="trace-1",
            environment_version="2",
            task_id="task-1",
            taskset_version="set-3",
            runtime_version="1",
            harness_version="1",
        ),
        capability=CapabilityProfile(dimensions={"outcome": 0.8}),
        behavior=BehavioralFingerprint(total_steps=2),
    )


def test_declared_failure_preserves_stated_uncertainty() -> None:
    trajectory = _trajectory(
        failure=FailureClassification(
            category=FailureCategory.MODEL_FAILURE,
            confidence=0.55,
        )
    )

    attribution = diagnose_failure(trajectory)

    assert attribution.primary_category is FailureCategory.UNKNOWN
    assert attribution.category_probabilities[FailureCategory.MODEL_FAILURE.value] == 0.55
    assert attribution.category_probabilities[FailureCategory.UNKNOWN.value] == pytest.approx(0.45)
    assert attribution.ambiguous is True
    assert attribution.evidence[0].direct is True


def test_declared_high_confidence_category_is_preserved_without_new_inference() -> None:
    trajectory = _trajectory(
        failure=FailureClassification(
            category=FailureCategory.VERIFIER_FAILURE,
            confidence=0.9,
        )
    )

    attribution = diagnose_failure(trajectory)

    assert attribution.primary_category is FailureCategory.VERIFIER_FAILURE
    assert attribution.category_probabilities[FailureCategory.VERIFIER_FAILURE.value] == 0.9
    assert attribution.category_probabilities[FailureCategory.UNKNOWN.value] == pytest.approx(0.1)
    assert attribution.qualified is True


def test_failed_resource_call_is_intentionally_ambiguous() -> None:
    attribution = diagnose_failure(_trajectory(resource_failed=True))

    assert attribution.primary_category is FailureCategory.UNKNOWN
    assert attribution.category_probabilities[FailureCategory.TOOL_ACTION_FAILURE.value] == 0.375
    assert (
        attribution.category_probabilities[FailureCategory.ENVIRONMENT_RUNTIME_FAILURE.value]
        == 0.375
    )
    assert attribution.category_probabilities[FailureCategory.UNKNOWN.value] == 0.25
    assert "cannot uniquely distinguish" in attribution.evidence[0].qualification


def test_provider_and_resource_signals_do_not_become_confident_blame() -> None:
    attribution = diagnose_failure(
        _trajectory(provider_failed=True, resource_failed=True)
    )

    assert attribution.primary_category is FailureCategory.UNKNOWN
    assert attribution.ambiguous is True
    assert max(
        value
        for category, value in attribution.category_probabilities.items()
        if category != FailureCategory.UNKNOWN.value
    ) < 0.8


def test_explicit_budget_truncation_is_qualified_not_certain() -> None:
    attribution = diagnose_failure(
        _trajectory(
            termination=TerminationRecord(
                reason="budget_exhausted",
                terminated=False,
                truncated=True,
            )
        )
    )

    assert attribution.primary_category is FailureCategory.UNKNOWN
    assert (
        attribution.category_probabilities[FailureCategory.BUDGET_TERMINATION_FAILURE.value]
        == 0.7
    )
    assert attribution.category_probabilities[FailureCategory.UNKNOWN.value] == 0.3


def test_low_reward_alone_never_implies_model_or_verifier_failure() -> None:
    attribution = diagnose_failure(_trajectory(reward=0.0))

    assert attribution.primary_category is FailureCategory.UNKNOWN
    assert attribution.category_probabilities[FailureCategory.UNKNOWN.value] == 1.0
    assert attribution.evidence == ()


def test_diagnostic_input_reuses_existing_observatory_run_and_provider_abstractions() -> None:
    trajectory = _trajectory()
    run = _capability_run()
    provider = ProviderSessionSummary(
        provider_id="test",
        model_id="model",
        model_snapshot="snap-1",
        calls=0,
        input_tokens=0,
        output_tokens=0,
        total_tokens=0,
        cost=0.0,
        latency_s=0.0,
    )

    bound = TrajectoryDiagnosticInput(
        trajectory=trajectory,
        capability_run=run,
        provider_session=provider,
    )

    assert bound.capability_run is run
    assert bound.provider_session is provider


def test_observatory_binding_rejects_identity_mismatch_instead_of_replacing_run_identity() -> None:
    trajectory = _trajectory()
    run = _capability_run()
    mismatched = run.model_copy(
        update={
            "cell": run.cell.model_copy(
                update={
                    "model": run.cell.model.model_copy(update={"model_id": "different-model"})
                }
            )
        }
    )

    with pytest.raises(ValueError, match="model id"):
        TrajectoryDiagnosticInput(trajectory=trajectory, capability_run=mismatched)
