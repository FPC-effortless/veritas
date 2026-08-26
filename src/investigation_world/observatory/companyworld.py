from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investigation_world.companyworld.models import CompanyWorldEpisode
from investigation_world.companyworld.runtime import CompanyWorldRuntime
from investigation_world.foundry.models import DistributionSplit, stable_hash
from investigation_world.observatory.models import LongitudinalCell, ScenarioPool, ScenarioRef
from investigation_world.observatory.runtime_interventions import (
    InterventionAwareCompanyWorldRuntime,
)


class CompanyWorldBundleRepository:
    """Privileged evaluator repository joining public episodes with private oracles."""

    def __init__(
        self,
        episodes: list[CompanyWorldEpisode],
        *,
        taskset_version: str,
        splits: dict[str, list[str]] | None = None,
        bundle_version: str | None = None,
    ):
        if not episodes:
            raise ValueError("CompanyWorld repository requires at least one episode")
        self.taskset_version = taskset_version
        self.splits = splits or {}
        self._episodes = {episode.episode_id: episode for episode in episodes}
        if len(self._episodes) != len(episodes):
            raise ValueError("duplicate CompanyWorld episode ids")
        world_ids = {episode.world_id for episode in episodes}
        if len(world_ids) != 1:
            raise ValueError("one CompanyWorld repository must contain exactly one world_id")
        self.world_id = next(iter(world_ids))
        canonical = [
            episode.model_dump(mode="json")
            for episode in sorted(episodes, key=lambda item: item.episode_id)
        ]
        self.bundle_version = bundle_version or (
            f"CW-{stable_hash([taskset_version, canonical])[:16].upper()}"
        )
        self._by_task: dict[str, list[CompanyWorldEpisode]] = {}
        for episode in episodes:
            self._by_task.setdefault(episode.task.task_id, []).append(episode)

    @classmethod
    def from_files(
        cls,
        public_path: str | Path,
        oracle_path: str | Path,
    ) -> "CompanyWorldBundleRepository":
        public = json.loads(Path(public_path).read_text(encoding="utf-8"))
        private = json.loads(Path(oracle_path).read_text(encoding="utf-8"))
        public_episodes = public.get("episodes", [])
        oracle_entries = private.get("oracles", [])
        oracle_by_episode: dict[str, dict[str, Any]] = {}
        for entry in oracle_entries:
            if not isinstance(entry, dict):
                continue
            episode_id = entry.get("episode_id")
            oracle = entry.get("oracle")
            if isinstance(episode_id, str) and isinstance(oracle, dict):
                oracle_by_episode[episode_id] = oracle
        episodes: list[CompanyWorldEpisode] = []
        missing: list[str] = []
        for public_episode in public_episodes:
            if not isinstance(public_episode, dict):
                continue
            episode_id = public_episode.get("episode_id")
            oracle = oracle_by_episode.get(str(episode_id))
            if oracle is None:
                missing.append(str(episode_id))
                continue
            episodes.append(
                CompanyWorldEpisode.model_validate({**public_episode, "oracle": oracle})
            )
        if missing:
            raise ValueError("missing private oracles for episodes: " + ", ".join(sorted(missing)))
        return cls(
            episodes,
            taskset_version=str(public.get("format", "companyworld-bundle-unspecified")),
            splits={
                str(key): [str(item) for item in value]
                for key, value in (public.get("splits") or {}).items()
                if isinstance(value, list)
            },
            bundle_version=f"CW-{stable_hash([public, private])[:16].upper()}",
        )

    def episode(self, scenario: ScenarioRef) -> CompanyWorldEpisode:
        direct = self._episodes.get(scenario.scenario_id)
        if direct is not None:
            if scenario.task_id is not None and direct.task.task_id != scenario.task_id:
                raise ValueError("scenario task_id does not match selected CompanyWorld episode")
            return direct
        task_id = scenario.task_id or scenario.scenario_id
        candidates = self._by_task.get(task_id, [])
        if len(candidates) == 1:
            return candidates[0]
        if not candidates:
            raise KeyError(f"no CompanyWorld episode for scenario {scenario.scenario_id!r}")
        raise ValueError(f"task id {task_id!r} maps to multiple CompanyWorld episodes")

    def scenario_refs(
        self,
        *,
        pool: ScenarioPool = ScenarioPool.ANCHOR,
        split_name: str | None = None,
        limit: int | None = None,
    ) -> list[ScenarioRef]:
        selected = list(self._episodes.values())
        split: DistributionSplit | None = None
        if split_name is not None:
            allowed = set(self.splits.get(split_name, []))
            if not allowed:
                raise KeyError(f"unknown or empty CompanyWorld split {split_name!r}")
            selected = [item for item in selected if item.episode_id in allowed]
            split_map = {
                "train": DistributionSplit.TRAIN,
                "public_eval": DistributionSplit.IID_TEST,
                "private_eval": DistributionSplit.IID_TEST,
            }
            split = split_map.get(split_name)
        selected.sort(key=lambda item: item.episode_id)
        if limit is not None:
            selected = selected[: max(0, limit)]
        result: list[ScenarioRef] = []
        for episode in selected:
            seed = int(stable_hash(episode.episode_id)[:8], 16)
            result.append(
                ScenarioRef(
                    scenario_id=episode.episode_id,
                    seed=seed,
                    pool=pool,
                    split=split,
                    task_id=episode.task.task_id,
                )
            )
        return result


@dataclass(frozen=True)
class CompanyWorldRuntimeContext:
    runtime: CompanyWorldRuntime
    episode_id: str
    taskset_version: str
    runtime_version: str
    capability_tags: list[str]

    @property
    def public_task(self) -> dict[str, Any]:
        return self.runtime.episode.task.model_dump(mode="json")


class CompanyWorldObservatoryRuntimeFactory:
    """Resolve Observatory cells to isolated CompanyWorld runtimes."""

    def __init__(
        self,
        repository: CompanyWorldBundleRepository,
        *,
        world_version: str | None = None,
        runtime_version: str = "companyworld-runtime-v2",
    ):
        self.repository = repository
        self.world_id = repository.world_id
        self.world_version = world_version or repository.bundle_version
        self.runtime_version = runtime_version

    def create(self, cell: LongitudinalCell) -> CompanyWorldRuntimeContext:
        if cell.world.world_id != self.world_id or cell.world.version != self.world_version:
            raise ValueError("CompanyWorld runtime factory received an incompatible world cell")
        episode = self.repository.episode(cell.scenario)
        constraints = episode.task.constraints
        world_cost_budget = cell.execution.parameters.get("world_cost_budget")
        if world_cost_budget is None:
            world_cost_budget = constraints.get("budget", 40)
        max_tool_calls = cell.execution.tool_call_budget
        if max_tool_calls is None:
            max_tool_calls = int(constraints.get("max_tool_calls", 30))
        intervention_enabled = any(
            key in constraints
            for key in ("foundry_tool_failures", "foundry_permission_change")
        )
        runtime_type = (
            InterventionAwareCompanyWorldRuntime if intervention_enabled else CompanyWorldRuntime
        )
        runtime = runtime_type(
            episode,
            total_cost=max(1, int(world_cost_budget)),
            max_tool_calls=max(1, int(max_tool_calls)),
        )
        raw_tags = episode.task.metadata.get("capability_tags", [])
        capability_tags = [str(item) for item in raw_tags] if isinstance(raw_tags, list) else []
        return CompanyWorldRuntimeContext(
            runtime=runtime,
            episode_id=episode.episode_id,
            taskset_version=self.repository.taskset_version,
            runtime_version=self.runtime_version,
            capability_tags=capability_tags,
        )
