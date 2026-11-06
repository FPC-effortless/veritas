from __future__ import annotations

import pytest

from investigation_world.observatory.trajectory_diagnostics import (
    build_trajectory_diagnostics,
    capability_conditioned_failure_profiles,
    compare_same_harness_different_model,
    compare_same_model_different_harness,
    compare_same_trajectory_verifier_versions,
    diagnose_failure,
    failure_category_distribution,
)
from investigation_world.trajectory import (
    EvaluationRecord,
    FailureCategory,
    FailureClassification,
    HarnessIdentity,
    ModelIdentity,
    ResourceCallSummary,
    ReverificationRecord,
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
    model_id: str = "model-a",
    harness_id: str = "harness-a",
    harness_version: str = "1",
    reward: float = 0.5,
    failure: FailureClassification | None = None,
    resource_failed: bool = False,
    capability_tags: tuple[str, ...] = ("planning",),
    task_id: str = "task-1",
) -> TrajectoryV2:
    verifier = VerifierIdentity(verifier_id="operational", version="7")
    return TrajectoryV2(
        world=WorldIdentity(
            environment_id="env",
            environment_version="2",
            world_id="world",
            world_version="5",
        ),
        task=TaskIdentity(task_id=task_id, taskset_version="set-3", split="iid_test"),
        model=ModelIdentity(provider="test", model_id=model_id, snapshot="snap-1"),
        harness=HarnessIdentity(harness_id=harness_id, version=harness_version),
        runtime=RuntimeIdentity(runtime_id="runtime", version="1"),
        verifier=verifier,
        initial_state=StateDigest(digest="a" * 64),
        resource_calls=(
            ResourceCallSummary(call_index=0, operation="search", success=False),
        )
        if resource_failed
        else (),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={"outcome": reward, "process": reward / 2},
            reward=reward,
        ),
        termination=TerminationRecord(reason="completed", terminated=True, truncated=False),
        failure=failure or FailureClassification(),
        capability_tags=capability_tags,
    )


def test_same_model_different_harness_requires_controlled_context() -> None:
    left = _trajectory(harness_id="harness-a", reward=0.4)
    right = _trajectory(harness_id="harness-b", reward=0.7)
    confounded = _trajectory(
        harness_id="harness-c",
        reward=0.9,
        task_id="different-task",
    )

    view = compare_same_model_different_harness((left, right, confounded))

    assert len(view.rows) == 1
    row = view.rows[0]
    assert {row.left_variant, row.right_variant} == {"harness-a@1", "harness-b@1"}
    assert abs(row.reward_delta) == pytest.approx(0.3)
    assert "does not by itself establish harness causality" in row.qualification


def test_same_harness_different_model_requires_other_identity_to_match() -> None:
    first = _trajectory(model_id="model-a", reward=0.3)
    second = _trajectory(model_id="model-b", reward=0.8)
    different_harness = _trajectory(model_id="model-c", harness_id="harness-b")

    view = compare_same_harness_different_model((first, second, different_harness))

    assert len(view.rows) == 1
    row = view.rows[0]
    assert {row.left_variant, row.right_variant} == {
        "test:model-a@snap-1",
        "test:model-b@snap-1",
    }
    assert abs(row.reward_delta) == pytest.approx(0.5)
    assert "does not by itself establish model causality" in row.qualification


def test_same_trajectory_different_verifier_version_reports_sensitivity_not_blame() -> None:
    trajectory = _trajectory(reward=0.4)
    record = ReverificationRecord(
        input_trajectory_id=trajectory.trajectory_id,
        verifier=VerifierIdentity(verifier_id="operational", version="8"),
        component_scores={"outcome": 0.9, "process": 0.5},
        reward=0.8,
    )

    rows = compare_same_trajectory_verifier_versions(trajectory, (record,))

    assert len(rows) == 1
    row = rows[0]
    assert row.trajectory_id == trajectory.trajectory_id
    assert row.baseline_version == "7"
    assert row.candidate_version == "8"
    assert row.reward_delta == pytest.approx(0.4)
    assert row.component_deltas == {
        "outcome": pytest.approx(0.5),
        "process": pytest.approx(0.3),
    }
    assert "does not establish verifier failure" in row.qualification


def test_verifier_comparison_rejects_record_for_another_trajectory() -> None:
    trajectory = _trajectory()
    foreign = ReverificationRecord(
        input_trajectory_id="TRAJ-V2-FOREIGN",
        verifier=VerifierIdentity(verifier_id="operational", version="8"),
        reward=0.1,
    )

    with pytest.raises(ValueError, match="different trajectory"):
        compare_same_trajectory_verifier_versions(trajectory, (foreign,))


def test_failure_distribution_preserves_fractional_ambiguous_mass() -> None:
    declared = _trajectory(
        failure=FailureClassification(category=FailureCategory.MODEL_FAILURE)
    )
    ambiguous = _trajectory(
        model_id="model-b",
        resource_failed=True,
        capability_tags=("planning", "tool-use"),
    )
    attributions = (diagnose_failure(declared), diagnose_failure(ambiguous))

    distribution = failure_category_distribution(attributions)

    assert distribution.trajectory_count == 2
    assert distribution.primary_counts[FailureCategory.MODEL_FAILURE.value] == 1
    assert distribution.primary_counts[FailureCategory.UNKNOWN.value] == 1
    assert distribution.expected_counts[FailureCategory.MODEL_FAILURE.value] == 1.0
    assert distribution.expected_counts[FailureCategory.TOOL_ACTION_FAILURE.value] == 0.375
    assert (
        distribution.expected_counts[FailureCategory.ENVIRONMENT_RUNTIME_FAILURE.value]
        == 0.375
    )
    assert distribution.expected_counts[FailureCategory.UNKNOWN.value] == 0.25
    assert distribution.ambiguous_count == 1


def test_capability_conditioned_profiles_keep_multi_tag_membership() -> None:
    first = _trajectory(
        failure=FailureClassification(category=FailureCategory.MODEL_FAILURE),
        capability_tags=("planning",),
    )
    second = _trajectory(
        model_id="model-b",
        resource_failed=True,
        capability_tags=("planning", "tool-use"),
    )

    profiles = {
        profile.capability_tag: profile
        for profile in capability_conditioned_failure_profiles((first, second))
    }

    assert profiles["planning"].distribution.trajectory_count == 2
    assert profiles["tool-use"].distribution.trajectory_count == 1
    assert (
        profiles["tool-use"].distribution.primary_counts[FailureCategory.UNKNOWN.value]
        == 1
    )


def test_report_consumes_external_reverification_without_mutating_trajectory() -> None:
    first = _trajectory(harness_id="harness-a", reward=0.4)
    second = _trajectory(harness_id="harness-b", reward=0.6)
    record = ReverificationRecord(
        input_trajectory_id=first.trajectory_id,
        verifier=VerifierIdentity(verifier_id="operational", version="8"),
        component_scores={"outcome": 0.7},
        reward=0.7,
    )

    report = build_trajectory_diagnostics((first, second), reverifications=(record,))

    assert report.consumed_reverification_record_ids == (record.record_id,)
    assert len(report.same_model_different_harness.rows) == 1
    assert len(report.verifier_version_comparisons) == 1
    assert first.reverifications == ()
    assert first.original_evaluation.reward == 0.4


def test_report_rejects_duplicate_trajectory_identity_to_avoid_distribution_skew() -> None:
    trajectory = _trajectory()

    with pytest.raises(ValueError, match="unique trajectory ids"):
        build_trajectory_diagnostics((trajectory, trajectory))


def test_report_rejects_unmatched_reverification_record() -> None:
    trajectory = _trajectory()
    record = ReverificationRecord(
        input_trajectory_id="TRAJ-V2-NOT-IN-REPORT",
        verifier=VerifierIdentity(verifier_id="operational", version="8"),
        reward=0.2,
    )

    with pytest.raises(ValueError, match="no matching diagnostic trajectory"):
        build_trajectory_diagnostics((trajectory,), reverifications=(record,))
