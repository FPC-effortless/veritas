from __future__ import annotations

import json
from statistics import mean
from typing import Any, Callable

from investigation_world.benchmark.policies import PublicEvidenceReferencePolicy
from investigation_world.calibration.fixtures import build_o2c_episode
from investigation_world.calibration.full_context import _claims, _json_object, _prompt
from investigation_world.companyworld.models import CompanyWorldEpisode
from investigation_world.companyworld.verifier import verify_companyworld

GenerateFn = Callable[[str], str]


def _with_world(episode: CompanyWorldEpisode, world_id: str) -> CompanyWorldEpisode:
    task = episode.task.model_copy(update={"world_id": world_id})
    return episode.model_copy(update={"world_id": world_id, "task": task})


def _target_payload(episode: CompanyWorldEpisode) -> dict[str, Any]:
    result = PublicEvidenceReferencePolicy()(episode.public_payload())
    return {
        "claims": [
            {
                "field_name": claim.get("field_name"),
                "value": claim.get("value"),
            }
            for claim in result.claims
        ],
        "evidence_record_ids": [item.get("record_id") for item in result.evidence],
        "confidence": 1.0,
    }


def build_diagnostic_examples(
    *,
    count: int = 24,
    start_index: int = 100,
    world_id: str = "CW-TRAINING",
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    for offset in range(count):
        index = start_index + offset
        delay = (index * 5 + 3) % 8
        episode = _with_world(build_o2c_episode(index, delay_days=delay), world_id)
        examples.append(
            {
                "episode": episode,
                "prompt": _prompt("diagnostic", episode.public_payload()),
                "target": json.dumps(_target_payload(episode), sort_keys=True),
            }
        )
    return examples


def build_heldout_diagnostic_episodes(
    *,
    count: int = 12,
    start_index: int = 1000,
    world_id: str = "CW-HELDOUT",
) -> list[CompanyWorldEpisode]:
    episodes: list[CompanyWorldEpisode] = []
    for offset in range(count):
        index = start_index + offset
        delay = (index * 7 + 1) % 8
        episodes.append(_with_world(build_o2c_episode(index, delay_days=delay), world_id))
    return episodes


def score_diagnostic_generator(
    generate: GenerateFn,
    episodes: list[CompanyWorldEpisode],
) -> dict[str, Any]:
    scores: list[float] = []
    parse_failures = 0
    per_episode: list[dict[str, Any]] = []
    for episode in episodes:
        raw = generate(_prompt("diagnostic", episode.public_payload()))
        payload = _json_object(raw)
        if not payload:
            parse_failures += 1
        result = _claims(payload, episode.task.model_dump(mode="json"))
        score = verify_companyworld(result, episode).overall_reward
        scores.append(score)
        per_episode.append(
            {
                "episode_id": episode.episode_id,
                "score": round(score, 6),
                "parsed": bool(payload),
            }
        )
    return {
        "mean": round(mean(scores), 6) if scores else 0.0,
        "min": round(min(scores), 6) if scores else 0.0,
        "max": round(max(scores), 6) if scores else 0.0,
        "parse_failures": parse_failures,
        "episodes": per_episode,
    }
