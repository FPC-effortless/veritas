from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import DistributionSplit, DifficultyVector, stable_hash
from investigation_world.projectworld.construction import construction_episode
from investigation_world.projectworld.models import OperationalProjectEpisode, ProjectStateValue


class ProjectWorldGenerationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    split: DistributionSplit
    seed: int
    count: int = Field(default=10, ge=1, le=10_000)
    domain: str = "construction"
    taskset_version: str = "construction-projectworld-v1"
    overrides: dict[str, Any] = Field(default_factory=dict)


class GeneratedProjectWorld(BaseModel):
    model_config = ConfigDict(extra="forbid")
    episode: OperationalProjectEpisode
    split: DistributionSplit
    seed: int
    difficulty: DifficultyVector
    generator_parameters: dict[str, Any]
    episode_hash: str


class ProjectWorldDistribution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = "veritas-operational-projectworld-distribution-v1"
    spec: ProjectWorldGenerationSpec
    worlds: list[GeneratedProjectWorld]
    manifest_hash: str


def _difficulty(split: DistributionSplit) -> DifficultyVector:
    if split == DistributionSplit.TRAIN:
        return DifficultyVector(entities=24, tools=12, steps=20, dependency_depth=8, stochasticity=0.15)
    if split == DistributionSplit.IID_TEST:
        return DifficultyVector(entities=26, tools=12, steps=22, dependency_depth=8, stochasticity=0.2)
    if split == DistributionSplit.OOD:
        return DifficultyVector(
            entities=34,
            tools=14,
            steps=28,
            distractors=4,
            conflict_probability=0.15,
            dependency_depth=10,
            budget_ratio=0.85,
            stochasticity=0.35,
        )
    return DifficultyVector(
        entities=38,
        tools=15,
        steps=32,
        distractors=8,
        missing_probability=0.08,
        conflict_probability=0.25,
        dependency_depth=10,
        budget_ratio=0.72,
        stochasticity=0.45,
        adversarial_pressure=0.7,
    )


def _mutate_episode(
    episode: OperationalProjectEpisode,
    *,
    split: DistributionSplit,
    rng: random.Random,
) -> dict[str, Any]:
    params: dict[str, Any] = {}
    if split in {DistributionSplit.TRAIN, DistributionSplit.IID_TEST}:
        duration_scale = rng.uniform(0.9, 1.15)
        cost_scale = rng.uniform(0.9, 1.12)
        capacity_drop_probability = 0.05
    elif split == DistributionSplit.OOD:
        duration_scale = rng.uniform(1.15, 1.65)
        cost_scale = rng.uniform(1.1, 1.45)
        capacity_drop_probability = 0.25
    else:
        duration_scale = rng.uniform(1.35, 1.9)
        cost_scale = rng.uniform(1.2, 1.6)
        capacity_drop_probability = 0.45

    for activity in episode.activities:
        activity.duration_ticks = max(1, round(activity.duration_ticks * duration_scale))
        activity.planned_cost = round(activity.planned_cost * cost_scale, 2)

    reduced_resources: list[str] = []
    for resource in episode.resources:
        if resource.capacity > 1 and rng.random() < capacity_drop_probability:
            resource.capacity -= 1
            reduced_resources.append(resource.resource_id)

    if split == DistributionSplit.ADVERSARIAL:
        episode.task.budget_limit = round(
            sum(item.planned_cost for item in episode.activities) * rng.uniform(1.01, 1.08), 2
        )
        for event in episode.oracle.hidden_events:
            event.due_tick = max(1, event.due_tick - rng.randint(1, 3))
        episode.evidence.append(
            episode.evidence[0].model_copy(
                update={
                    "evidence_id": f"DISTRACTOR-{rng.randint(1000, 9999)}",
                    "evidence_type": "unverified_note",
                    "title": "Unverified field note",
                    "text": "A plausible but non-authoritative field note that may conflict with verified project evidence.",
                    "authoritative": False,
                    "source_ids": ["adversarial-generator"],
                }
            )
        )
    elif split == DistributionSplit.OOD:
        episode.task.budget_limit = round(
            sum(item.planned_cost for item in episode.activities) * rng.uniform(1.12, 1.3), 2
        )

    event_jitter: dict[str, int] = {}
    for event in episode.oracle.hidden_events:
        jitter = rng.choice([-1, 0, 0, 1])
        event.due_tick = max(1, min(episode.task.max_ticks - 1, event.due_tick + jitter))
        event_jitter[event.event_id] = jitter

    episode.initial_state.append(
        ProjectStateValue(
            object_type="project",
            object_id=episode.episode_id.removeprefix("EP-"),
            field_name="scenario_split",
            value=split.value,
            namespace="project",
            source_ids=["projectworld-foundry"],
        )
    )
    params.update(
        {
            "duration_scale": round(duration_scale, 4),
            "cost_scale": round(cost_scale, 4),
            "reduced_resources": reduced_resources,
            "event_jitter": event_jitter,
            "budget_limit": episode.task.budget_limit,
        }
    )
    return params


def generate_construction_distribution(
    spec: ProjectWorldGenerationSpec,
) -> ProjectWorldDistribution:
    if spec.domain != "construction":
        raise ValueError("only the construction domain pack is implemented in v1")
    worlds: list[GeneratedProjectWorld] = []
    difficulty = _difficulty(spec.split)
    for index in range(spec.count):
        episode_seed = spec.seed + index * 104_729
        rng = random.Random(episode_seed)
        project_id = f"CW-{spec.split.value.upper()}-{episode_seed:010d}"
        base_budget = float(spec.overrides.get("budget_limit", rng.uniform(34_000_000, 44_000_000)))
        episode = construction_episode(project_id=project_id, budget_limit=base_budget)
        parameters = _mutate_episode(episode, split=spec.split, rng=rng)
        episode.metadata["foundry"] = {
            "split": spec.split.value,
            "seed": episode_seed,
            "taskset_version": spec.taskset_version,
            "generator_parameters": parameters,
        }
        payload = episode.model_dump(mode="json")
        episode_hash = stable_hash(payload)
        worlds.append(
            GeneratedProjectWorld(
                episode=episode,
                split=spec.split,
                seed=episode_seed,
                difficulty=difficulty,
                generator_parameters=parameters,
                episode_hash=episode_hash,
            )
        )

    manifest_payload = {
        "spec": spec.model_dump(mode="json"),
        "world_hashes": [item.episode_hash for item in worlds],
    }
    return ProjectWorldDistribution(
        spec=spec,
        worlds=worlds,
        manifest_hash=stable_hash(manifest_payload),
    )


def default_construction_splits(
    *,
    train_count: int = 100,
    eval_count: int = 25,
) -> dict[DistributionSplit, ProjectWorldDistribution]:
    return {
        DistributionSplit.TRAIN: generate_construction_distribution(
            ProjectWorldGenerationSpec(split=DistributionSplit.TRAIN, seed=42, count=train_count)
        ),
        DistributionSplit.IID_TEST: generate_construction_distribution(
            ProjectWorldGenerationSpec(split=DistributionSplit.IID_TEST, seed=43, count=eval_count)
        ),
        DistributionSplit.OOD: generate_construction_distribution(
            ProjectWorldGenerationSpec(split=DistributionSplit.OOD, seed=142, count=eval_count)
        ),
        DistributionSplit.ADVERSARIAL: generate_construction_distribution(
            ProjectWorldGenerationSpec(split=DistributionSplit.ADVERSARIAL, seed=242, count=eval_count)
        ),
    }
