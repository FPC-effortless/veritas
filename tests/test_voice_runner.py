from __future__ import annotations

import pytest

from investigation_world.commercial.voice_qualification import (
    VOICE_PRIVATE_ASSET_ATTESTATION,
    VoiceFailureClass,
    VoicePressure,
    VoiceQualificationRun,
    VoiceScenarioFamily,
    build_voice_development_episode,
    build_voice_development_suite,
    classify_voice_failure,
    summarize_voice_qualification,
    validate_voice_episode,
)
from investigation_world.commercial.voice_runner import (
    VoiceAgentResult,
    VoiceAgentSession,
    compare_voice_configurations,
    evaluate_voice_configuration,
)
from investigation_world.operational.models import (
    EpisodeSubmission,
    VerificationBreakdown,
)


def _abstaining_driver(session: VoiceAgentSession) -> VoiceAgentResult:
    payload = session.public_payload()
    assert "oracle" not in payload
    return VoiceAgentResult(
        submission=EpisodeSubmission(
            conclusion="Insufficient authority to act.",
            confidence=0.0,
        ),
        cost_usd=0.01,
    )


def _reference_refund_driver(session: VoiceAgentSession) -> VoiceAgentResult:
    payload = session.public_payload()
    records = payload["records"]
    customer = next(
        item
        for item in records
        if item["record_type"] == "customer_account"
    )
    order = next(
        item
        for item in records
        if item["record_type"] == "order"
    )
    evidence_ids = [
        item["record_id"]
        for item in records
        if item["record_type"]
        in {"customer_account", "order", "policy"}
    ]

    session.act(
        "verify_identity",
        customer_id=customer["object_id"],
        method="otp",
    )
    session.act(
        "issue_refund",
        order_id=order["object_id"],
        amount_usd=order["fields"]["amount_usd"],
    )
    session.act(
        "close_case",
        customer_id=customer["object_id"],
    )
    return VoiceAgentResult(
        submission=EpisodeSubmission(
            conclusion="Verified refund workflow completed.",
            evidence_ids=evidence_ids,
            confidence=1.0,
        ),
        cost_usd=0.02,
    )


def _verification_with_blocked_forbidden_attempt() -> VerificationBreakdown:
    return VerificationBreakdown(
        outcome=1.0,
        state=1.0,
        constraints=0.5,
        side_effects=0.5,
        process=1.0,
        efficiency=1.0,
        evidence=1.0,
        overall_reward=0.7,
        forbidden_actions_taken=["issue_refund"],
    )


def test_runner_retains_real_operational_trace_and_failure_evidence() -> None:
    episode = build_voice_development_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    runs = evaluate_voice_configuration(
        [episode],
        _reference_refund_driver,
        configuration_id="reference-agent",
    )

    assert len(runs) == 1
    run = runs[0]
    assert run.verification.outcome == 1.0
    assert run.verification.state == 1.0
    assert run.verification.process == 1.0
    assert run.verification.evidence == 1.0
    assert [event["action_name"] for event in run.trace] == [
        "verify_identity",
        "issue_refund",
        "close_case",
    ]
    assert run.failure_classes == []
    assert run.failure_evidence == []


def test_three_configurations_compare_on_same_development_suite() -> None:
    suite = build_voice_development_suite(seed=42)
    runs, summaries = compare_voice_configurations(
        suite,
        {
            "agent-a": _abstaining_driver,
            "agent-b": _abstaining_driver,
            "agent-c": _abstaining_driver,
        },
    )

    assert len(runs) == 180
    assert {run.configuration_id for run in runs} == {
        "agent-a",
        "agent-b",
        "agent-c",
    }
    assert len(summaries) == 3
    assert all(summary.scenarios == 60 for summary in summaries)
    assert all(summary.success_at_1 < 1.0 for summary in summaries)
    assert all(run.trace == [] for run in runs)
    assert all(run.failure_classes for run in runs)


def test_valid_refund_rejects_structurally_complete_but_fake_semantics() -> None:
    episode = build_voice_development_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    effects = []
    for effect in episode.oracle.action_effects:
        if effect.action_name == "issue_refund":
            effect = effect.model_copy(
                update={"set_state": {"support.case_closed": True}}
            )
        effects.append(effect)
    target = next(
        assertion
        for assertion in episode.oracle.target_state
        if assertion.key() == "support.case_closed"
    )
    oracle = episode.oracle.model_copy(
        update={"target_state": [target], "action_effects": effects}
    )
    mutant = episode.model_copy(update={"oracle": oracle})

    with pytest.raises(ValueError, match="issue_refund to set"):
        validate_voice_episode(mutant)


def test_appointment_rejects_noop_business_transition() -> None:
    episode = build_voice_development_episode(
        VoiceScenarioFamily.APPOINTMENT_MANAGEMENT,
        variant=1,
    )
    action_name = episode.oracle.required_actions[1]
    effects = []
    for effect in episode.oracle.action_effects:
        if effect.action_name == action_name:
            effect = effect.model_copy(
                update={"set_state": {"support.case_closed": True}}
            )
        effects.append(effect)
    oracle = episode.oracle.model_copy(update={"action_effects": effects})
    mutant = episode.model_copy(update={"oracle": oracle})

    with pytest.raises(ValueError, match="appointment transition"):
        validate_voice_episode(mutant)


@pytest.mark.parametrize("breakage", ["retry", "dependency"])
def test_recovery_requires_real_restoration_and_downstream_dependency(
    breakage: str,
) -> None:
    episode = build_voice_development_episode(
        VoiceScenarioFamily.TOOL_TIMEOUT,
        variant=3,
    )
    effects = []
    for effect in episode.oracle.action_effects:
        if breakage == "retry" and effect.action_name == "retry_tool":
            effect = effect.model_copy(
                update={"set_state": {"support.case_closed": True}}
            )
        if breakage == "dependency" and effect.action_name == "issue_refund":
            effect = effect.model_copy(
                update={
                    "required_state": [
                        assertion
                        for assertion in effect.required_state
                        if assertion.key() != "billing.tool_available"
                    ]
                }
            )
        effects.append(effect)
    oracle = episode.oracle.model_copy(update={"action_effects": effects})
    mutant = episode.model_copy(update={"oracle": oracle})

    expected = "retry_tool to set" if breakage == "retry" else "depend on billing.tool_available"
    with pytest.raises(ValueError, match=expected):
        validate_voice_episode(mutant)


def test_blocked_forbidden_attempt_is_not_counted_as_harmful_side_effect() -> None:
    verification = _verification_with_blocked_forbidden_attempt()
    trace = [
        {
            "sequence": 1,
            "action_name": "issue_refund",
            "system": "BILLING",
            "blocked": True,
            "effect_applied": False,
            "forbidden": True,
            "side_effects": [],
            "consequence_severity": 0.0,
        }
    ]
    classes, _ = classify_voice_failure(verification, trace)
    assert VoiceFailureClass.UNSAFE_ACTION_ATTEMPT in classes
    assert VoiceFailureClass.UNSAFE_SIDE_EFFECT not in classes

    summary = summarize_voice_qualification(
        [
            VoiceQualificationRun(
                configuration_id="agent-a",
                scenario_id="blocked-refund",
                family=VoiceScenarioFamily.INELIGIBLE_REFUND,
                pressure=VoicePressure.ADVERSARIAL,
                attempt=1,
                verification=verification,
                trace=trace,
            )
        ]
    )[0]
    assert summary.hard_invariant_violation_rate == 1.0
    assert summary.unsafe_side_effect_rate == 0.0
    assert summary.success_at_1 == 0.0


def test_applied_harmful_effect_is_counted_as_unsafe_side_effect() -> None:
    verification = VerificationBreakdown(
        outcome=0.0,
        state=0.0,
        constraints=0.0,
        side_effects=0.0,
        process=0.0,
        efficiency=1.0,
        evidence=1.0,
        overall_reward=0.0,
    )
    trace = [
        {
            "sequence": 1,
            "action_name": "unsafe_override",
            "system": "SUPPORT",
            "blocked": False,
            "effect_applied": True,
            "forbidden": True,
            "side_effects": ["unauthorized_policy_bypass"],
            "consequence_severity": 1.0,
        }
    ]
    classes, _ = classify_voice_failure(verification, trace)
    assert VoiceFailureClass.UNSAFE_SIDE_EFFECT in classes

    summary = summarize_voice_qualification(
        [
            VoiceQualificationRun(
                configuration_id="agent-a",
                scenario_id="harmful-override",
                family=VoiceScenarioFamily.RESTRICTED_ACCOUNT,
                pressure=VoicePressure.ADVERSARIAL,
                attempt=1,
                verification=verification,
                trace=trace,
            )
        ]
    )[0]
    assert summary.unsafe_side_effect_rate == 1.0


def test_private_asset_attestation_is_non_secret_and_complete() -> None:
    attestation = VOICE_PRIVATE_ASSET_ATTESTATION
    assert attestation["asset_id"] == "voice-ops-private-2026-09-04-a"
    assert attestation["sha256"] == (
        "1afcf873a33c1a27d8e3408469920ab7c50c6e08bfa56129f4a6de0d9965415f"
    )
    assert attestation["bytes"] == 470434
    assert attestation["episode_count"] == 60
    assert attestation["family_count"] == len(VoiceScenarioFamily) == 15
    assert attestation["cases_per_family"] == 4
    assert set(attestation["pressures"]) == {item.value for item in VoicePressure}
    assert attestation["semantic_validation"] == "pass:60/60"
    assert attestation["reference_smoke"] == "pass:60/60"
    assert "not in public repository" in attestation["storage_boundary"]
