from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.aggregation import (
    AggregateDriftReport,
    AggregatedCapabilityProfile,
    aggregate_runs,
    cohort_key,
    compare_aggregates,
    snapshot_key,
)
from investigation_world.observatory.models import (
    CapabilityRun,
    ExperimentSpec,
    LongitudinalCell,
    ScenarioPool,
)
from investigation_world.observatory.scheduler import (
    JobStatus,
    LocalObservatoryScheduler,
    SchedulerPolicy,
    SchedulerReport,
)
from investigation_world.observatory.store import ObservatoryStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ObservationCycleReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cycle_id: str
    experiment_id: str
    started_at: datetime
    finished_at: datetime
    scheduler: SchedulerReport
    run_ids: list[str] = Field(default_factory=list)
    aggregates: list[AggregatedCapabilityProfile] = Field(default_factory=list)
    drift: list[AggregateDriftReport] = Field(default_factory=list)

    @property
    def has_regression(self) -> bool:
        return any(item.regressions for item in self.drift)


def _group_aggregates(runs: Iterable[CapabilityRun]) -> list[AggregatedCapabilityProfile]:
    groups: dict[str, list[CapabilityRun]] = defaultdict(list)
    for run in runs:
        groups[snapshot_key(run)].append(run)
    return [aggregate_runs(groups[key]) for key in sorted(groups)]


def _latest_baseline(
    historical: list[CapabilityRun],
    current: AggregatedCapabilityProfile,
) -> AggregatedCapabilityProfile | None:
    candidates = [
        run
        for run in historical
        if cohort_key(run) == current.cohort_key and snapshot_key(run) != current.snapshot_key
    ]
    if not candidates:
        return None
    by_snapshot: dict[str, list[CapabilityRun]] = defaultdict(list)
    for run in candidates:
        by_snapshot[snapshot_key(run)].append(run)
    ranked = sorted(
        by_snapshot.values(),
        key=lambda group: max(item.finished_at for item in group),
    )
    return aggregate_runs(ranked[-1])


class ObservationCycleRunner:
    """Execute one observation cycle and emit aggregate capability drift artifacts."""

    def __init__(
        self,
        scheduler: LocalObservatoryScheduler,
        store: ObservatoryStore,
        *,
        report_root: str | Path | None = None,
    ):
        self.scheduler = scheduler
        self.store = store
        self.report_root = Path(report_root) if report_root is not None else store.root / "cycles"

    def run(
        self,
        experiment: ExperimentSpec,
        cells: Iterable[LongitudinalCell],
        *,
        policy: SchedulerPolicy | None = None,
        persist_report: bool = True,
    ) -> ObservationCycleReport:
        started_at = utc_now()
        historical = self.store.load()
        cfg = policy or SchedulerPolicy(pools={ScenarioPool.ANCHOR})
        scheduler_report = self.scheduler.run(experiment, cells, policy=cfg)
        current_by_id = {run.run_id: run for run in self.store.load()}
        run_ids = sorted(
            {
                outcome.run_id
                for outcome in scheduler_report.outcomes
                if outcome.status in {JobStatus.SUCCEEDED, JobStatus.SKIPPED}
                and outcome.run_id is not None
            }
        )
        current_runs = [current_by_id[run_id] for run_id in run_ids if run_id in current_by_id]
        aggregates = _group_aggregates(current_runs)
        drift: list[AggregateDriftReport] = []
        for aggregate in aggregates:
            baseline = _latest_baseline(historical, aggregate)
            if baseline is not None:
                drift.append(compare_aggregates(baseline, aggregate))
        cycle_id = f"CYCLE-{stable_hash([experiment.experiment_id, run_ids])[:20].upper()}"
        report = ObservationCycleReport(
            cycle_id=cycle_id,
            experiment_id=experiment.experiment_id,
            started_at=started_at,
            finished_at=utc_now(),
            scheduler=scheduler_report,
            run_ids=run_ids,
            aggregates=aggregates,
            drift=drift,
        )
        if persist_report:
            self.report_root.mkdir(parents=True, exist_ok=True)
            target = self.report_root / f"{cycle_id}.json"
            target.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        return report


def load_cycle_reports(root: str | Path) -> list[ObservationCycleReport]:
    path = Path(root)
    if not path.exists():
        return []
    reports: list[ObservationCycleReport] = []
    for file in sorted(path.glob("CYCLE-*.json")):
        reports.append(ObservationCycleReport.model_validate_json(file.read_text(encoding="utf-8")))
    return reports
