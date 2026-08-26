from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FoundryMetrics:
    capability_gain: float
    transfer: float
    verifier_reliability: float
    task_coverage: float
    rollout_cost: float
    reward_exploitability: float
    variance: float
    environment_brittleness: float


def foundry_objective(metrics: FoundryMetrics, *, epsilon: float = 1e-6) -> float:
    numerator = (
        max(0.0, metrics.capability_gain)
        * max(0.0, metrics.transfer)
        * max(0.0, metrics.verifier_reliability)
        * max(0.0, metrics.task_coverage)
    )
    denominator = (
        max(epsilon, metrics.rollout_cost)
        * max(epsilon, metrics.reward_exploitability)
        * max(epsilon, metrics.variance)
        * max(epsilon, metrics.environment_brittleness)
    )
    return numerator / denominator


@dataclass(frozen=True)
class EfficiencyPoint:
    quality: float
    cost: float
    latency: float
    risk: float


def pareto_frontier(points: list[EfficiencyPoint]) -> list[EfficiencyPoint]:
    result: list[EfficiencyPoint] = []
    for candidate in points:
        dominated = False
        for other in points:
            if other is candidate:
                continue
            no_worse = (
                other.quality >= candidate.quality
                and other.cost <= candidate.cost
                and other.latency <= candidate.latency
                and other.risk <= candidate.risk
            )
            strictly_better = (
                other.quality > candidate.quality
                or other.cost < candidate.cost
                or other.latency < candidate.latency
                or other.risk < candidate.risk
            )
            if no_worse and strictly_better:
                dominated = True
                break
        if not dominated:
            result.append(candidate)
    return result
