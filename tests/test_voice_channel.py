from __future__ import annotations

import json

import pytest

from investigation_world.commercial.voice_channel import (
    VoiceChannelRuntime,
    VoiceEventKind,
    VoiceSpeaker,
    measure_voice_channel,
    replay_voice_events,
)
from investigation_world.commercial.voice_qualification import (
    VoiceScenarioFamily,
    build_voice_qualification_episode,
    qualification_submission,
)


def _object_id(episode, record_type: str) -> str:
    return next(
        record.object_id
        for record in episode.records
        if record.record_type == record_type
    )


def test_voice_events_keep_harness_only_labels_private() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    channel = VoiceChannelRuntime(episode)

    channel.asr_hypothesis(
        "refund order sixty forty two",
        0.48,
        at_ms=100,
        critical_slot=True,
        resolved_before_action=False,
        led_to_wrong_action=True,
    )
    public = channel.public_events()[0]
    serialized = json.dumps(public, sort_keys=True)

    assert public["kind"] == "ASRHypothesis"
    assert public["payload"]["confidence"] == 0.48
    assert "harness_payload" not in public
    assert "led_to_wrong_action" not in serialized
    assert "critical_slot" not in serialized


def test_interruption_requires_active_agent_speech_and_can_recover() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    channel = VoiceChannelRuntime(episode)

    with pytest.raises(ValueError, match="active agent speech"):
        channel.user_barge_in(at_ms=10)

    channel.agent_speech_started("I can help with that refund.", at_ms=20)
    interrupted, barge_in = channel.user_barge_in(at_ms=30)
    channel.speech_final(
        VoiceSpeaker.USER,
        "Wait, I meant the other order.",
        at_ms=50,
    )
    channel.agent_speech_started("Understood. I will verify the other order.", at_ms=90)

    assert interrupted.kind == VoiceEventKind.AGENT_SPEECH_INTERRUPTED
    assert barge_in.kind == VoiceEventKind.USER_BARGE_IN
    metrics = measure_voice_channel(channel.events)
    assert metrics.interruptions == 1
    assert metrics.interruption_recovery_rate == 1.0
    assert metrics.response_latency_p50_ms == 40.0


def test_completed_tool_events_replay_to_same_operational_verification() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    customer_id = _object_id(episode, "customer_account")
    order_id = _object_id(episode, "order")
    channel = VoiceChannelRuntime(episode)

    channel.tool_call(
        "call-auth",
        "verify_identity",
        {"customer_id": customer_id, "method": "otp"},
        started_at_ms=100,
        completed_at_ms=140,
    )
    channel.tool_call(
        "call-refund",
        "issue_refund",
        {"order_id": order_id, "amount_usd": 80},
        started_at_ms=200,
        completed_at_ms=260,
    )
    channel.tool_call(
        "call-close",
        "close_case",
        {"customer_id": customer_id},
        started_at_ms=300,
        completed_at_ms=320,
    )

    original = channel.runtime.submit(qualification_submission(episode))
    replayed_runtime = replay_voice_events(episode, channel.events)
    replayed = replayed_runtime.submit(qualification_submission(episode))

    assert original == replayed
    assert original.outcome == 1.0
    assert original.state == 1.0
    assert original.process == 1.0
    assert original.constraints == 1.0
    assert original.side_effects == 1.0


def test_unknown_tool_outcome_is_not_replayed_as_known_success() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    customer_id = _object_id(episode, "customer_account")
    order_id = _object_id(episode, "order")
    channel = VoiceChannelRuntime(episode)

    channel.tool_call(
        "call-auth",
        "verify_identity",
        {"customer_id": customer_id, "method": "otp"},
        started_at_ms=10,
        completed_at_ms=20,
    )
    channel.tool_unknown_outcome(
        "call-refund-unknown",
        "issue_refund",
        {"order_id": order_id, "amount_usd": 80},
        started_at_ms=30,
        unknown_at_ms=60,
    )

    replayed = replay_voice_events(episode, channel.events)
    assert replayed.state_snapshot()[f"{order_id}.refund_count"] == 0
    assert any(
        event.kind == VoiceEventKind.TOOL_CALL_UNKNOWN_OUTCOME
        for event in channel.events
    )

    with pytest.raises(ValueError, match="already used"):
        channel.tool_unknown_outcome(
            "call-refund-unknown",
            "issue_refund",
            {"order_id": order_id, "amount_usd": 80},
            started_at_ms=70,
            unknown_at_ms=80,
        )


def test_disconnect_blocks_mutation_until_call_resumes() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    customer_id = _object_id(episode, "customer_account")
    channel = VoiceChannelRuntime(episode)

    channel.disconnect(at_ms=10)
    with pytest.raises(ValueError, match="while disconnected"):
        channel.tool_call(
            "call-auth",
            "verify_identity",
            {"customer_id": customer_id, "method": "otp"},
            started_at_ms=20,
            completed_at_ms=30,
        )

    channel.resume(at_ms=40)
    channel.tool_call(
        "call-auth",
        "verify_identity",
        {"customer_id": customer_id, "method": "otp"},
        started_at_ms=50,
        completed_at_ms=60,
    )
    metrics = measure_voice_channel(channel.events)
    assert metrics.disconnect_recovery_rate == 1.0


def test_handoff_contains_observed_public_continuity_not_hidden_state() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.RESTRICTED_ACCOUNT,
        variant=0,
    )
    customer_id = _object_id(episode, "customer_account")
    channel = VoiceChannelRuntime(episode)

    channel.speech_final(
        VoiceSpeaker.USER,
        "I need help changing this restricted account.",
        at_ms=10,
    )
    channel.tool_call(
        "call-inspect",
        "inspect_account",
        {"customer_id": customer_id},
        started_at_ms=20,
        completed_at_ms=30,
    )
    channel.agent_speech_started("I need to bring in a specialist.", at_ms=40)
    channel.speech_final(
        VoiceSpeaker.AGENT,
        "I need to bring in a specialist.",
        at_ms=50,
    )
    snapshot = channel.handoff(
        "restricted_account",
        at_ms=60,
        continuity_ok=True,
    )
    public_event = channel.public_events()[-1]
    serialized = json.dumps(public_event, sort_keys=True)

    assert snapshot.completed_tool_calls == ["call-inspect"]
    assert snapshot.observed_object_ids == [customer_id]
    assert snapshot.last_user_utterance is not None
    assert "oracle" not in serialized
    assert "initial_state" not in serialized
    assert "state_continuity_ok" not in serialized
    assert measure_voice_channel(channel.events).handoff_state_continuity_rate == 1.0


def test_voice_metrics_measure_asr_premature_action_and_resolution_latency() -> None:
    episode = build_voice_qualification_episode(
        VoiceScenarioFamily.VALID_REFUND,
        variant=0,
    )
    customer_id = _object_id(episode, "customer_account")
    channel = VoiceChannelRuntime(episode)

    channel.speech_final(VoiceSpeaker.USER, "Refund order sixty forty two.", at_ms=100)
    channel.asr_hypothesis(
        "refund order sixteen forty two",
        0.55,
        at_ms=110,
        critical_slot=True,
        resolved_before_action=False,
        led_to_wrong_action=True,
    )
    channel.agent_speech_started("Let me confirm that order number.", at_ms=180)
    channel.speech_final(
        VoiceSpeaker.AGENT,
        "Let me confirm that order number.",
        at_ms=210,
    )
    channel.tool_call(
        "call-inspect",
        "inspect_account",
        {"customer_id": customer_id},
        started_at_ms=220,
        completed_at_ms=250,
        premature=True,
    )
    channel.mark_verified_resolution(at_ms=400)

    metrics = measure_voice_channel(channel.events)
    assert metrics.critical_asr_hypotheses == 1
    assert metrics.asr_induced_action_error_rate == 1.0
    assert metrics.clarification_correctness == 0.0
    assert metrics.premature_action_rate == 1.0
    assert metrics.response_latency_p50_ms == 80.0
    assert metrics.time_to_verified_resolution_ms == 300
