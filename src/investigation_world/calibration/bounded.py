from __future__ import annotations

from typing import Any

from investigation_world.calibration.fixtures import diagnostic_fixture, interactive_fixture
from investigation_world.calibration.full_context import (
    GenerateFn,
    _action,
    _claims,
    _json_object,
    _prompt,
    _stats,
    empty_anchors,
    reference_anchors,
)
from investigation_world.companyworld.interactive_runtime import InteractiveCompanyWorldRuntime
from investigation_world.companyworld.verifier import verify_companyworld


SUPPORTED_LEVELS = ("diagnostic", "interactive")


def _score_diagnostic_bounded(generate: GenerateFn, *, episode_limit: int) -> tuple[list[float], int]:
    scores: list[float] = []
    failures = 0
    for episode in diagnostic_fixture()[:episode_limit]:
        output = _json_object(generate(_prompt("diagnostic", episode.public_payload())))
        if not output:
            failures += 1
        result = _claims(output, episode.task.model_dump(mode="json"))
        scores.append(verify_companyworld(result, episode).overall_reward)
    return scores, failures


def _score_interactive_bounded(generate: GenerateFn, *, episode_limit: int) -> tuple[list[float], int]:
    scores: list[float] = []
    failures = 0
    for episode in interactive_fixture()[:episode_limit]:
        public = episode.public_payload()
        output = _json_object(generate(_prompt("interactive", public)))
        if not output:
            failures += 1
        result = _claims(output, episode.task.model_dump(mode="json"))
        runtime = InteractiveCompanyWorldRuntime(episode)
        action = _action(output, episode.task.model_dump(mode="json"))
        if action is not None:
            try:
                runtime.act(action)
            except (ValueError, KeyError):
                pass
        scores.append(runtime.submit(result).overall_reward)
    return scores, failures


def run_bounded_calibration(
    generate: GenerateFn,
    *,
    model_name: str,
    levels: tuple[str, ...] = SUPPORTED_LEVELS,
    episodes_per_level: int = 2,
) -> dict[str, Any]:
    if episodes_per_level < 1 or episodes_per_level > 3:
        raise ValueError("episodes_per_level must be between 1 and 3")
    unknown = set(levels) - set(SUPPORTED_LEVELS)
    if unknown:
        raise ValueError(f"unsupported bounded calibration levels: {sorted(unknown)}")

    scorers = {
        "diagnostic": _score_diagnostic_bounded,
        "interactive": _score_interactive_bounded,
    }
    model_scores: dict[str, dict[str, float]] = {}
    parse_failures: dict[str, int] = {}
    for level in levels:
        scores, failures = scorers[level](generate, episode_limit=episodes_per_level)
        model_scores[level] = _stats(scores)
        parse_failures[level] = failures

    refs = reference_anchors()
    empties = empty_anchors()
    return {
        "schema_version": "0.2.0",
        "mode": "bounded_full_context_plan",
        "model": model_name,
        "levels": list(levels),
        "episodes": {level: episodes_per_level for level in levels},
        "model_scores": model_scores,
        "reference_anchors": {level: refs[level] for level in levels},
        "empty_anchors": {level: empties[level] for level in levels},
        "parse_failures": parse_failures,
        "purpose": "strong-model capability emergence screen; not a procurement-grade comparative benchmark",
    }
