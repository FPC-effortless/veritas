from __future__ import annotations

from math import sqrt
from statistics import mean, stdev
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.models import CapabilityRun, DimensionDelta


class MetricEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    n: int = Field(ge=1)
    mean: float
    stddev: float = Field(ge=0.0)
    standard_error: float = Field(ge=0.0)
    ci95_low: float
    ci95_high: float
    minimum: float
    maximum: float


class AggregatedCapabilityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    aggregate_id: str
    cohort_key: str
    snapshot_key: str
    time_snapshot: str
    model_snapshot: str
    run_ids: list[str]
    reward: MetricEstimate
    cost: MetricEstimate
    steps: MetricEstimate
    dimensions: dict[str, MetricEstimate] = Field(default_factory=dict)


class AggregateDriftReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cohort_key: str
    baseline_aggregate_id: str
    current_aggregate_id: str
    baseline_snapshot: str
    current_snapshot: str
    reward: DimensionDelta
    cost: DimensionDelta
    steps: DimensionDelta
    dimensions: dict[str, DimensionDelta] = Field(default_factory=dict)
    regressions: list[str] = Field(default_factory=list)
    improvements: list[str] = Field(default_factory=list)


def _scenario_distribution_payload(run: CapabilityRun) -> dict[str, Any]:
    scenario = run.cell.scenario
    return {
        "pool": scenario.pool.value,
        "split": scenario.split.value if scenario.split is not None else None,
    }


def _model_payload(run: CapabilityRun, *, include_snapshot: bool) -> dict[str, Any]:
    payload = run.cell.model.model_dump(mode="json")
    if not include_snapshot:
        payload.pop("snapshot", None)
    return payload


def cohort_payload(run: CapabilityRun) -> dict[str, Any]:
    """Identity for a repeated-seed cohort across time/model snapshots.

    Scenario identity and seed are intentionally excluded; pool and distribution split remain.
    """
    return {
        "world": run.cell.world.model_dump(mode="json"),
        "scenario_distribution": _scenario_distribution_payload(run),
        "model": _model_payload(run, include_snapshot=False),
        "harness": run.cell.harness.model_dump(mode="json"),
        "verifier": run.cell.verifier.model_dump(mode="json"),
        "execution": run.cell.execution.model_dump(mode="json"),
    }


def snapshot_payload(run: CapabilityRun) -> dict[str, Any]:
    payload = cohort_payload(run)
    payload["model"] = _model_payload(run, include_snapshot=True)
    payload["time_snapshot"] = run.cell.time_snapshot
    return payload


def cohort_key(run: CapabilityRun) -> str:
    return f"COHORT-{stable_hash(cohort_payload(run))[:20].upper()}"


def snapshot_key(run: CapabilityRun) -> str:
    return f"SNAP-{stable_hash(snapshot_payload(run))[:20].upper()}"


def _estimate(values: list[float]) -> MetricEstimate:
    n = len(values)
    if n == 0:
        raise ValueError("cannot estimate an empty metric")
    center = mean(values)
    deviation = stdev(values) if n > 1 else 0.0
    error = deviation / sqrt(n) if n > 1 else 0.0
    margin = 1.96 * error
    return MetricEstimate(
        n=n,
        mean=center,
        stddev=deviation,
        standard_error=error,
        ci95_low=center - margin,
        ci95_high=center + margin,
        minimum=min(values),
        maximum=max(values),
    )


def aggregate_runs(runs: Iterable[CapabilityRun]) -> AggregatedCapabilityProfile:
    items = list(runs)
    if not items:
        raise ValueError("cannot aggregate zero runs")
    expected_snapshot_key = snapshot_key(items[0])
    mismatched = [run.run_id for run in items if snapshot_key(run) != expected_snapshot_key]
    if mismatched:
        raise ValueError(
            "runs do not belong to one snapshot cohort; mismatched run ids: "
            + ", ".join(sorted(mismatched))
        )

    dimension_names = sorted(
        set().union(*(run.capability.dimensions.keys() for run in items))
    )
    dimensions: dict[str, MetricEstimate] = {}
    for name in dimension_names:
        present = [
            run.capability.dimensions[name]
            for run in items
            if name in run.capability.dimensions
        ]
        dimensions[name] = _estimate(present)

    first = items[0]
    run_ids = sorted(run.run_id for run in items)
    aggregate_id = f"AGG-{stable_hash([expected_snapshot_key, run_ids])[:20].upper()}"
    return AggregatedCapabilityProfile(
        aggregate_id=aggregate_id,
        cohort_key=cohort_key(first),
        snapshot_key=expected_snapshot_key,
        time_snapshot=first.cell.time_snapshot,
        model_snapshot=first.cell.model.snapshot,
        run_ids=run_ids,
        reward=_estimate([run.total_reward for run in items]),
        cost=_estimate([run.total_cost for run in items]),
        steps=_estimate([float(run.behavior.total_steps) for run in items]),
        dimensions=dimensions,
    )


def _delta(before: float, after: float, *, tolerance: float) -> DimensionDelta:
    change = after - before
    relative = change / abs(before) if abs(before) > tolerance else None
    return DimensionDelta(
        baseline=before,
        current=after,
        delta=change,
        relative_delta=relative,
    )


def compare_aggregates(
    baseline: AggregatedCapabilityProfile,
    current: AggregatedCapabilityProfile,
    *,
    tolerance: float = 1e-9,
) -> AggregateDriftReport:
    if baseline.cohort_key != current.cohort_key:
        raise ValueError("aggregates are not cohort-comparable")

    dimensions: dict[str, DimensionDelta] = {}
    regressions: list[str] = []
    improvements: list[str] = []
    names = sorted(set(baseline.dimensions) | set(current.dimensions))
    for name in names:
        before = baseline.dimensions.get(name)
        after = current.dimensions.get(name)
        if before is None or after is None:
            continue
        delta = _delta(before.mean, after.mean, tolerance=tolerance)
        dimensions[name] = delta
        if delta.delta < -tolerance:
            regressions.append(name)
        elif delta.delta > tolerance:
            improvements.append(name)

    return AggregateDriftReport(
        cohort_key=current.cohort_key,
        baseline_aggregate_id=baseline.aggregate_id,
        current_aggregate_id=current.aggregate_id,
        baseline_snapshot=baseline.time_snapshot,
        current_snapshot=current.time_snapshot,
        reward=_delta(baseline.reward.mean, current.reward.mean, tolerance=tolerance),
        cost=_delta(baseline.cost.mean, current.cost.mean, tolerance=tolerance),
        steps=_delta(baseline.steps.mean, current.steps.mean, tolerance=tolerance),
        dimensions=dimensions,
        regressions=regressions,
        improvements=improvements,
    )
