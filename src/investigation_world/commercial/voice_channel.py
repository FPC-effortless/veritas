from __future__ import annotations

from enum import StrEnum
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.operational.models import OperationalEpisode
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
        payload = self.model_dump(mode="json", exclude={"harness_payload"})
        return payload


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
    handoff_state_continuity_rate: float
    disconnect_recovery_rate: float
    response_latency_p50_ms: float | None
    response_latency_p95_ms: float | None
    time_to_verified_resolution_ms: int | None


class VoiceChannelRuntime:
    """Provider-neutral voice/session layer above `OperationalRuntime`.

    Only observable tool results enter the voice event stream. Hidden operational
    state, action consequences, and verifier truth remain inside the wrapped runtime.
    """

    def __init__(self, episode: OperationalEpisode):
        self.runtime = OperationalRuntime(episode)
        self.events: list[VoiceChannelEvent] = []
        self.connected = True
        self.agent_speaking = False
        self.user_speaking = False
        self._last_at_ms = -1
        self._completed_calls: set[str] = set()
        self._unknown_calls: set[str] = set()
        self._observed_object_ids: set[str] = set()
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

    def speech_started(self, speaker: VoiceSpeaker, *, at_ms: int) -> VoiceChannelEvent:
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

    def agent_speech_started(self, text: str, *, at_ms: int) -> VoiceChannelEvent:
        self.agent_speaking = True
        self._last_agent_utterance = text
        return self._emit(
            VoiceEventKind.AGENT_SPEECH_STARTED,
            at_ms=at_ms,
            speaker=VoiceSpeaker.AGENT,
            text=text,
        )

    def user_barge_in(self, *, at_ms: int) -> tuple[VoiceChannelEvent, VoiceChannelEvent]:
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
        if not self.connected:
            raise ValueError("cannot execute a tool call while disconnected")
        if call_id in self._completed_calls or call_id in self._unknown_calls:
            raise ValueError(f"tool call ID already used: {call_id}")
        self._emit(
            VoiceEventKind.TOOL_CALL_STARTED,
            at_ms=started_at_ms,
            payload={
                "call_id": call_id,
                "action_name": action_name,
                "parameters": parameters,
            },
            harness_payload={"premature": premature},
        )
        result = self.runtime.act(action_name, **parameters)
        self._completed_calls.add(call_id)
        self._observe_parameters(parameters)
        self._emit(
            VoiceEventKind.TOOL_CALL_COMPLETED,
            at_ms=completed_at_ms,
            payload={
                "call_id": call_id,
                "action_name": action_name,
                "parameters": parameters,
                "result": result,
            },
        )
        return result

    def tool_unknown_outcome(
        self,
        call_id: str,
        action_name: str,
        parameters: dict[str, Any],
        *,
        started_at_ms: int,
        unknown_at_ms: int,
    ) -> None:
        if call_id in self._completed_calls or call_id in self._unknown_calls:
            raise ValueError(f"tool call ID already used: {call_id}")
        self._emit(
            VoiceEventKind.TOOL_CALL_STARTED,
            at_ms=started_at_ms,
            payload={
                "call_id": call_id,
                "action_name": action_name,
                "parameters": parameters,
            },
        )
        self._unknown_calls.add(call_id)
        self._observe_parameters(parameters)
        self._emit(
            VoiceEventKind.TOOL_CALL_UNKNOWN_OUTCOME,
            at_ms=unknown_at_ms,
            payload={
                "call_id": call_id,
                "action_name": action_name,
                "parameters": parameters,
            },
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
        snapshot = VoiceHandoffSnapshot(
            reason=reason,
            task_id=self.runtime.episode.task.task_id,
            last_user_utterance=self._last_user_utterance,
            last_agent_utterance=self._last_agent_utterance,
            completed_tool_calls=sorted(self._completed_calls),
            unresolved_tool_calls=sorted(self._unknown_calls),
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

    def mark_verified_resolution(self, *, at_ms: int) -> VoiceChannelEvent:
        return self._emit(
            VoiceEventKind.SPEECH_FINAL,
            at_ms=at_ms,
            speaker=VoiceSpeaker.AGENT,
            text="Interaction resolved.",
            harness_payload={"resolution_verified": True},
        )

    def public_events(self) -> list[dict[str, Any]]:
        return [event.public_payload() for event in self.events]

    def _observe_parameters(self, parameters: dict[str, Any]) -> None:
        for name, value in parameters.items():
            if name.endswith("_id") and isinstance(value, str):
                self._observed_object_ids.add(value)


def replay_voice_events(
    episode: OperationalEpisode,
    events: list[VoiceChannelEvent],
) -> OperationalRuntime:
    """Replay completed tool effects from a voice trace into a fresh runtime."""
    runtime = OperationalRuntime(episode)
    expected_sequence = 1
    last_at_ms = -1
    completed_call_ids: set[str] = set()
    for event in events:
        if event.sequence != expected_sequence:
            raise ValueError("voice event sequence is not contiguous")
        if event.at_ms < last_at_ms:
            raise ValueError("voice event timestamps are not monotonic")
        expected_sequence += 1
        last_at_ms = event.at_ms
        if event.kind != VoiceEventKind.TOOL_CALL_COMPLETED:
            continue
        call_id = str(event.payload.get("call_id", ""))
        if not call_id or call_id in completed_call_ids:
            raise ValueError("completed voice tool calls require unique call IDs")
        action_name = str(event.payload.get("action_name", ""))
        parameters = event.payload.get("parameters")
        if not isinstance(parameters, dict):
            raise ValueError("completed voice tool call parameters must be an object")
        runtime.act(action_name, **parameters)
        completed_call_ids.add(call_id)
    return runtime


def _percentile(values: list[int], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * percentile))
    return float(ordered[index])


def measure_voice_channel(events: list[VoiceChannelEvent]) -> VoiceChannelMetrics:
    interruptions = [event for event in events if event.kind == VoiceEventKind.USER_BARGE_IN]
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

    tool_starts = [event for event in events if event.kind == VoiceEventKind.TOOL_CALL_STARTED]
    premature_actions = sum(
        bool(event.harness_payload.get("premature"))
        for event in tool_starts
    )

    handoffs = [event for event in events if event.kind == VoiceEventKind.HUMAN_HANDOFF]
    scored_handoffs = [
        event
        for event in handoffs
        if "state_continuity_ok" in event.harness_payload
    ]
    continuous_handoffs = sum(
        bool(event.harness_payload.get("state_continuity_ok"))
        for event in scored_handoffs
    )

    disconnects = [event for event in events if event.kind == VoiceEventKind.CALL_DISCONNECTED]
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
        if event.kind == VoiceEventKind.SPEECH_FINAL and event.speaker == VoiceSpeaker.USER
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
