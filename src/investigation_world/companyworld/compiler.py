from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from investigation_world.companyworld.adapter import CompanyWorldAdapter
from investigation_world.companyworld.models import CompanyWorldEpisode


def split_episode_ids(episodes: list[CompanyWorldEpisode]) -> dict[str, list[str]]:
    ids = [episode.episode_id for episode in episodes]
    if not ids:
        return {"train": [], "public_eval": [], "private_eval": []}
    train_end = max(1, int(len(ids) * 0.6))
    public_end = max(train_end, int(len(ids) * 0.8))
    return {
        "train": ids[:train_end],
        "public_eval": ids[train_end:public_end],
        "private_eval": ids[public_end:],
    }


def compile_companyworld(
    root: str | Path,
    *,
    limit: int | None = None,
) -> tuple[CompanyWorldAdapter, list[CompanyWorldEpisode]]:
    adapter = CompanyWorldAdapter(root)
    episodes = adapter.compile_episodes(limit=limit)
    return adapter, episodes


def public_bundle_payload(episodes: list[CompanyWorldEpisode]) -> dict[str, Any]:
    return {
        "format": "veritas-companyworld-public-v1",
        "episodes": [episode.public_payload() for episode in episodes],
        "splits": split_episode_ids(episodes),
    }


def oracle_bundle_payload(episodes: list[CompanyWorldEpisode]) -> dict[str, Any]:
    return {
        "format": "veritas-companyworld-oracles-v1",
        "oracles": [
            {
                "episode_id": episode.episode_id,
                "world_id": episode.world_id,
                "oracle": episode.oracle.model_dump(mode="json"),
            }
            for episode in episodes
        ],
    }


def write_companyworld_bundle(
    root: str | Path,
    public_output: str | Path,
    *,
    oracle_output: str | Path | None = None,
    limit: int | None = None,
) -> dict[str, Any]:
    adapter, episodes = compile_companyworld(root, limit=limit)
    public_path = Path(public_output)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(public_bundle_payload(episodes), indent=2, default=str))

    if oracle_output is not None:
        oracle_path = Path(oracle_output)
        oracle_path.parent.mkdir(parents=True, exist_ok=True)
        oracle_path.write_text(json.dumps(oracle_bundle_payload(episodes), indent=2, default=str))

    leaks = sum(len(adapter.public_projection_leaks(episode)) for episode in episodes)
    report = adapter.validate()
    report.public_projection_leakage_count = leaks
    if leaks:
        report.errors.append(f"compiled public payload contains {leaks} private-field leaks")

    return {
        "world_id": adapter.world_id,
        "episodes": len(episodes),
        "splits": {key: len(value) for key, value in split_episode_ids(episodes).items()},
        "validation": report.model_dump(mode="json"),
    }
