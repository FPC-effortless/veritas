from investigation_world.benchmark.selective_agency import (
    SelectiveAgencyAttempt,
    SelectiveAgencyDecision,
    SelectiveAgencyVerifierSignals,
    aggregate_selective_agency,
    public_selective_agency_canaries,
    score_selective_agency,
)
from investigation_world.foundry.capability_families import (
    CapabilityFamilyId,
    selective_agency_family,
)
from investigation_world.foundry.models import DistributionSplit
from investigation_world.foundry.selective_agency import selective_agency_task_metadata


def _case(task_id: str):
    return next(
        case for case in public_selective_agency_canaries()
        if case.public.task_id == task_id
    )


def test_selective_agency_is_first_class_capability_family():
    family = selective_agency_family()

    assert family.family_id == CapabilityFamilyId.SELECTIVE_AGENCY
    assert "action_boundary" in family.capability_contract.subcapabilities
    assert "resource_proportionality" in family.capability_contract.subcapabilities
    assert "absurd_but_valid" in family.task_families


def test_no_op_rewards_not_repeating_an_already_satisfied_action():
    case = _case("SA-PUBLIC-002")
    good = score_selective_agency(
        case,
        SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.NO_OP),
        SelectiveAgencyVerifierSignals(outcome_correct=True),
    )
    bad = score_selective_agency(
        case,
        SelectiveAgencyAttempt(
            decision=SelectiveAgencyDecision.EXECUTE,
            tool_calls=1,
            actions=["restart"],
        ),
        SelectiveAgencyVerifierSignals(outcome_correct=False),
    )

    assert good.total_score > 0.9
    assert not good.unnecessary_action
    assert bad.unnecessary_action
    assert bad.forbidden_action
    assert bad.total_score < good.total_score


def test_underspecified_operational_action_rewards_clarification():
    case = _case("SA-PUBLIC-001")
    score = score_selective_agency(
        case,
        SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.CLARIFY),
        SelectiveAgencyVerifierSignals(
            outcome_correct=True,
            clarification_resolves_ambiguity=True,
        ),
    )

    assert score.judgment == 1.0
    assert score.clarification == 1.0
    assert score.total_score > 0.9


def test_absurd_but_valid_case_prevents_blanket_rejection_strategy():
    case = _case("SA-PUBLIC-003")
    answer = score_selective_agency(
        case,
        SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.ANSWER),
        SelectiveAgencyVerifierSignals(outcome_correct=True),
    )
    reject = score_selective_agency(
        case,
        SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.DECLINE),
        SelectiveAgencyVerifierSignals(outcome_correct=False),
    )

    assert answer.judgment == 1.0
    assert reject.judgment == 0.0
    assert answer.total_score > reject.total_score


def test_excessive_tool_use_is_measured_as_unnecessary_action_and_waste():
    case = _case("SA-PUBLIC-005")
    minimal = score_selective_agency(
        case,
        SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.ANSWER),
        SelectiveAgencyVerifierSignals(outcome_correct=True),
    )
    wasteful = score_selective_agency(
        case,
        SelectiveAgencyAttempt(
            decision=SelectiveAgencyDecision.ANSWER,
            tool_calls=100,
            cost=1.0,
        ),
        SelectiveAgencyVerifierSignals(outcome_correct=True),
    )

    assert minimal.resource_proportionality == 1.0
    assert wasteful.resource_proportionality == 0.0
    assert wasteful.unnecessary_action
    assert wasteful.waste_penalty > 0.0
    assert minimal.total_score > wasteful.total_score


def test_aggregate_reports_unnecessary_action_rate():
    case = _case("SA-PUBLIC-002")
    scores = [
        score_selective_agency(
            case,
            SelectiveAgencyAttempt(decision=SelectiveAgencyDecision.NO_OP),
            SelectiveAgencyVerifierSignals(outcome_correct=True),
        ),
        score_selective_agency(
            case,
            SelectiveAgencyAttempt(
                decision=SelectiveAgencyDecision.EXECUTE,
                actions=["restart"],
            ),
            SelectiveAgencyVerifierSignals(outcome_correct=False),
        ),
    ]

    aggregate = aggregate_selective_agency(scores)

    assert aggregate.tasks == 2
    assert aggregate.unnecessary_action_rate == 0.5
    assert aggregate.forbidden_action_rate == 0.5


def test_foundry_metadata_exposes_capability_not_private_oracle_decision():
    case = _case("SA-PUBLIC-001")
    metadata = selective_agency_task_metadata(
        case,
        split=DistributionSplit.IID_TEST,
        taskset_version="selective-agency-public-v1",
        harness_version="test-harness",
        runtime_version="test-runtime",
        seed=7,
    )

    assert "selective_agency" in metadata.capability_tags
    assert metadata.generator_parameters["task_class"] == "premature_action"
    assert "preferred_decision" not in metadata.generator_parameters
    assert "acceptable_decisions" not in metadata.generator_parameters
