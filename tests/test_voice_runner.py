from __future__ import annotations

from investigation_world.commercial.voice_qualification import (
    VoiceScenarioFamily,
    build_voice_development_episode,
    build_voice_development_suite,
)
from investigation_world.commercial.voice_runner import (
    VoiceAgentResult,
    VoiceAgentSession,
    compare_voice_configurations,
    evaluate_voice_configuration,
)
from investigation_world.operational.models import EpisodeSubmission


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
