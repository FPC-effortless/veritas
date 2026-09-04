import pytest
from pydantic import ValidationError

from investigation_world.gold10 import (
    EpistemicClaim,
    Gold10Submission,
    reference_submission,
    score_submission,
)


def test_reference_submissions_are_deterministic_and_fully_scored() -> None:
    for case_id in (
        "2005-04-I-TX",
        "2008-03-I-FL",
        "2008-05-I-GA",
        "2010-08-I-WA",
        "2012-03-I-CA",
        "2013-02-I-TX",
        "2013-03-I-LA",
        "2017-08-I-TX",
        "2018-02-I-WI",
        "2019-04-I-PA",
    ):
        submission = reference_submission(case_id)
        first = score_submission(case_id, submission)
        second = score_submission(case_id, submission)
        assert first == second
        assert first.reward == 1.0
        assert first.hard_failures == ()


def test_hindsight_evidence_is_a_zero_reward_hard_failure() -> None:
    case_id = "2005-04-I-TX"
    reference = reference_submission(case_id)
    payload = reference.model_dump(mode="python")
    payload["evidence_ids"] = (
        *reference.evidence_ids,
        "csb-final-findings-release-2007-03-20",
    )
    submission = Gold10Submission.model_validate(payload)
    score = score_submission(case_id, submission)
    assert score.reward == 0.0
    assert any(item.startswith("hindsight_evidence:") for item in score.hard_failures)


def test_unknown_evidence_is_a_zero_reward_hard_failure() -> None:
    case_id = "2005-04-I-TX"
    reference = reference_submission(case_id)
    payload = reference.model_dump(mode="python")
    payload["evidence_ids"] = (*reference.evidence_ids, "invented-private-oracle")
    submission = Gold10Submission.model_validate(payload)
    score = score_submission(case_id, submission)
    assert score.reward == 0.0
    assert any(item.startswith("unknown_evidence:") for item in score.hard_failures)


def test_calibration_case_penalizes_collapsed_uncertainty() -> None:
    case_id = "2012-03-I-CA"
    reference = reference_submission(case_id)
    payload = reference.model_dump(mode="python")
    payload.update(
        {
            "primary_confidence": 0.90,
            "alternative_confidence": 0.09,
            "unresolved_questions": (),
        }
    )
    submission = Gold10Submission.model_validate(payload)
    score = score_submission(case_id, submission)
    assert score.hard_failures == ()
    assert score.component_scores["calibration_integrity"] == 0.0
    assert score.reward < 1.0


def test_submission_schema_has_no_ground_truth_claim_kind() -> None:
    with pytest.raises(ValidationError):
        EpistemicClaim.model_validate(
            {
                "claim_id": "forbidden",
                "statement": "Institutional findings are private truth.",
                "kind": "ground_truth",
                "evidence_ids": ("evidence-1",),
            }
        )


def test_submission_requires_probability_mass_for_uncertainty() -> None:
    with pytest.raises(ValidationError):
        Gold10Submission(
            primary_hypothesis="Primary",
            alternative_hypothesis="Alternative",
            primary_confidence=0.8,
            alternative_confidence=0.3,
            evidence_ids=("evidence-1",),
        )
