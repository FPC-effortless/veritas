from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from investigation_world.operational import (
    EpisodeSubmission,
    OperationalEpisode,
    OperationalRuntime,
    VerificationBreakdown,
)


def execute_episode(
    episode: OperationalEpisode,
    *,
    actions: Iterable[tuple[str, Mapping[str, Any]]],
    evidence_ids: Iterable[str],
    claimed_state: Mapping[str, Any],
    conclusion: str,
) -> VerificationBreakdown:
    """Execute only through the public runtime and canonical verifier."""
    runtime = OperationalRuntime(episode)
    for action_name, parameters in actions:
        runtime.act(action_name, **dict(parameters))
    return runtime.submit(
        EpisodeSubmission(
            conclusion=conclusion,
            claimed_state=dict(claimed_state),
            evidence_ids=list(evidence_ids),
            confidence=1.0,
        )
    )


def require_perfect(result: VerificationBreakdown) -> VerificationBreakdown:
    """Fail loudly when a supposedly successful example stops satisfying its verifier."""
    if result.overall_reward != 1.0:
        raise RuntimeError(f"example verifier did not pass perfectly: {result.model_dump()}")
    return result
