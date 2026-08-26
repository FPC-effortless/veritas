from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Iterable

from investigation_world.foundry.models import FoundryTaskMetadata


@dataclass(frozen=True)
class TaskPerformance:
    task_id: str
    attempts: int
    successes: int
    mean_reward: float

    @property
    def success_rate(self) -> float:
        return self.successes / self.attempts if self.attempts else 0.0


def frontier_priority(
    performance: TaskPerformance,
    *,
    low: float = 0.10,
    high: float = 0.70,
    exploration_attempts: int = 3,
) -> float:
    if performance.attempts < exploration_attempts:
        return 2.0 + (exploration_attempts - performance.attempts) / exploration_attempts
    midpoint = (low + high) / 2.0
    half_width = max((high - low) / 2.0, 1e-9)
    distance = abs(performance.success_rate - midpoint) / half_width
    frontier = max(0.0, 1.0 - distance)
    if low <= performance.success_rate <= high:
        frontier += 1.0
    return frontier


def select_frontier_tasks(
    task_metadata: Iterable[FoundryTaskMetadata],
    performance: Iterable[TaskPerformance],
    *,
    limit: int,
    seed: int = 0,
    low: float = 0.10,
    high: float = 0.70,
) -> list[str]:
    perf = {item.task_id: item for item in performance}
    ranked: list[tuple[float, str, str]] = []
    for task in task_metadata:
        item = perf.get(task.task_id, TaskPerformance(task.task_id, 0, 0, 0.0))
        priority = frontier_priority(item, low=low, high=high)
        tie = hashlib.sha256(f"{seed}|{task.task_id}".encode()).hexdigest()
        ranked.append((-priority, tie, task.task_id))
    ranked.sort()
    return [task_id for _, _, task_id in ranked[: max(0, limit)]]
