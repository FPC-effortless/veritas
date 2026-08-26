from __future__ import annotations

import json
import os
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
    lease_ttl_seconds: int = Field(default=6 * 3600, ge=300)
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
            "lease_ttl_seconds": self.lease_ttl_seconds,
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
    last_scheduled_at: datetime | None = None
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
    """Filesystem cadence state with atomic checkpoint replacement and exclusive run leases.

    The lease is safe across processes that share this filesystem. Deployments whose workers do not
    share a filesystem should provide an equivalent transactional store rather than treating the JSON
    checkpoint alone as distributed coordination.
    """

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

    def _lease_path(self, cadence_id: str) -> Path:
        return self.root / f"{cadence_id}.lease"

    def claim(
        self,
        cadence_id: str,
        *,
        claimed_at: datetime,
        ttl_seconds: int,
    ) -> bool:
        if claimed_at.tzinfo is None:
            raise ValueError("cadence lease claim time must be timezone-aware")
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._lease_path(cadence_id)
        expires_at = claimed_at + timedelta(seconds=ttl_seconds)
        payload = json.dumps(
            {
                "cadence_id": cadence_id,
                "claimed_at": claimed_at.isoformat(),
                "expires_at": expires_at.isoformat(),
                "pid": os.getpid(),
            },
            sort_keys=True,
        )

        def create_exclusive() -> bool:
            try:
                descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                return False
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(payload)
            return True

        if create_exclusive():
            return True

        # Reclaim an expired lease exactly once. A malformed lease is not stolen automatically.
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_expiry = datetime.fromisoformat(str(existing["expires_at"]))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False
        if existing_expiry.tzinfo is None or existing_expiry > claimed_at:
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        return create_exclusive()

    def release(self, cadence_id: str) -> None:
        try:
            self._lease_path(cadence_id).unlink()
        except FileNotFoundError:
            pass


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
            next_due_at=first_due,
            reason="initial observation is due" if due else "cadence start time has not arrived",
        )

    if policy.catch_up:
        # Preserve scheduled boundaries. Each successful invocation advances one missed interval,
        # allowing repeated scheduler invocations to drain a backlog without collapsing it into one
        # present-time observation.
        anchor = checkpoint.last_scheduled_at or checkpoint.last_completed_at
        next_due = anchor + interval
        reason_due = "scheduled interval due (catch-up enabled)"
    else:
        # No backlog semantics: schedule relative to actual completion time.
        next_due = checkpoint.last_completed_at + interval
        reason_due = "interval elapsed"
    due = current >= next_due
    return CadenceDecision(
        cadence_id=policy.cadence_id,
        due=due,
        now=current,
        next_due_at=next_due,
        reason=reason_due if due else "interval has not elapsed",
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

        if not self.store.claim(
            self.policy.cadence_id,
            claimed_at=current,
            ttl_seconds=self.policy.lease_ttl_seconds,
        ):
            return CadenceRunResult(
                decision=decision.model_copy(
                    update={
                        "due": False,
                        "reason": "cadence run already claimed by another worker",
                    }
                )
            )

        started = current
        scheduled_at = (
            decision.next_due_at
            if self.policy.catch_up and decision.due and not force
            else started
        )
        self.store.save(checkpoint.model_copy(update={"last_started_at": started}))
        snapshot = scheduled_at.replace(microsecond=0).isoformat()
        try:
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
                    last_scheduled_at=scheduled_at,
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
        finally:
            self.store.release(self.policy.cadence_id)
