from __future__ import annotations

import json
from enum import StrEnum
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational.models import (
    EpisodeSubmission,
    OperationalEpisode,
    VerificationBreakdown,
)
from investigation_world.operational.runtime import OperationalRuntime

VOICE_CHANNEL_VERSION = "veritas-voice-channel-v1"


class VoiceEventKind(StrEnum):
    SPEECH_STARTED = "SpeechStarted"
    SPEECH_PARTIAL = "SpeechPartial"
    SPEECH_FINAL = "SpeechFinal"
    AGENT_SPEECH_STARTED = "AgentSpeechStarted"
    AGENT_SPEECH_INTERRUPTED = "AgentSpeechInterrupted"
    USER_BARGE_IN = "UserBargeIn"
    SILENCE = "Silence"
    TURN_TIMEOUT = "TurnTimeout"
    ASR_HYPOTHESIS = "ASRHypothesis"
    TOOL_CALL_STARTED = "ToolCallStarted"
    TOOL_CALL_COMPLETED = "ToolCallCompleted"
    TOOL_CALL_UNKNOWN_OUTCOME = "ToolCallUnknownOutcome"
    HUMAN_HANDOFF = "HumanHandoff"
    CALL_DISCONNECTED = "CallDisconnected"
    CALL_RESUMED = "CallResumed"


class VoiceSpeaker(StrEnum):
    USER = "user"
    AGENT = "agent"
    HUMAN = "human"
    SYSTEM = "system"


class VoiceChannelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int = Field(ge=1)
    at_ms: int = Field(ge=0)
    kind: VoiceEventKind
    speaker: VoiceSpeaker | None = None
    text: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    harness_payload: dict[str, Any] = Field(default_factory=dict)

    def public_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"harness_payload"})


class VoiceHandoffSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str
    task_id: str
    last_user_utterance: str | None = None
    last_agent_utterance: str | None = None
    completed_tool_calls: list[str] = Field(default_factory=list)
    unresolved_tool_calls: list[str] = Field(default_factory=list)
    observed_object_ids: list[str] = Field(default_factory=list)


class VoiceChannelMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: int
    interruptions: int
    interruption_recovery_rate: float
    critical_asr_hypotheses: int
    asr_induced_action_error_rate: float
    clarification_correctness: float
    premature_action_rate: float
    duplicate_side_effect_rate: float
    handoff_state_continuity_rate: float
    disconnect_recovery_rate: float
    response_latency_p50_ms: float | None
    response_latency_p95_ms: float | None
    time_to_verified_resolution_ms: int | None


class PendingVoiceToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    call_id: str
    action_name: str
    parameters: dict[str, Any]
    premature: bool = False


class VoiceChannelRuntime:
    """Provider-neutral voice/session layer above ``OperationalRuntime``.

    Tool calls have an explicit asynchronous lifecycle. A call may start while the
    voice session is connected and reach a completed or unknown terminal outcome
    after a disconnect. Hidden operational truth and verifier results remain in the
    harness-only side of the trace.
    """

    def __init__(self, episode: OperationalEpisode):
        self.runtime = OperationalRuntime(episode)
        self.events: list[VoiceChannelEvent] = []
        self.connected = True
        self.agent_speaking = False
        self.user_speaking = False
        self._last_at_ms = -1
        self._pending_calls: dict[str, PendingVoiceToolCall] = {}
        self._completed_calls: set[str] = set()
        self._unknown_calls: set[str] = set()
        self._observed_object_ids: set[str] = set()
        self._seen_side_effects: set[str] = set()
        self._last_user_utterance: str | None = None
        self._last_agent_utterance: str | None = None

    def _emit(
        self,
        kind: VoiceEventKind,
        *,
        at_ms: int,
        speaker: VoiceSpeaker | None = None,
        text: str | None = None,
        payload: dict[str, Any] | None = None,
        harness_payload: dict[str, Any] | None = None,
    ) -> VoiceChannelEvent:
        if at_ms < self._last_at_ms:
            raise ValueError("voice event timestamps must be monotonic")
        self._last_at_ms = at_ms
        event = VoiceChannelEvent(
            sequence=len(self.events) + 1,
            at_ms=at_ms,
            kind=kind,
            speaker=speaker,
            text=text,
            payload=payload or {},
            harness_payload=harness_payload or {},
        )
        self.events.append(event)
        return event

    def speech_started(
        self,
        speaker: VoiceSpeaker,
        *,
        at_ms: int,
    ) -> VoiceChannelEvent:
        if speaker == VoiceSpeaker.USER:
            self.user_speaking = True
        elif speaker == VoiceSpeaker.AGENT:
            self.agent_speaking = True
        return self._emit(
            VoiceEventKind.SPEECH_STARTED,
            at_ms=at_ms,
            speaker=speaker,
        )

    def speech_partial(
        self,
        speaker: VoiceSpeaker,
        text: str,
        *,
        at_ms: int,
    ) -> VoiceChannelEvent:
        return self._emit(
            VoiceEventKind.SPEECH_PARTIAL,
            at_ms=at_ms,
            speaker=speaker,
            text=text,
        )

    def speech_final(
        self,
        speaker: VoiceSpeaker,
        text: str,
        *,
        at_ms: int,
    ) -> VoiceChannelEvent:
        if speaker == VoiceSpeaker.USER:
            self.user_speaking = False
            self._last_user_utterance = text
        elif speaker == VoiceSpeaker.AGENT:
            self.agent_speaking = False
            self._last_agent_utterance = text
        return self._emit(
            VoiceEventKind.SPEECH_FINAL,
            at_ms=at_ms,
            speaker=speaker,
            text=text,
        )

    def agent_speech_started(
        self,
        text: str,
        *,
        at_ms: int,
    ) -> VoiceChannelEvent:
        self.agent_speaking = True
        self._last_agent_utterance = text
        return self._emit(
            VoiceEventKind.AGENT_SPEECH_STARTED,
            at_ms=at_ms,
            speaker=VoiceSpeaker.AGENT,
            text=text,
        )

    def user_barge_in(
        self,
        *,
        at_ms: int,
    ) -> tuple[VoiceChannelEvent, VoiceChannelEvent]:
        if not self.agent_speaking:
            raise ValueError("barge-in requires active agent speech")
        interrupted = self._emit(
            VoiceEventKind.AGENT_SPEECH_INTERRUPTED,
            at_ms=at_ms,
            speaker=VoiceSpeaker.AGENT,
        )
        self.agent_speaking = False
        self.user_speaking = True
        barge_in = self._emit(
            VoiceEventKind.USER_BARGE_IN,
            at_ms=at_ms,
            speaker=VoiceSpeaker.USER,
        )
        return interrupted, barge_in

    def silence(self, duration_ms: int, *, at_ms: int) -> VoiceChannelEvent:
        if duration_ms < 0:
            raise ValueError("silence duration must be non-negative")
        return self._emit(
            VoiceEventKind.SILENCE,
            at_ms=at_ms,
            payload={"duration_ms": duration_ms},
        )

    def turn_timeout(self, *, at_ms: int) -> VoiceChannelEvent:
        return self._emit(VoiceEventKind.TURN_TIMEOUT, at_ms=at_ms)

    def asr_hypothesis(
        self,
        text: str,
        confidence: float,
        *,
        at_ms: int,
        critical_slot: bool = False,
        resolved_before_action: bool = True,
        led_to_wrong_action: bool = False,
    ) -> VoiceChannelEvent:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("ASR confidence must be between 0 and 1")
        return self._emit(
            VoiceEventKind.ASR_HYPOTHESIS,
            at_ms=at_ms,
            speaker=VoiceSpeaker.USER,
            text=text,
            payload={"confidence": confidence},
            harness_payload={
                "critical_slot": critical_slot,
                "resolved_before_action": resolved_before_action,
                "led_to_wrong_action": led_to_wrong_action,
            },
        )

    def _call_id_used(self, call_id: str) -> bool:
        return (
            call_id in self._pending_calls
            or call_id in self._completed_calls
            or call_id in self._unknown_calls
        )

    def start_tool_call(
        self,
        call_id: str,
        action_name: str,
        parameters: dict[str, Any],
        *,
        at_ms: int,
        premature: bool = False,
    ) -> VoiceChannelEvent:
        if not self.connected:
            raise ValueError("cannot start a tool call while disconnected")
        if not call_id.strip():
            raise ValueError("tool call ID must be non-empty")
        if self._call_id_used(call_id):
            raise ValueError(f"tool call ID already used: {call_id}")
        pending = PendingVoiceToolCall(
            call_id=call_id,
            action_name=action_name,
            parameters=dict(parameters),
            premature=premature,
        )
        self._pending_calls[call_id] = pending
        self._observe_parameters(parameters)
        return self._emit(
            VoiceEventKind.TOOL_CALL_STARTED,
            at_ms=at_ms,
            payload={
                "call_id": call_id,
                "action_name": action_name,
                "parameters": parameters,
            },
            harness_payload={"premature": premature},
        )

    def _duplicate_side_effect(self) -> bool:
        if not self.runtime.events:
            return False
        action_event = self.runtime.events[-1]
        duplicate = any(
            side_effect in self._seen_side_effects
            for side_effect in action_event.side_effects
        )
        self._seen_side_effects.update(action_event.side_effects)
        return duplicate

    def complete_tool_call(
        self,
        call_id: str,
        *,
        at_ms: int,
    ) -> dict[str, Any]:
        pending = self._pending_calls.get(call_id)
        if pending is None:
            raise ValueError(f"tool call is not pending: {call_id}")
        result = self.runtime.act(
            pending.action_name,
            **pending.parameters,
        )
        duplicate_side_effect = self._duplicate_side_effect()
        del self._pending_calls[call_id]
        self._completed_calls.add(call_id)
        self._emit(
            VoiceEventKind.TOOL_CALL_COMPLETED,
            at_ms=at_ms,
            payload={
                "call_id": call_id,
                "action_name": pending.action_name,
                "parameters": pending.parameters,
                "result": result,
            },
            harness_payload={
                "duplicate_side_effect": duplicate_side_effect,
            },
        )
        return result

    def mark_tool_unknown(
        self,
        call_id: str,
        *,
        at_ms: int,
        effect_applied: bool,
    ) -> VoiceChannelEvent:
        pending = self._pending_calls.get(call_id)
        if pending is None:
            raise ValueError(f"tool call is not pending: {call_id}")
        duplicate_side_effect = False
        if effect_applied:
            self.runtime.act(
                pending.action_name,
                **pending.parameters,
            )
            duplicate_side_effect = self._duplicate_side_effect()
        del self._pending_calls[call_id]
        self._unknown_calls.add(call_id)
        return self._emit(
            VoiceEventKind.TOOL_CALL_UNKNOWN_OUTCOME,
            at_ms=at_ms,
            payload={
                "call_id": call_id,
                "action_name": pending.action_name,
                "parameters": pending.parameters,
            },
            harness_payload={
                "effect_applied": effect_applied,
                "duplicate_side_effect": duplicate_side_effect,
            },
        )

    def tool_call(
        self,
        call_id: str,
        action_name: str,
        parameters: dict[str, Any],
        *,
        started_at_ms: int,
        completed_at_ms: int,
        premature: bool = False,
    ) -> dict[str, Any]:
        self.start_tool_call(
            call_id,
            action_name,
            parameters,
            at_ms=started_at_ms,
            premature=premature,
        )
        return self.complete_tool_call(call_id, at_ms=completed_at_ms)

    def tool_unknown_outcome(
        self,
        call_id: str,
        action_name: str,
        parameters: dict[str, Any],
        *,
        started_at_ms: int,
        unknown_at_ms: int,
        effect_applied: bool = False,
    ) -> None:
        self.start_tool_call(
            call_id,
            action_name,
            parameters,
            at_ms=started_at_ms,
        )
        self.mark_tool_unknown(
            call_id,
            at_ms=unknown_at_ms,
            effect_applied=effect_applied,
        )

    def disconnect(self, *, at_ms: int) -> VoiceChannelEvent:
        if not self.connected:
            raise ValueError("call is already disconnected")
        self.connected = False
        self.agent_speaking = False
        self.user_speaking = False
        return self._emit(VoiceEventKind.CALL_DISCONNECTED, at_ms=at_ms)

    def resume(self, *, at_ms: int) -> VoiceChannelEvent:
        if self.connected:
            raise ValueError("call is already connected")
        self.connected = True
        return self._emit(VoiceEventKind.CALL_RESUMED, at_ms=at_ms)

    def handoff(
        self,
        reason: str,
        *,
        at_ms: int,
        continuity_ok: bool | None = None,
    ) -> VoiceHandoffSnapshot:
        unresolved = set(self._unknown_calls) | set(self._pending_calls)
        snapshot = VoiceHandoffSnapshot(
            reason=reason,
            task_id=self.runtime.episode.task.task_id,
            last_user_utterance=self._last_user_utterance,
            last_agent_utterance=self._last_agent_utterance,
            completed_tool_calls=sorted(self._completed_calls),
            unresolved_tool_calls=sorted(unresolved),
            observed_object_ids=sorted(self._observed_object_ids),
        )
        harness_payload: dict[str, Any] = {}
        if continuity_ok is not None:
            harness_payload["state_continuity_ok"] = continuity_ok
        self._emit(
            VoiceEventKind.HUMAN_HANDOFF,
            at_ms=at_ms,
            payload=snapshot.model_dump(mode="json"),
            harness_payload=harness_payload,
        )
        return snapshot

    def verify_resolution(
        self,
        submission: EpisodeSubmission,
        *,
        at_ms: int,
        text: str = "Interaction resolved.",
    ) -> tuple[VoiceChannelEvent, VerificationBreakdown]:
        verification = self.runtime.submit(submission)
        verified = _is_verified_resolution(verification)
        event = self._emit(
            VoiceEventKind.SPEECH_FINAL,
            at_ms=at_ms,
            speaker=VoiceSpeaker.AGENT,
            text=text,
            harness_payload={
                "resolution_verified": verified,
                "verification_overall_reward": verification.overall_reward,
            },
        )
        return event, verification

    def mark_verified_resolution(
        self,
        submission: EpisodeSubmission,
        *,
        at_ms: int,
    ) -> tuple[VoiceChannelEvent, VerificationBreakdown]:
        """Compatibility name that now requires real verifier evidence."""
        return self.verify_resolution(submission, at_ms=at_ms)

    def public_events(self) -> list[dict[str, Any]]:
        return [event.public_payload() for event in self.events]

    def _observe_parameters(self, parameters: dict[str, Any]) -> None:
        for name, value in parameters.items():
            if name.endswith("_id") and isinstance(value, str):
                self._observed_object_ids.add(value)


def _is_verified_resolution(verification: VerificationBreakdown) -> bool:
    return all(
        score == 1.0
        for score in (
            verification.outcome,
            verification.state,
            verification.constraints,
            verification.side_effects,
            verification.process,
            verification.evidence,
        )
    )


def _tool_event_identity(
    event: VoiceChannelEvent,
) -> tuple[str, str, dict[str, Any]]:
    call_id = event.payload.get("call_id")
    action_name = event.payload.get("action_name")
    parameters = event.payload.get("parameters")
    if not isinstance(call_id, str) or not call_id:
        raise ValueError("voice tool event requires a non-empty call ID")
    if not isinstance(action_name, str) or not action_name:
        raise ValueError("voice tool event requires an action name")
    if not isinstance(parameters, dict):
        raise ValueError("voice tool event parameters must be an object")
    return call_id, action_name, parameters


def replay_voice_events(
    episode: OperationalEpisode,
    events: list[VoiceChannelEvent],
) -> OperationalRuntime:
    """Replay trusted voice events while enforcing tool lifecycle provenance.

    Unknown outcomes are replayed only when the trusted harness event records
    whether the hidden effect actually happened. Public traces intentionally omit
    that bit and therefore cannot silently convert uncertainty into success.
    """
    runtime = OperationalRuntime(episode)
    expected_sequence = 1
    last_at_ms = -1
    pending: dict[str, tuple[str, dict[str, Any]]] = {}
    terminal_call_ids: set[str] = set()

    for event in events:
        if event.sequence != expected_sequence:
            raise ValueError("voice event sequence is not contiguous")
        if event.at_ms < last_at_ms:
            raise ValueError("voice event timestamps are not monotonic")
        expected_sequence += 1
        last_at_ms = event.at_ms

        if event.kind == VoiceEventKind.TOOL_CALL_STARTED:
            call_id, action_name, parameters = _tool_event_identity(event)
            if call_id in pending or call_id in terminal_call_ids:
                raise ValueError("voice tool call IDs must be unique")
            pending[call_id] = (action_name, parameters)
            continue

        if event.kind not in {
            VoiceEventKind.TOOL_CALL_COMPLETED,
            VoiceEventKind.TOOL_CALL_UNKNOWN_OUTCOME,
        }:
            continue

        call_id, action_name, parameters = _tool_event_identity(event)
        started = pending.get(call_id)
        if started is None:
            raise ValueError("terminal voice tool event has no matching start")
        if started != (action_name, parameters):
            raise ValueError("terminal voice tool event does not match its start")

        if event.kind == VoiceEventKind.TOOL_CALL_COMPLETED:
            recorded_result = event.payload.get("result")
            if not isinstance(recorded_result, dict):
                raise ValueError("completed voice tool event requires a result object")
            replayed_result = runtime.act(action_name, **parameters)
            if replayed_result != recorded_result:
                raise ValueError("completed voice tool result does not replay exactly")
        else:
            if "effect_applied" not in event.harness_payload:
                raise ValueError(
                    "unknown outcome replay requires trusted outcome provenance"
                )
            effect_applied = event.harness_payload["effect_applied"]
            if not isinstance(effect_applied, bool):
                raise ValueError("unknown outcome provenance must be boolean")
            if effect_applied:
                runtime.act(action_name, **parameters)

        del pending[call_id]
        terminal_call_ids.add(call_id)

    return runtime


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return float(ordered[index])


def measure_voice_channel(events: list[VoiceChannelEvent]) -> VoiceChannelMetrics:
    interruptions = [
        event
        for event in events
        if event.kind == VoiceEventKind.USER_BARGE_IN
    ]
    recovered_interruptions = 0
    for interruption in interruptions:
        if any(
            later.kind == VoiceEventKind.AGENT_SPEECH_STARTED
            for later in events
            if later.sequence > interruption.sequence
        ):
            recovered_interruptions += 1

    critical_asr = [
        event
        for event in events
        if event.kind == VoiceEventKind.ASR_HYPOTHESIS
        and bool(event.harness_payload.get("critical_slot"))
    ]
    asr_action_errors = sum(
        bool(event.harness_payload.get("led_to_wrong_action"))
        for event in critical_asr
    )
    resolved_asr = sum(
        bool(event.harness_payload.get("resolved_before_action"))
        for event in critical_asr
    )

    tool_starts = [
        event
        for event in events
        if event.kind == VoiceEventKind.TOOL_CALL_STARTED
    ]
    premature_actions = sum(
        bool(event.harness_payload.get("premature"))
        for event in tool_starts
    )
    tool_terminals = [
        event
        for event in events
        if event.kind
        in {
            VoiceEventKind.TOOL_CALL_COMPLETED,
            VoiceEventKind.TOOL_CALL_UNKNOWN_OUTCOME,
        }
    ]
    duplicate_side_effects = sum(
        bool(event.harness_payload.get("duplicate_side_effect"))
        for event in tool_terminals
    )

    handoffs = [
        event
        for event in events
        if event.kind == VoiceEventKind.HUMAN_HANDOFF
    ]
    scored_handoffs = [
        event
        for event in handoffs
        if "state_continuity_ok" in event.harness_payload
    ]
    continuous_handoffs = sum(
        bool(event.harness_payload.get("state_continuity_ok"))
        for event in scored_handoffs
    )

    disconnects = [
        event
        for event in events
        if event.kind == VoiceEventKind.CALL_DISCONNECTED
    ]
    recovered_disconnects = 0
    for disconnect in disconnects:
        resumed = any(
            later.kind == VoiceEventKind.CALL_RESUMED
            for later in events
            if later.sequence > disconnect.sequence
        )
        if resumed:
            recovered_disconnects += 1

    response_latencies: list[int] = []
    user_final_events = [
        event
        for event in events
        if event.kind == VoiceEventKind.SPEECH_FINAL
        and event.speaker == VoiceSpeaker.USER
    ]
    for user_event in user_final_events:
        next_agent = next(
            (
                event
                for event in events
                if event.sequence > user_event.sequence
                and event.kind == VoiceEventKind.AGENT_SPEECH_STARTED
            ),
            None,
        )
        if next_agent is not None:
            response_latencies.append(next_agent.at_ms - user_event.at_ms)

    verified_events = [
        event
        for event in events
        if bool(event.harness_payload.get("resolution_verified"))
    ]
    time_to_verified: int | None = None
    if events and verified_events:
        time_to_verified = verified_events[-1].at_ms - events[0].at_ms

    return VoiceChannelMetrics(
        events=len(events),
        interruptions=len(interruptions),
        interruption_recovery_rate=(
            recovered_interruptions / len(interruptions)
            if interruptions
            else 1.0
        ),
        critical_asr_hypotheses=len(critical_asr),
        asr_induced_action_error_rate=(
            asr_action_errors / len(critical_asr)
            if critical_asr
            else 0.0
        ),
        clarification_correctness=(
            resolved_asr / len(critical_asr)
            if critical_asr
            else 1.0
        ),
        premature_action_rate=(
            premature_actions / len(tool_starts)
            if tool_starts
            else 0.0
        ),
        duplicate_side_effect_rate=(
            duplicate_side_effects / len(tool_terminals)
            if tool_terminals
            else 0.0
        ),
        handoff_state_continuity_rate=(
            continuous_handoffs / len(scored_handoffs)
            if scored_handoffs
            else 1.0
        ),
        disconnect_recovery_rate=(
            recovered_disconnects / len(disconnects)
            if disconnects
            else 1.0
        ),
        response_latency_p50_ms=(
            float(median(response_latencies))
            if response_latencies
            else None
        ),
        response_latency_p95_ms=_percentile(response_latencies, 0.95),
        time_to_verified_resolution_ms=time_to_verified,
    )
