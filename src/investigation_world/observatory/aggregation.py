from __future__ import annotations

from math import sqrt
from statistics import mean, stdev
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.models import CapabilityRun, DimensionDelta


_T95 = {
    1: 12.706,
    2: 4.303,
    3: 3.182,
    4: 2.776,
    5: 2.571,
    6: 2.447,
    7: 2.365,
    8: 2.306,
    9: 2.262,
    10: 2.228,
    11: 2.201,
    12: 2.179,
    13: 2.160,
    14: 2.145,
    15: 2.131,
    16: 2.120,
    17: 2.110,
    18: 2.101,
    19: 2.093,
    20: 2.086,
    21: 2.080,
    22: 2.074,
    23: 2.069,
    24: 2.064,
    25: 2.060,
    26: 2.056,
    27: 2.052,
    28: 2.048,
    29: 2.045,
    30: 2.042,
}


def critical_95(n: int) -> float:
    """Two-sided 95% Student-t critical value, asymptoting to the normal value."""
    if n <= 1:
        return 0.0
    df = n - 1
    if df <= 30:
        return _T95[df]
    if df <= 40:
        return 2.021
    if df <= 60:
        return 2.000
    if df <= 120:
        return 1.980
    return 1.960


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


class CapabilitySample(BaseModel):
    """One scenario-level observation retained so longitudinal comparisons can stay paired."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    sample_key: str
    scenario_id: str
    task_id: str | None = None
    scenario_seed: int
    run_id: str
    reward: float
    cost: float
    steps: float
    dimensions: dict[str, float] = Field(default_factory=dict)


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
    panel_id: str = ""
    samples: list[CapabilitySample] = Field(default_factory=list)


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
    baseline_panel_id: str = ""
    current_panel_id: str = ""
    panel_match: bool = False
    baseline_n: int = 0
    current_n: int = 0
    matched_n: int = 0
    baseline_coverage: float = 0.0
    current_coverage: float = 0.0


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

    Exact scenario identity remains outside the cohort identity so a distribution can be observed
    longitudinally. Unlike earlier versions, exact scenario/task/seed identity is retained in a
    separate sample panel and all drift is computed from matched scenario-level differences.
    Runtime and taskset versions remain frozen so infrastructure drift is not misclassified as
    model capability drift.
    """
    return {
        "world": run.cell.world.model_dump(mode="json"),
        "scenario_distribution": _scenario_distribution_payload(run),
        "model": _model_payload(run, include_snapshot=False),
        "harness": run.cell.harness.model_dump(mode="json"),
        "verifier": run.cell.verifier.model_dump(mode="json"),
        "execution": run.cell.execution.model_dump(mode="json"),
        "runtime_version": run.provenance.runtime_version,
        "taskset_version": run.provenance.taskset_version,
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


def _sample_key(run: CapabilityRun) -> str:
    scenario = run.cell.scenario
    payload = [scenario.scenario_id, scenario.task_id, scenario.seed]
    return f"SAMPLE-{stable_hash(payload)[:20].upper()}"


def _sample(run: CapabilityRun) -> CapabilitySample:
    scenario = run.cell.scenario
    return CapabilitySample(
        sample_key=_sample_key(run),
        scenario_id=scenario.scenario_id,
        task_id=scenario.task_id,
        scenario_seed=scenario.seed,
        run_id=run.run_id,
        reward=run.total_reward,
        cost=run.total_cost,
        steps=float(run.behavior.total_steps),
        dimensions=dict(run.capability.dimensions),
    )


def _estimate(values: list[float]) -> MetricEstimate:
    n = len(values)
    if n == 0:
        raise ValueError("cannot estimate an empty metric")
    center = mean(values)
    deviation = stdev(values) if n > 1 else 0.0
    error = deviation / sqrt(n) if n > 1 else 0.0
    margin = critical_95(n) * error
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

    samples = [_sample(run) for run in items]
    sample_keys = [sample.sample_key for sample in samples]
    if len(sample_keys) != len(set(sample_keys)):
        raise ValueError("duplicate scenario/task/seed observations are not allowed in one aggregate")

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
    panel_id = f"PANEL-{stable_hash(sorted(sample_keys))[:20].upper()}"
    aggregate_id = f"AGG-{stable_hash([expected_snapshot_key, panel_id, run_ids])[:20].upper()}"
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
        panel_id=panel_id,
        samples=sorted(samples, key=lambda sample: sample.sample_key),
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


def _paired_delta(before: list[float], after: list[float], *, tolerance: float) -> DimensionDelta:
    if len(before) != len(after) or not before:
        raise ValueError("paired drift requires non-empty equal-length samples")
    return _delta(mean(before), mean(after), tolerance=tolerance)


def compare_aggregates(
    baseline: AggregatedCapabilityProfile,
    current: AggregatedCapabilityProfile,
    *,
    tolerance: float = 1e-9,
) -> AggregateDriftReport:
    if baseline.cohort_key != current.cohort_key:
        raise ValueError("aggregates are not cohort-comparable")
    if not baseline.samples or not current.samples:
        raise ValueError("aggregate drift requires scenario-level samples for matched comparison")

    baseline_by_key = {sample.sample_key: sample for sample in baseline.samples}
    current_by_key = {sample.sample_key: sample for sample in current.samples}
    matched_keys = sorted(set(baseline_by_key) & set(current_by_key))
    if not matched_keys:
        raise ValueError("aggregate drift has no matched scenario/task/seed observations")

    baseline_samples = [baseline_by_key[key] for key in matched_keys]
    current_samples = [current_by_key[key] for key in matched_keys]

    dimensions: dict[str, DimensionDelta] = {}
    regressions: list[str] = []
    improvements: list[str] = []
    names = sorted(
        set.intersection(
            *(set(sample.dimensions) for sample in baseline_samples + current_samples)
        )
    ) if baseline_samples and current_samples else []
    for name in names:
        delta = _paired_delta(
            [sample.dimensions[name] for sample in baseline_samples],
            [sample.dimensions[name] for sample in current_samples],
            tolerance=tolerance,
        )
        dimensions[name] = delta
        if delta.delta < -tolerance:
            regressions.append(name)
        elif delta.delta > tolerance:
            improvements.append(name)

    baseline_n = len(baseline.samples)
    current_n = len(current.samples)
    matched_n = len(matched_keys)
    return AggregateDriftReport(
        cohort_key=current.cohort_key,
        baseline_aggregate_id=baseline.aggregate_id,
        current_aggregate_id=current.aggregate_id,
        baseline_snapshot=baseline.time_snapshot,
        current_snapshot=current.time_snapshot,
        reward=_paired_delta(
            [sample.reward for sample in baseline_samples],
            [sample.reward for sample in current_samples],
            tolerance=tolerance,
        ),
        cost=_paired_delta(
            [sample.cost for sample in baseline_samples],
            [sample.cost for sample in current_samples],
            tolerance=tolerance,
        ),
        steps=_paired_delta(
            [sample.steps for sample in baseline_samples],
            [sample.steps for sample in current_samples],
            tolerance=tolerance,
        ),
        dimensions=dimensions,
        regressions=regressions,
        improvements=improvements,
        baseline_panel_id=baseline.panel_id,
        current_panel_id=current.panel_id,
        panel_match=baseline.panel_id == current.panel_id,
        baseline_n=baseline_n,
        current_n=current_n,
        matched_n=matched_n,
        baseline_coverage=matched_n / baseline_n,
        current_coverage=matched_n / current_n,
    )
