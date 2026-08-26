from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from investigation_world.foundry.models import RolloutTrace
from investigation_world.observatory.models import (
    BehavioralFingerprint,
    CapabilityDriftReport,
    CapabilityProfile,
    CapabilityRun,
    DimensionDelta,
    LongitudinalCell,
    RunProvenance,
)


def _contains_failure_signal(value: Any) -> bool:
    if isinstance(value, dict):
        if value.get("success") is False or value.get("passed") is False:
            return True
        if value.get("error") not in {None, "", False}:
            return True
        return any(_contains_failure_signal(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_failure_signal(child) for child in value)
    return False


def behavior_from_trace(trace: RolloutTrace) -> BehavioralFingerprint:
    counts = Counter(event.event_type for event in trace.events)
    total = len(trace.events)
    changed = sum(
        event.state_hash_before is not None
        and event.state_hash_after is not None
        and event.state_hash_before != event.state_hash_after
        for event in trace.events
    )
    verification = sum(
        "verify" in event.event_type.lower() or "submit" in event.event_type.lower()
        for event in trace.events
    )
    recovery = sum(
        any(
            token in event.event_type.lower()
            for token in ("recover", "retry", "repair", "replay", "fallback")
        )
        for event in trace.events
    )
    failure_signals = sum(
        "fail" in event.event_type.lower()
        or "error" in event.event_type.lower()
        or _contains_failure_signal(event.payload)
        for event in trace.events
    )
    return BehavioralFingerprint(
        total_steps=total,
        total_cost=trace.total_cost,
        unique_event_types=len(counts),
        event_counts=dict(sorted(counts.items())),
        tool_mix={key: value / total for key, value in sorted(counts.items())} if total else {},
        state_change_rate=changed / total if total else 0.0,
        verification_events=verification,
        recovery_events=recovery,
        failure_signals=failure_signals,
        mean_step_cost=trace.total_cost / total if total else 0.0,
    )


def capability_from_trace(trace: RolloutTrace) -> CapabilityProfile:
    dimensions = dict(sorted(trace.verifier_components.items()))
    dimensions.setdefault("overall_reward", trace.total_reward)
    return CapabilityProfile(dimensions=dimensions)


def validate_cell_trace_alignment(cell: LongitudinalCell, trace: RolloutTrace) -> None:
    errors: list[str] = []
    if cell.world.version != trace.environment_version:
        errors.append(
            f"world version {cell.world.version!r} != trace {trace.environment_version!r}"
        )
    if cell.scenario.seed != trace.task_seed:
        errors.append(f"scenario seed {cell.scenario.seed} != trace {trace.task_seed}")
    if cell.scenario.task_id is not None and cell.scenario.task_id != trace.task_id:
        errors.append(f"task id {cell.scenario.task_id!r} != trace {trace.task_id!r}")
    if cell.harness.version != trace.harness_version:
        errors.append(
            f"harness version {cell.harness.version!r} != trace {trace.harness_version!r}"
        )
    if errors:
        raise ValueError("cell/trace mismatch: " + "; ".join(errors))


def capability_run_from_trace(
    cell: LongitudinalCell,
    trace: RolloutTrace,
    *,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    metadata: dict[str, Any] | None = None,
    validate_alignment: bool = True,
) -> CapabilityRun:
    if validate_alignment:
        validate_cell_trace_alignment(cell, trace)
    payload: dict[str, Any] = {
        "cell": cell,
        "provenance": RunProvenance(
            trace_id=trace.trace_id,
            environment_version=trace.environment_version,
            task_id=trace.task_id,
            taskset_version=trace.taskset_version,
            runtime_version=trace.runtime_version,
            harness_version=trace.harness_version,
        ),
        "capability": capability_from_trace(trace),
        "behavior": behavior_from_trace(trace),
        "total_reward": trace.total_reward,
        "total_cost": trace.total_cost,
        "termination_reason": trace.termination_reason,
        "metadata": metadata or {},
    }
    if started_at is not None:
        payload["started_at"] = started_at
    if finished_at is not None:
        payload["finished_at"] = finished_at
    return CapabilityRun.model_validate(payload)


def compare_runs(
    baseline: CapabilityRun,
    current: CapabilityRun,
    *,
    tolerance: float = 1e-9,
) -> CapabilityDriftReport:
    if baseline.cell.longitudinal_key != current.cell.longitudinal_key:
        raise ValueError("runs are not longitudinally comparable")
    dimensions: dict[str, DimensionDelta] = {}
    regressions: list[str] = []
    improvements: list[str] = []
    names = sorted(set(baseline.capability.dimensions) | set(current.capability.dimensions))
    for name in names:
        before = baseline.capability.dimensions.get(name, 0.0)
        after = current.capability.dimensions.get(name, 0.0)
        delta = after - before
        relative = delta / abs(before) if abs(before) > tolerance else None
        dimensions[name] = DimensionDelta(
            baseline=before,
            current=after,
            delta=delta,
            relative_delta=relative,
        )
        if delta < -tolerance:
            regressions.append(name)
        elif delta > tolerance:
            improvements.append(name)
    return CapabilityDriftReport(
        longitudinal_key=current.cell.longitudinal_key,
        baseline_run_id=baseline.run_id,
        current_run_id=current.run_id,
        baseline_snapshot=baseline.cell.time_snapshot,
        current_snapshot=current.cell.time_snapshot,
        reward_delta=current.total_reward - baseline.total_reward,
        cost_delta=current.total_cost - baseline.total_cost,
        step_delta=current.behavior.total_steps - baseline.behavior.total_steps,
        dimensions=dimensions,
        regressions=regressions,
        improvements=improvements,
    )
