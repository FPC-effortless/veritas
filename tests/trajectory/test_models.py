from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from investigation_world.trajectory import (
    EvaluationRecord,
    FailureCategory,
    FailureClassification,
    ModelIdentity,
    ReverificationRecord,
    StateDigest,
    TaskIdentity,
    TrajectoryEvent,
    TrajectoryV2,
    VerifierIdentity,
    WorldIdentity,
)


def _trajectory(*, events: tuple[TrajectoryEvent, ...] | None = None) -> TrajectoryV2:
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
        verifier=verifier,
        initial_state=StateDigest(digest="a" * 64),
        events=events
        or (
            TrajectoryEvent(step=0, event_type="search", payload={"query": "alpha"}),
            TrajectoryEvent(step=1, event_type="submit", payload={"answer": 1}),
        ),
        original_evaluation=EvaluationRecord(
            verifier=verifier,
            component_scores={"outcome": 0.8},
            reward=0.8,
        ),
        final_state=StateDigest(digest="b" * 64),
    )


def test_trajectory_id_is_deterministic_from_semantic_content() -> None:
    first = _trajectory()
    second = _trajectory()
    assert first.trajectory_id == second.trajectory_id
    assert first.trajectory_id.startswith("TRAJ-V2-")


def test_event_order_changes_trajectory_identity() -> None:
    first = _trajectory()
    reversed_events = tuple(reversed(first.events))
    second = _trajectory(events=reversed_events)
    assert first.trajectory_id != second.trajectory_id


def test_reverification_is_append_only_and_does_not_replace_original_scores() -> None:
    trajectory = _trajectory()
    record = ReverificationRecord(
        input_trajectory_id=trajectory.trajectory_id,
        verifier=VerifierIdentity(verifier_id="operational", version="8"),
        component_scores={"outcome": 0.25, "efficiency": 0.5},
        reward=0.25,
        timestamp=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )

    updated = trajectory.with_reverification(record)

    assert updated.trajectory_id == trajectory.trajectory_id
    assert updated.original_evaluation.reward == 0.8
    assert updated.original_evaluation.component_scores == {"outcome": 0.8}
    assert updated.reverifications == (record,)
    with pytest.raises(ValueError, match="already appended"):
        updated.with_reverification(record)
    with pytest.raises(ValidationError):
        updated.original_evaluation = EvaluationRecord(
            verifier=updated.verifier,
            component_scores={},
            reward=0.0,
        )


def test_unknown_failure_attribution_stays_explicitly_unknown() -> None:
    failure = FailureClassification()
    assert failure.category is FailureCategory.UNKNOWN
    with pytest.raises(ValidationError):
        FailureClassification(category=FailureCategory.UNKNOWN, confidence=0.8)


def test_failure_taxonomy_rejects_arbitrary_status_strings() -> None:
    with pytest.raises(ValidationError):
        FailureClassification(category="mysterious_flaky_failure")


def test_wrong_supplied_trajectory_id_is_rejected() -> None:
    trajectory = _trajectory()
    payload = trajectory.model_dump(mode="python")
    payload["trajectory_id"] = "TRAJ-V2-NOT-THE-CONTENT-ID"
    with pytest.raises(ValidationError, match="trajectory_id does not match"):
        TrajectoryV2.model_validate(payload)


def test_reverification_record_id_is_deterministic() -> None:
    trajectory = _trajectory()
    payload = {
        "input_trajectory_id": trajectory.trajectory_id,
        "verifier": VerifierIdentity(verifier_id="verifier", version="2"),
        "component_scores": {"b": 0.2, "a": 0.1},
        "reward": 0.3,
        "timestamp": datetime(2026, 8, 27, tzinfo=timezone.utc),
    }
    first = ReverificationRecord(**payload)
    second = ReverificationRecord(**payload)
    assert first.record_id == second.record_id
    assert json.loads(first.model_dump_json())["record_id"] == first.record_id


def test_arbitrary_event_payload_keys_remain_identity_bearing() -> None:
    first = _trajectory(
        events=(TrajectoryEvent(step=0, event_type="observe", payload={"visibility": "alpha"}),)
    )
    second = _trajectory(
        events=(TrajectoryEvent(step=0, event_type="observe", payload={"visibility": "beta"}),)
    )
    assert first.trajectory_id != second.trajectory_id
