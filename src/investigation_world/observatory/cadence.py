from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.cycles import ObservationCycleReport


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CadencePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    interval_seconds: int = Field(ge=3600)
    start_at: datetime | None = None
    catch_up: bool = False
    cadence_id: str = ""

    @model_validator(mode="after")
    def validate_id(self) -> "CadencePolicy":
        if self.start_at is not None and self.start_at.tzinfo is None:
            raise ValueError("cadence start_at must be timezone-aware")
        payload = {
            "name": self.name,
            "interval_seconds": self.interval_seconds,
            "start_at": self.start_at.isoformat() if self.start_at is not None else None,
            "catch_up": self.catch_up,
        }
        expected = f"CAD-{stable_hash(payload)[:20].upper()}"
        if self.cadence_id and self.cadence_id != expected:
            raise ValueError("cadence_id does not match cadence policy")
        object.__setattr__(self, "cadence_id", expected)
        return self


class CadenceCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cadence_id: str
    last_started_at: datetime | None = None
    last_completed_at: datetime | None = None
    last_failed_at: datetime | None = None
    last_cycle_id: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)


class CadenceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    cadence_id: str
    due: bool
    now: datetime
    next_due_at: datetime
    reason: str


class CadenceRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decision: CadenceDecision
    cycle: ObservationCycleReport | None = None


class CadenceStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.path = self.root / "cadence.json"

    def load(self, cadence_id: str) -> CadenceCheckpoint:
        if not self.path.exists():
            return CadenceCheckpoint(cadence_id=cadence_id)
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        raw = payload.get(cadence_id)
        if raw is None:
            return CadenceCheckpoint(cadence_id=cadence_id)
        return CadenceCheckpoint.model_validate(raw)

    def save(self, checkpoint: CadenceCheckpoint) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload: dict[str, object] = {}
        if self.path.exists():
            existing = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                payload.update(existing)
        payload[checkpoint.cadence_id] = checkpoint.model_dump(mode="json")
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str), encoding="utf-8")
        temp.replace(self.path)


def cadence_decision(
    policy: CadencePolicy,
    checkpoint: CadenceCheckpoint,
    *,
    now: datetime | None = None,
) -> CadenceDecision:
    current = now or utc_now()
    if current.tzinfo is None:
        raise ValueError("cadence evaluation requires timezone-aware datetime")
    interval = timedelta(seconds=policy.interval_seconds)

    if checkpoint.last_completed_at is None:
        first_due = policy.start_at or current
        due = current >= first_due
        return CadenceDecision(
            cadence_id=policy.cadence_id,
            due=due,
            now=current,
            next_due_at=first_due if not due else current,
            reason="initial observation is due" if due else "cadence start time has not arrived",
        )

    next_due = checkpoint.last_completed_at + interval
    due = current >= next_due
    return CadenceDecision(
        cadence_id=policy.cadence_id,
        due=due,
        now=current,
        next_due_at=next_due,
        reason="interval elapsed" if due else "interval has not elapsed",
    )


class CadencedObservationRunner:
    """Resumable cadence gate around one observation-cycle callable."""

    def __init__(
        self,
        policy: CadencePolicy,
        store: CadenceStore,
        run_cycle: Callable[[str], ObservationCycleReport],
    ):
        self.policy = policy
        self.store = store
        self.run_cycle = run_cycle

    def run_if_due(
        self,
        *,
        now: datetime | None = None,
        force: bool = False,
    ) -> CadenceRunResult:
        current = now or utc_now()
        checkpoint = self.store.load(self.policy.cadence_id)
        decision = cadence_decision(self.policy, checkpoint, now=current)
        if not decision.due and not force:
            return CadenceRunResult(decision=decision)

        started = current
        self.store.save(checkpoint.model_copy(update={"last_started_at": started}))
        snapshot = started.replace(microsecond=0).isoformat()
        try:
            cycle = self.run_cycle(snapshot)
        except Exception:
            failed = self.store.load(self.policy.cadence_id)
            self.store.save(
                failed.model_copy(
                    update={
                        "last_failed_at": utc_now(),
                        "consecutive_failures": failed.consecutive_failures + 1,
                    }
                )
            )
            raise

        completed = utc_now()
        self.store.save(
            CadenceCheckpoint(
                cadence_id=self.policy.cadence_id,
                last_started_at=started,
                last_completed_at=completed,
                last_failed_at=checkpoint.last_failed_at,
                last_cycle_id=cycle.cycle_id,
                consecutive_failures=0,
            )
        )
        return CadenceRunResult(
            decision=decision.model_copy(
                update={
                    "due": True,
                    "reason": "forced" if force and not decision.due else decision.reason,
                }
            ),
            cycle=cycle,
        )
