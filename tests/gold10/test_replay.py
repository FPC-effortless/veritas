from investigation_world.experience import ExperienceMaturity, ReadinessStatus
from investigation_world.gold10 import (
    build_reference_experiences,
    reference_submission,
    traceable_experience,
)


def test_reference_experiences_are_native_traceable_machine_experience() -> None:
    experiences = build_reference_experiences()
    assert len(experiences) == 10
    assert len({item.experience_id for item in experiences}) == 10
    assert len({item.trajectory.trajectory_id for item in experiences}) == 10

    for experience in experiences:
        assert experience.maturity is ExperienceMaturity.E0_TRACEABLE
        assert experience.private_metadata == {}
        assert experience.trajectory.private_metadata == {}
        assert all(event.private_payload == {} for event in experience.trajectory.events)
        assert experience.readiness.reverification_ready.status is ReadinessStatus.UNKNOWN
        assert experience.public_metadata["evidence_boundary"] == "pilot_candidate_only"


def test_traceable_experience_identity_is_deterministic() -> None:
    case_id = "2005-04-I-TX"
    submission = reference_submission(case_id)
    first = traceable_experience(case_id, submission)
    second = traceable_experience(case_id, submission)
    assert first.experience_id == second.experience_id
    assert first.trajectory.trajectory_id == second.trajectory.trajectory_id
    assert first.trajectory.original_evaluation == second.trajectory.original_evaluation


def test_public_trajectory_serialization_drops_private_buckets() -> None:
    case_id = "2012-03-I-CA"
    experience = traceable_experience(case_id, reference_submission(case_id))
    payload = experience.trajectory.public_payload()
    assert "private_metadata" not in payload
    assert all("private_payload" not in event for event in payload["events"])
