from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from pydantic import BaseModel, Field

from investigation_world.foundry.challenges import ChallengeSpec, challenge_from_trace
from investigation_world.foundry.curriculum import TaskPerformance, select_frontier_tasks
from investigation_world.foundry.models import FoundryTaskMetadata, RolloutTrace
from investigation_world.foundry.promotion import ChallengeValidation, PromotionPolicy, promotable


class FoundryCycleConfig(BaseModel):
    frontier_low: float = Field(default=0.10, ge=0.0, le=1.0)
    frontier_high: float = Field(default=0.70, ge=0.0, le=1.0)
    frontier_limit: int = Field(default=100, ge=1)
    failure_reward_threshold: float = Field(default=0.80, ge=0.0, le=1.0)
    seed: int = 0
    promotion_policy: PromotionPolicy = Field(default_factory=PromotionPolicy)


class FoundryCycleResult(BaseModel):
    task_performance: list[TaskPerformance] = Field(default_factory=list)
    frontier_task_ids: list[str] = Field(default_factory=list)
    challenge_proposals: list[ChallengeSpec] = Field(default_factory=list)
    promoted_challenge_ids: list[str] = Field(default_factory=list)
    rejected_challenge_ids: list[str] = Field(default_factory=list)
    trace_count: int = 0


def aggregate_task_performance(traces: Iterable[RolloutTrace]) -> list[TaskPerformance]:
    grouped: dict[str, list[RolloutTrace]] = defaultdict(list)
    for trace in traces:
        grouped[trace.task_id].append(trace)
    result = []
    for task_id, items in sorted(grouped.items()):
        result.append(TaskPerformance(
            task_id=task_id,
            attempts=len(items),
            successes=sum(item.total_reward >= 0.99 for item in items),
            mean_reward=sum(item.total_reward for item in items) / len(items),
        ))
    return result


def run_foundry_cycle(
    tasks: Iterable[FoundryTaskMetadata],
    traces: Iterable[RolloutTrace],
    *,
    validations: Iterable[ChallengeValidation] = (),
    config: FoundryCycleConfig | None = None,
) -> FoundryCycleResult:
    cfg = config or FoundryCycleConfig()
    task_list = list(tasks)
    trace_list = list(traces)
    performance = aggregate_task_performance(trace_list)
    frontier = select_frontier_tasks(
        task_list,
        performance,
        limit=cfg.frontier_limit,
        seed=cfg.seed,
        low=cfg.frontier_low,
        high=cfg.frontier_high,
    )

    proposals_by_id: dict[str, ChallengeSpec] = {}
    for trace in trace_list:
        if trace.total_reward < cfg.failure_reward_threshold:
            challenge = challenge_from_trace(trace)
            proposals_by_id.setdefault(challenge.challenge_id, challenge)

    validation_by_id = {item.challenge_id: item for item in validations}
    promoted: list[str] = []
    rejected: list[str] = []
    for challenge_id in sorted(proposals_by_id):
        validation = validation_by_id.get(challenge_id)
        if validation is None:
            continue
        if promotable(validation, cfg.promotion_policy):
            promoted.append(challenge_id)
        else:
            rejected.append(challenge_id)

    return FoundryCycleResult(
        task_performance=performance,
        frontier_task_ids=frontier,
        challenge_proposals=[proposals_by_id[key] for key in sorted(proposals_by_id)],
        promoted_challenge_ids=promoted,
        rejected_challenge_ids=rejected,
        trace_count=len(trace_list),
    )
