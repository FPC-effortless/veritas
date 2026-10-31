"""Safe export classification checks using only public synthetic fixtures."""

import pytest
from test_machine_experience import _trajectory

from investigation_world.experience import ExperienceReference, MachineExperience
from investigation_world.trajectory import TrajectoryV2, VisibilityClass


@pytest.mark.parametrize("visibility", list(VisibilityClass))
@pytest.mark.parametrize("method", ["public_payload", "buyer_safe_payload"])
def test_root_classification_is_an_export_boundary(visibility, method):
    trajectory = _trajectory()
    experience = MachineExperience(
        trajectory=trajectory,
        visibility=visibility,
        public_metadata={"synthetic": "ROOT-ANNOTATION"},
        private_metadata={"synthetic": "PRIVATE-BUCKET"},
    )
    before = experience.model_dump(mode="python")
    allowed = visibility is VisibilityClass.PUBLIC or (
        method == "buyer_safe_payload" and visibility is VisibilityClass.BUYER_SAFE
    )
    if allowed:
        payload = getattr(experience, method)()
        assert payload["public_metadata"] == {"synthetic": "ROOT-ANNOTATION"}
        assert "PRIVATE-BUCKET" not in repr(payload)
        assert payload["trajectory"]["events"][0]["payload"] == {"public": "visible"}
    else:
        with pytest.raises(ValueError, match="experience is not classified"):
            getattr(experience, method)()
    assert experience.model_dump(mode="python") == before
    assert experience.experience_id == MachineExperience(trajectory=trajectory).experience_id


@pytest.mark.parametrize("visibility", list(VisibilityClass))
@pytest.mark.parametrize("method", ["public_payload", "buyer_safe_payload"])
def test_public_root_does_not_override_nested_trajectory_classification(visibility, method):
    trajectory = TrajectoryV2.model_validate(
        {
            **_trajectory().model_dump(mode="python"),
            "visibility": visibility,
        }
    )
    experience = MachineExperience(trajectory=trajectory)
    allowed = visibility is VisibilityClass.PUBLIC or (
        method == "buyer_safe_payload" and visibility is VisibilityClass.BUYER_SAFE
    )
    if allowed:
        assert getattr(experience, method)()["trajectory"] == getattr(trajectory, method)()
    else:
        with pytest.raises(ValueError, match="trajectory is not classified"):
            getattr(experience, method)()


@pytest.mark.parametrize("method", ["public_payload", "buyer_safe_payload"])
def test_allowed_root_retains_recursive_child_filtering(method):
    experience = MachineExperience(
        trajectory=_trajectory(),
        derivation_references=tuple(
            ExperienceReference(
                reference_id=f"synthetic-{visibility.value}",
                reference_type="test",
                visibility=visibility,
                private_metadata={"sentinel": "PRIVATE-CHILD"},
            )
            for visibility in VisibilityClass
        ),
    )
    payload = getattr(experience, method)()
    expected = ["synthetic-public"]
    if method == "buyer_safe_payload":
        expected.append("synthetic-buyer_safe")
    assert [item["reference_id"] for item in payload["derivation_references"]] == expected
    assert "PRIVATE-CHILD" not in repr(payload)
    assert "never-public" not in repr(payload)
