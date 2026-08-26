from __future__ import annotations

import json
from collections import Counter, defaultdict
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


def stratified_split_episode_ids(episodes: list[CompanyWorldEpisode]) -> dict[str, list[str]]:
    """Deterministically split each task family 60/20/20 to prevent family drift."""
    by_family: dict[str, list[CompanyWorldEpisode]] = defaultdict(list)
    for episode in episodes:
        by_family[episode.task.task_type].append(episode)
    result = {"train": [], "public_eval": [], "private_eval": []}
    for family in sorted(by_family):
        family_episodes = sorted(by_family[family], key=lambda item: item.episode_id)
        n = len(family_episodes)
        train_end = int(n * 0.6)
        public_end = int(n * 0.8)
        if n and train_end == 0:
            train_end = 1
        if public_end < train_end:
            public_end = train_end
        result["train"].extend(item.episode_id for item in family_episodes[:train_end])
        result["public_eval"].extend(item.episode_id for item in family_episodes[train_end:public_end])
        result["private_eval"].extend(item.episode_id for item in family_episodes[public_end:])
    return result


def compile_companyworld_distribution(
    root: str | Path,
    *,
    per_family: int = 200,
    include_legacy: bool = True,
    legacy_limit: int | None = None,
    families: tuple[str, ...] | None = None,
) -> tuple[CompanyWorldAdapter, list[CompanyWorldEpisode]]:
    from investigation_world.companyworld.distribution import (
        CompanyWorldTaskDistributionConfig,
        compile_task_distribution,
    )

    config = CompanyWorldTaskDistributionConfig(
        per_family=per_family,
        include_legacy=include_legacy,
        legacy_limit=legacy_limit,
        families=families or CompanyWorldTaskDistributionConfig().families,
    )
    return compile_task_distribution(root, config=config)


def public_distribution_payload(episodes: list[CompanyWorldEpisode]) -> dict[str, Any]:
    return {
        "format": "veritas-companyworld-distribution-v2",
        "episodes": [episode.public_payload() for episode in episodes],
        "splits": stratified_split_episode_ids(episodes),
    }


def write_companyworld_distribution_bundle(
    root: str | Path,
    public_output: str | Path,
    *,
    oracle_output: str | Path | None = None,
    per_family: int = 200,
    include_legacy: bool = True,
    legacy_limit: int | None = None,
    families: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    adapter, episodes = compile_companyworld_distribution(
        root,
        per_family=per_family,
        include_legacy=include_legacy,
        legacy_limit=legacy_limit,
        families=families,
    )
    public_path = Path(public_output)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(public_distribution_payload(episodes), indent=2, default=str))
    if oracle_output is not None:
        oracle_path = Path(oracle_output)
        oracle_path.parent.mkdir(parents=True, exist_ok=True)
        oracle_path.write_text(json.dumps(oracle_bundle_payload(episodes), indent=2, default=str))

    leaks = sum(len(adapter.public_projection_leaks(episode)) for episode in episodes)
    report = adapter.validate()
    report.public_projection_leakage_count = leaks
    if leaks:
        report.errors.append(f"compiled public payload contains {leaks} private-field leaks")
    splits = stratified_split_episode_ids(episodes)
    return {
        "world_id": adapter.world_id,
        "episodes": len(episodes),
        "task_families": dict(sorted(Counter(item.task.task_type for item in episodes).items())),
        "splits": {key: len(value) for key, value in splits.items()},
        "validation": report.model_dump(mode="json"),
    }
