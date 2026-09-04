from __future__ import annotations

from investigation_world.commercial.voice_qualification import build_voice_qualification_suite
from investigation_world.commercial.voice_runner import (
    VoiceAgentResult,
    VoiceAgentSession,
    compare_voice_configurations,
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


def test_three_configurations_compare_on_same_frozen_suite() -> None:
    suite = build_voice_qualification_suite(seed=42)
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
