from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.commercial.voice_qualification import (
    VoicePressure,
    VoiceQualificationRun,
    VoiceQualificationSummary,
    VoiceScenarioFamily,
    classify_voice_failure,
    summarize_voice_qualification,
    validate_voice_episode,
)
from investigation_world.commercial.voice_qualification_core import _LoadedVoiceSuite
from investigation_world.operational.models import EpisodeSubmission, OperationalEpisode
from investigation_world.operational.runtime import OperationalRuntime


class VoiceAgentResult(BaseModel):
    """One agent-driver submission plus optional provider/model cost."""

    model_config = ConfigDict(extra="forbid")
    submission: EpisodeSubmission
    cost_usd: float | None = Field(default=None, ge=0.0)


class VoiceAgentSession:
    """Narrow agent-facing facade over OperationalRuntime.

    The driver receives only the public task payload, record search/open operations,
    public action results, and budget state. Hidden state snapshots, traces, and the
    episode oracle are intentionally not exposed by this facade.
    """

    __slots__ = ("__runtime",)

    def __init__(self, runtime: OperationalRuntime):
        self.__runtime = runtime

    def public_payload(self) -> dict[str, Any]:
        return self.__runtime.public_payload()

    def search(
        self,
        system: str,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self.__runtime.search(system, query, limit)

    def search_all(
        self,
        query: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        return self.__runtime.search_all(query, limit)

    def open_record(self, record_id: str) -> dict[str, Any]:
        return self.__runtime.open_record(record_id)

    def act(self, action_name: str, **parameters: Any) -> dict[str, Any]:
        return self.__runtime.act(action_name, **parameters)

    def budget_snapshot(self) -> dict[str, Any]:
        return self.__runtime.budget_snapshot()


class VoiceAgentDriver(Protocol):
    def __call__(self, session: VoiceAgentSession) -> VoiceAgentResult: ...


def evaluate_voice_configuration(
    episodes: Iterable[OperationalEpisode],
    driver: VoiceAgentDriver,
    *,
    configuration_id: str,
    attempts: int = 1,
) -> list[VoiceQualificationRun]:
    """Evaluate one configuration and retain evaluator-side trace evidence."""
    if attempts < 1:
        raise ValueError("attempts must be >= 1")

    sealed_digest = episodes.verified_digest() if isinstance(episodes, _LoadedVoiceSuite) else None
    suite = list(episodes)
    if not suite:
        raise ValueError("at least one voice qualification episode is required")
    for episode in suite:
        validate_voice_episode(episode)

    sealed_cases = {
        episode.episode_id: (
            VoiceScenarioFamily(str(episode.metadata["scenario_family"])),
            VoicePressure(str(episode.metadata["pressure"])),
            bool(episode.oracle.metadata.get("recovery_required", False)),
        )
        for episode in suite
    } if sealed_digest else {}
    runs: list[VoiceQualificationRun] = []
    for episode in suite:
        family = VoiceScenarioFamily(str(episode.metadata["scenario_family"]))
        pressure = VoicePressure(str(episode.metadata["pressure"]))
        recovery_required = bool(
            episode.oracle.metadata.get("recovery_required", False)
        )
        for attempt in range(1, attempts + 1):
            runtime = OperationalRuntime(episode)
            result = driver(VoiceAgentSession(runtime))
            verification = runtime.submit(result.submission)
            trace = runtime.trace()
            failure_classes, failure_evidence = classify_voice_failure(
                verification,
                trace,
            )
            runs.append(
                VoiceQualificationRun(
                    configuration_id=configuration_id,
                    evidence_scope=(
                        "sealed" if sealed_digest else "development"
                        if episode.metadata.get("qualification_split") == "development"
                        else "unverified"
                    ),
                    sealed_suite_sha256=sealed_digest,
                    sealed_suite_scenarios=len(suite) if sealed_digest else 0,
                    sealed_suite_cases=sealed_cases,
                    scenario_id=episode.episode_id,
                    family=family,
                    pressure=pressure,
                    recovery_required=recovery_required,
                    attempt=attempt,
                    verification=verification,
                    cost_usd=result.cost_usd,
                    trace=trace,
                    failure_classes=failure_classes,
                    failure_evidence=failure_evidence,
                )
            )
    return runs


def compare_voice_configurations(
    episodes: Iterable[OperationalEpisode],
    drivers: Mapping[str, VoiceAgentDriver],
    *,
    attempts: int = 1,
) -> tuple[list[VoiceQualificationRun], list[VoiceQualificationSummary]]:
    """Compare multiple configurations while holding the operational suite fixed."""
    if len(drivers) < 2:
        raise ValueError("comparison requires at least two configurations")

    suite = episodes if isinstance(episodes, _LoadedVoiceSuite) else list(episodes)
    if not suite:
        raise ValueError("at least one voice qualification episode is required")
    for episode in suite:
        validate_voice_episode(episode)

    runs: list[VoiceQualificationRun] = []
    for configuration_id, driver in sorted(drivers.items()):
        runs.extend(
            evaluate_voice_configuration(
                suite,
                driver,
                configuration_id=configuration_id,
                attempts=attempts,
            )
        )
    return runs, summarize_voice_qualification(runs)
