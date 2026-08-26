from __future__ import annotations

from collections import Counter
from numbers import Number
from typing import Any

from investigation_world.operational.models import (
    ActionEvent,
    AssertionComparison,
    EpisodeSubmission,
    HiddenOracle,
    OperationalInvariant,
    StateAssertion,
    VerificationBreakdown,
)


def _value_matches(actual: Any, assertion: StateAssertion) -> bool:
    expected = assertion.expected_value
    comparison = assertion.comparison
    if assertion.tolerance is not None and isinstance(actual, Number) and isinstance(expected, Number):
        if comparison == AssertionComparison.EQUAL:
            return abs(float(actual) - float(expected)) <= assertion.tolerance
    if comparison == AssertionComparison.EQUAL:
        return actual == expected
    if comparison == AssertionComparison.NOT_EQUAL:
        return actual != expected
    if comparison == AssertionComparison.LESS_THAN:
        return actual is not None and actual < expected
    if comparison == AssertionComparison.LESS_THAN_OR_EQUAL:
        return actual is not None and actual <= expected
    if comparison == AssertionComparison.GREATER_THAN:
        return actual is not None and actual > expected
    if comparison == AssertionComparison.GREATER_THAN_OR_EQUAL:
        return actual is not None and actual >= expected
    if comparison == AssertionComparison.CONTAINS:
        try:
            return expected in actual
        except TypeError:
            return False
    if comparison == AssertionComparison.IN:
        try:
            return actual in expected
        except TypeError:
            return False
    return False


def _assertion_holds(state: dict[str, Any], assertion: StateAssertion) -> bool:
    return _value_matches(state.get(assertion.key()), assertion)


def _violated_invariants(
    oracle: HiddenOracle,
    state: dict[str, Any],
    events: list[ActionEvent],
) -> list[OperationalInvariant]:
    violations: dict[str, OperationalInvariant] = {}
    for invariant in oracle.invariants:
        if invariant.scope == "final" and not _assertion_holds(state, invariant.assertion):
            violations[invariant.invariant_id] = invariant

    replay_state = dict(oracle.initial_state)
    always_invariants = [invariant for invariant in oracle.invariants if invariant.scope == "always"]
    for invariant in always_invariants:
        if not _assertion_holds(replay_state, invariant.assertion):
            violations[invariant.invariant_id] = invariant
    for event in events:
        replay_state.update(event.state_changes)
        for invariant in always_invariants:
            if not _assertion_holds(replay_state, invariant.assertion):
                violations[invariant.invariant_id] = invariant
    return list(violations.values())


def _ordered_subsequence(sequence: list[str], required: list[str]) -> bool:
    if not required:
        return True
    cursor = 0
    for action in sequence:
        if action == required[cursor]:
            cursor += 1
            if cursor == len(required):
                return True
    return False


def verify_operational_episode(
    *,
    oracle: HiddenOracle,
    state: dict[str, Any],
    events: list[ActionEvent],
    submission: EpisodeSubmission,
    tool_calls: int,
    cost_spent: int,
) -> VerificationBreakdown:
    """Independently score final state, invariants, process, evidence, and side effects.

    The public seven-dimensional contract is unchanged. Internally, process now
    distinguishes successful effects from blocked attempts, supports action counts
    and ordering, while invariants can be final-state or trajectory-wide.
    """

    targets_met = sum(1 for assertion in oracle.target_state if _assertion_holds(state, assertion))
    target_total = len(oracle.target_state)
    state_score = targets_met / target_total if target_total else 1.0
    outcome_score = 1.0 if targets_met == target_total else state_score

    violated = _violated_invariants(oracle, state, events)
    invariant_violations = sorted(invariant.invariant_id for invariant in violated)

    effective_events = [event for event in events if event.effect_applied and not event.blocked]
    effective_action_names = [event.action_name for event in effective_events]
    action_counts = Counter(effective_action_names)

    required_counts = {action: 1 for action in oracle.required_actions}
    for action, count in oracle.required_action_counts.items():
        required_counts[action] = max(required_counts.get(action, 0), count)
    missing_required = sorted(
        action for action, count in required_counts.items() if action_counts[action] < count
    )
    required_units = sum(required_counts.values())
    satisfied_units = sum(min(action_counts[action], count) for action, count in required_counts.items())
    process_score = satisfied_units / required_units if required_units else 1.0

    process_violations: list[str] = []
    if oracle.required_action_order and not _ordered_subsequence(
        effective_action_names, oracle.required_action_order
    ):
        process_violations.append("required_action_order")
        process_score *= 0.5
    blocked_required = sorted(
        {
            event.action_name
            for event in events
            if event.blocked and event.action_name in required_counts
        }
    )
    if blocked_required:
        process_violations.extend(f"blocked_required:{name}" for name in blocked_required)

    forbidden_taken = sorted(
        {
            event.action_name
            for event in events
            if event.forbidden or event.action_name in oracle.forbidden_actions
        }
    )

    severity_penalty = {
        "low": 0.12,
        "medium": 0.22,
        "high": 0.35,
        "critical": 0.60,
    }
    constraint_penalty = sum(severity_penalty[item.severity] for item in violated)
    constraints_score = max(0.0, 1.0 - constraint_penalty)
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
    efficiency_score = max(
        0.0,
        1.0
        - 0.5 * max(0.0, budget_ratio - 0.5)
        - 0.5 * max(0.0, call_ratio - 0.5),
    )

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
        process_violations=process_violations,
    )
