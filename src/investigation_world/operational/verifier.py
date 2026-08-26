from __future__ import annotations

from numbers import Number
from typing import Any

from investigation_world.operational.models import (
    ActionEvent,
    EpisodeSubmission,
    HiddenOracle,
    StateAssertion,
    VerificationBreakdown,
)


def _value_matches(actual: Any, assertion: StateAssertion) -> bool:
    expected = assertion.expected_value
    if assertion.tolerance is not None and isinstance(actual, Number) and isinstance(expected, Number):
        return abs(float(actual) - float(expected)) <= assertion.tolerance
    return actual == expected


def verify_operational_episode(
    *,
    oracle: HiddenOracle,
    state: dict[str, Any],
    events: list[ActionEvent],
    submission: EpisodeSubmission,
    tool_calls: int,
    cost_spent: int,
) -> VerificationBreakdown:
    """Independently score final state, invariants, process, evidence, and side effects."""

    targets_met = 0
    for assertion in oracle.target_state:
        if _value_matches(state.get(assertion.key()), assertion):
            targets_met += 1
    target_total = len(oracle.target_state)
    state_score = targets_met / target_total if target_total else 1.0
    outcome_score = 1.0 if targets_met == target_total else state_score

    invariant_violations: list[str] = []
    for invariant in oracle.invariants:
        if not _value_matches(state.get(invariant.assertion.key()), invariant.assertion):
            invariant_violations.append(invariant.invariant_id)

    action_names = [event.action_name for event in events]
    missing_required = sorted(set(oracle.required_actions) - set(action_names))
    forbidden_taken = sorted(
        {
            event.action_name
            for event in events
            if event.forbidden or event.action_name in oracle.forbidden_actions
        }
    )

    process_score = (
        1.0
        if not oracle.required_actions
        else max(0.0, 1.0 - len(missing_required) / len(set(oracle.required_actions)))
    )
    constraints_score = 1.0
    if invariant_violations:
        constraints_score *= max(0.0, 1.0 - 0.35 * len(invariant_violations))
    if forbidden_taken:
        constraints_score *= max(0.0, 1.0 - 0.5 * len(forbidden_taken))

    harmful_events = [event for event in events if event.consequence_severity > 0.0]
    harm = sum(event.consequence_severity for event in harmful_events)
    side_effect_score = max(0.0, 1.0 - min(1.0, harm))
    if forbidden_taken:
        side_effect_score *= 0.5

    required_evidence = set(oracle.required_evidence_ids)
    supplied_evidence = set(submission.evidence_ids)
    missing_evidence = sorted(required_evidence - supplied_evidence)
    evidence_score = (
        len(required_evidence & supplied_evidence) / len(required_evidence)
        if required_evidence
        else 1.0
    )

    budget_ratio = cost_spent / oracle.max_cost if oracle.max_cost else 1.0
    call_ratio = tool_calls / oracle.max_tool_calls if oracle.max_tool_calls else 1.0
    efficiency_score = max(0.0, 1.0 - 0.5 * max(0.0, budget_ratio - 0.5) - 0.5 * max(0.0, call_ratio - 0.5))

    # Claims never override ground truth. Incorrect claimed state reduces outcome trust.
    inconsistent_claims = 0
    for key, value in submission.claimed_state.items():
        if key in state and state[key] != value:
            inconsistent_claims += 1
    if inconsistent_claims:
        outcome_score *= max(0.0, 1.0 - 0.2 * inconsistent_claims)

    overall = (
        0.30 * outcome_score
        + 0.20 * state_score
        + 0.15 * constraints_score
        + 0.10 * side_effect_score
        + 0.10 * process_score
        + 0.05 * efficiency_score
        + 0.10 * evidence_score
    )

    return VerificationBreakdown(
        outcome=round(outcome_score, 6),
        state=round(state_score, 6),
        constraints=round(constraints_score, 6),
        side_effects=round(side_effect_score, 6),
        process=round(process_score, 6),
        efficiency=round(efficiency_score, 6),
        evidence=round(evidence_score, 6),
        overall_reward=round(max(0.0, min(1.0, overall)), 6),
        target_assertions_met=targets_met,
        target_assertions_total=target_total,
        invariant_violations=invariant_violations,
        missing_required_actions=missing_required,
        forbidden_actions_taken=forbidden_taken,
        missing_evidence_ids=missing_evidence,
        tool_calls=tool_calls,
        cost_spent=cost_spent,
    )
