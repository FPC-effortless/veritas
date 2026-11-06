from __future__ import annotations

from collections.abc import Iterable

from investigation_world.foundry.models import (
    DifficultyVector,
    DistributionSplit,
    FoundryTaskMetadata,
)
from investigation_world.tasks.spec import TaskFamily, TaskSpec


_FAMILY_CAPABILITIES: dict[TaskFamily, list[str]] = {
    TaskFamily.ENTITY_RESOLUTION: [
        "discover",
        "entity_resolution",
        "uncertainty",
        "evidence",
        "verify",
    ],
    TaskFamily.OWNERSHIP: [
        "discover",
        "relationship_reconstruction",
        "provenance",
        "evidence",
        "verify",
    ],
    TaskFamily.TEMPORAL: [
        "discover",
        "temporal_reconstruction",
        "relationship_reconstruction",
        "evidence",
        "verify",
    ],
    TaskFamily.PROVENANCE: [
        "source_selection",
        "provenance",
        "evidence",
        "verify",
    ],
    TaskFamily.CONFLICT: [
        "conflict_resolution",
        "hypothesis_management",
        "uncertainty",
        "evidence",
        "verify",
    ],
    TaskFamily.DUE_DILIGENCE: [
        "discover",
        "entity_resolution",
        "relationship_reconstruction",
        "temporal_reconstruction",
        "provenance",
        "hypothesis_management",
        "uncertainty",
        "evidence",
        "verify",
        "communicate",
    ],
}


def infer_external_investigation_difficulty(task: TaskSpec) -> DifficultyVector:
    difficulty = task.difficulty
    candidate_entities = max(1, int(round(float(difficulty.get("candidate_entities", 1.0)))))
    graph_hops = max(1, int(round(float(difficulty.get("required_graph_hops", 1.0)))))
    temporal_depth = max(0, int(round(float(difficulty.get("temporal_depth", 0.0)))))
    noise_ratio = max(0.0, min(1.0, float(difficulty.get("noise_ratio", 0.0))))
    budget_tightness = max(
        0.0,
        min(1.0, float(difficulty.get("budget_tightness", 0.0))),
    )
    conflict_probability = max(0.0, min(1.0, noise_ratio * 0.5))
    if task.family == TaskFamily.CONFLICT:
        conflict_probability = max(conflict_probability, 0.5)
    return DifficultyVector(
        entities=candidate_entities,
        tools=6,
        steps=max(1, graph_hops + temporal_depth),
        distractors=max(0, int(round(candidate_entities * noise_ratio))),
        missing_probability=min(1.0, noise_ratio * 0.35),
        conflict_probability=conflict_probability,
        dependency_depth=max(graph_hops, temporal_depth),
        budget_ratio=max(0.05, 1.0 - 0.9 * budget_tightness),
        stochasticity=0.0,
        adversarial_pressure=noise_ratio,
    )


def external_investigation_task_metadata(
    task: TaskSpec,
    *,
    split: DistributionSplit,
    taskset_version: str,
    harness_version: str,
    runtime_version: str,
    seed: int,
) -> FoundryTaskMetadata:
    return FoundryTaskMetadata(
        task_id=f"{task.world_id}::{task.task_id}",
        split=split,
        capability_tags=_FAMILY_CAPABILITIES[task.family],
        difficulty=infer_external_investigation_difficulty(task),
        seed=seed,
        taskset_version=taskset_version,
        harness_version=harness_version,
        runtime_version=runtime_version,
        generator_parameters={
            "capability_family": "external_investigation",
            "world_id": task.world_id,
            "local_task_id": task.task_id,
            "task_family": task.family.value,
            "query_date": task.query_date.isoformat() if task.query_date else None,
            "must_cite_evidence": bool(task.constraints.get("must_cite_evidence", False)),
        },
    )


def adapt_external_investigation_tasks(
    tasks: Iterable[TaskSpec],
    *,
    split: DistributionSplit,
    taskset_version: str,
    harness_version: str,
    runtime_version: str,
    seed_start: int,
) -> list[FoundryTaskMetadata]:
    return [
        external_investigation_task_metadata(
            task,
            split=split,
            taskset_version=taskset_version,
            harness_version=harness_version,
            runtime_version=runtime_version,
            seed=seed_start + index,
        )
        for index, task in enumerate(tasks)
    ]
