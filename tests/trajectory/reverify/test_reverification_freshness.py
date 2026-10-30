"""Public synthetic regressions for fresh evidence under stable record identity."""

import pytest
from test_reverification import _registry, _reverifiable_trajectory

from investigation_world.experience import MachineExperience
from investigation_world.trajectory import ReverificationRecord, TrajectoryV2
from investigation_world.trajectory.reverify import (
    AuthorizedVerifierRegistry,
    ReverificationStatus,
    batch_reverify_trajectories,
    reverify_trajectory,
)


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {
            "verification_breakdown": {"forbidden_actions_taken": ["SYNTHETIC-STALE"]},
            "caller_annotation": "not verifier evidence",
        },
    ],
)
def test_existing_identity_returns_fresh_evidence_without_mutating_input(metadata):
    trajectory, _ = _reverifiable_trajectory()
    registry, verifier = _registry()
    fresh = reverify_trajectory(trajectory, verifier=verifier, registry=registry).record
    assert fresh is not None
    retained = ReverificationRecord.model_validate(
        {
            **fresh.model_dump(mode="python"),
            "private_metadata": metadata,
        }
    )
    other = ReverificationRecord.model_validate(
        {
            **fresh.model_dump(mode="python"),
            "record_id": "",
            "reward": 0.125,
            "private_metadata": {"unrelated": "preserved"},
        }
    )
    original = trajectory.with_reverification(other).with_reverification(retained)
    before = original.model_dump(mode="python")
    outcome = reverify_trajectory(original, verifier=verifier, registry=registry)
    assert outcome.status is ReverificationStatus.ALREADY_RECORDED
    assert outcome.reason_code == "REVERIFICATION_RECORD_ALREADY_PRESENT"
    assert outcome.record == fresh
    updated = outcome.trajectory_with_reverification
    assert updated is not None
    assert updated.reverifications == (other, fresh)
    assert updated.trajectory_id == original.trajectory_id
    assert updated.original_evaluation == original.original_evaluation
    assert original.model_dump(mode="python") == before
    assert reverify_trajectory(updated, verifier=verifier, registry=registry) == outcome

    batch = batch_reverify_trajectories([original], verifier=verifier, registry=registry)
    assert batch.trajectories == (updated,)
    experience = MachineExperience(trajectory=original)
    refreshed = MachineExperience.model_validate(
        {
            **experience.model_dump(mode="python"),
            "trajectory": updated,
        }
    )
    assert refreshed.experience_id == experience.experience_id
    assert refreshed.trajectory.reverifications[-1] == outcome.record

    denied = reverify_trajectory(
        original, verifier=verifier, registry=AuthorizedVerifierRegistry(())
    )
    assert denied.status is ReverificationStatus.UNAUTHORIZED
    assert denied.record is None
    missing = TrajectoryV2.model_validate({**before, "private_metadata": {}})
    rejected = reverify_trajectory(missing, verifier=verifier, registry=registry)
    assert rejected.status is ReverificationStatus.NOT_REVERIFIABLE
    assert rejected.record is None
