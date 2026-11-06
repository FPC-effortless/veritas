from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from enum import StrEnum
from threading import Lock
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.execution import ObservatoryExecutionEngine
from investigation_world.observatory.models import (
    CapabilityRun,
    ExperimentSpec,
    LongitudinalCell,
    ScenarioPool,
)
from investigation_world.observatory.store import ObservatoryStore


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


class SchedulerPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    max_workers: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=1, ge=1)
    force: bool = False
    pools: set[ScenarioPool] = Field(
        default_factory=lambda: {
            ScenarioPool.ANCHOR,
            ScenarioPool.ROTATION,
            ScenarioPool.SEQUESTERED,
        }
    )


class ExecutionJob(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: str
    experiment_id: str
    cell: LongitudinalCell
    max_attempts: int = Field(ge=1)


class JobOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    job_id: str
    cell_id: str
    status: JobStatus
    attempts: int = Field(ge=0)
    run_id: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    started_at: datetime
    finished_at: datetime


class SchedulerReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    experiment_id: str
    planned: int = Field(ge=0)
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    skipped: int = Field(ge=0)
    outcomes: list[JobOutcome] = Field(default_factory=list)


def materialize_jobs(
    experiment: ExperimentSpec,
    cells: Iterable[LongitudinalCell],
    *,
    policy: SchedulerPolicy | None = None,
) -> list[ExecutionJob]:
    cfg = policy or SchedulerPolicy()
    items = list(cells)
    ids = [cell.cell_id for cell in items]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate cell ids supplied to scheduler")
    if set(ids) != set(experiment.cell_ids):
        missing = sorted(set(experiment.cell_ids) - set(ids))
        extra = sorted(set(ids) - set(experiment.cell_ids))
        raise ValueError(f"experiment/cell mismatch; missing={missing}, extra={extra}")

    jobs = []
    for cell in items:
        if cell.scenario.pool not in cfg.pools:
            continue
        job_id = f"JOB-{stable_hash([experiment.experiment_id, cell.cell_id])[:20].upper()}"
        jobs.append(
            ExecutionJob(
                job_id=job_id,
                experiment_id=experiment.experiment_id,
                cell=cell,
                max_attempts=cfg.max_attempts,
            )
        )
    return sorted(jobs, key=lambda job: job.job_id)


class LocalObservatoryScheduler:
    """Bounded local scheduler with retry, idempotent skipping, and serialized persistence."""

    def __init__(
        self,
        engine: ObservatoryExecutionEngine,
        *,
        store: ObservatoryStore | None = None,
    ):
        self.engine = engine
        self.store = store if store is not None else engine.store
        self._store_lock = Lock()

    def _existing_run(self, cell_id: str) -> CapabilityRun | None:
        if self.store is None:
            return None
        runs = self.store.for_cell(cell_id)
        return runs[-1] if runs else None

    def _persist(self, run: CapabilityRun) -> None:
        if self.store is None:
            return
        with self._store_lock:
            if not self.store.has_run(run.run_id):
                self.store.append(run)

    def _run_job(self, job: ExecutionJob, *, force: bool) -> JobOutcome:
        started = utc_now()
        existing = self._existing_run(job.cell.cell_id)
        if existing is not None and not force:
            return JobOutcome(
                job_id=job.job_id,
                cell_id=job.cell.cell_id,
                status=JobStatus.SKIPPED,
                attempts=0,
                run_id=existing.run_id,
                started_at=started,
                finished_at=utc_now(),
            )

        last_error: Exception | None = None
        for attempt in range(1, job.max_attempts + 1):
            try:
                run = self.engine.execute_cell(job.cell, persist=False)
                self._persist(run)
                return JobOutcome(
                    job_id=job.job_id,
                    cell_id=job.cell.cell_id,
                    status=JobStatus.SUCCEEDED,
                    attempts=attempt,
                    run_id=run.run_id,
                    started_at=started,
                    finished_at=utc_now(),
                )
            except Exception as exc:  # scheduler boundary: isolate one cell and continue
                last_error = exc

        assert last_error is not None
        return JobOutcome(
            job_id=job.job_id,
            cell_id=job.cell.cell_id,
            status=JobStatus.FAILED,
            attempts=job.max_attempts,
            error_type=type(last_error).__name__,
            error_message=str(last_error),
            started_at=started,
            finished_at=utc_now(),
        )

    def run(
        self,
        experiment: ExperimentSpec,
        cells: Iterable[LongitudinalCell],
        *,
        policy: SchedulerPolicy | None = None,
    ) -> SchedulerReport:
        cfg = policy or SchedulerPolicy()
        jobs = materialize_jobs(experiment, cells, policy=cfg)
        if not jobs:
            return SchedulerReport(
                experiment_id=experiment.experiment_id,
                planned=0,
                succeeded=0,
                failed=0,
                skipped=0,
                outcomes=[],
            )

        outcomes: list[JobOutcome] = []
        if cfg.max_workers == 1:
            outcomes = [self._run_job(job, force=cfg.force) for job in jobs]
        else:
            with ThreadPoolExecutor(max_workers=cfg.max_workers) as executor:
                futures = {
                    executor.submit(self._run_job, job, force=cfg.force): job.job_id
                    for job in jobs
                }
                for future in as_completed(futures):
                    outcomes.append(future.result())
        outcomes.sort(key=lambda item: item.job_id)

        return SchedulerReport(
            experiment_id=experiment.experiment_id,
            planned=len(jobs),
            succeeded=sum(item.status == JobStatus.SUCCEEDED for item in outcomes),
            failed=sum(item.status == JobStatus.FAILED for item in outcomes),
            skipped=sum(item.status == JobStatus.SKIPPED for item in outcomes),
            outcomes=outcomes,
        )
