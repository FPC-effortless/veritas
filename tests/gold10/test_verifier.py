import pytest
from pydantic import ValidationError

from investigation_world.gold10 import (
    EpistemicClaim,
    EpistemicClaimKind,
    Gold10Submission,
    build_task,
    reference_submission,
    score_submission,
)


def test_reference_submissions_are_deterministic_and_bounded() -> None:
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
        assert first.reward == 0.75
        assert first.hard_failures == ()
        assert first.component_scores["canonical_target_fidelity"] == 1.0
        assert first.component_scores["hypothesis_structure"] == 1.0


def test_arbitrary_hypothesis_claims_cannot_receive_positive_reward() -> None:
    case_id = "2005-04-I-TX"
    task = build_task(case_id)
    evidence_ids = tuple(item.evidence_id for item in task.available_evidence)
    submission = Gold10Submission(
        primary_hypothesis="Arbitrary primary text.",
        alternative_hypothesis="Arbitrary alternative text.",
        primary_confidence=0.5,
        alternative_confidence=0.25,
        evidence_ids=evidence_ids,
        claims=(
            EpistemicClaim(
                claim_id="primary",
                statement="Arbitrary primary text.",
                kind=EpistemicClaimKind.HYPOTHESIS,
                evidence_ids=evidence_ids,
            ),
            EpistemicClaim(
                claim_id="alternative",
                statement="Arbitrary alternative text.",
                kind=EpistemicClaimKind.HYPOTHESIS,
                evidence_ids=evidence_ids,
            ),
        ),
        unresolved_questions=("Boilerplate uncertainty.",),
    )
    score = score_submission(case_id, submission)
    assert score.reward == 0.0
    assert "no_canonical_verifier_target" in score.hard_failures


def test_canonical_target_statement_mismatch_is_a_hard_failure() -> None:
    case_id = "2005-04-I-TX"
    reference = reference_submission(case_id)
    payload = reference.model_dump(mode="python")
    claims = list(payload["claims"])
    target_index = next(
        index
        for index, claim in enumerate(claims)
        if claim.get("canonical_target_id") is not None
    )
    claims[target_index] = {
        **claims[target_index],
        "statement": "Fabricated canonical target statement.",
    }
    payload["claims"] = claims
    score = score_submission(case_id, Gold10Submission.model_validate(payload))
    assert score.reward == 0.0
    assert any(
        item.startswith("canonical_target_statement_mismatch:")
        for item in score.hard_failures
    )


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
    assert score.reward < score_submission(case_id, reference).reward


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
