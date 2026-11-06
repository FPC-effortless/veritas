from __future__ import annotations

from datetime import datetime, timedelta, timezone

from investigation_world.observatory.cadence import (
    CadenceCheckpoint,
    CadencePolicy,
    CadenceStore,
    cadence_decision,
)


def test_catch_up_uses_scheduled_boundary_instead_of_completion_drift():
    t0 = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    interval = 7 * 24 * 3600
    policy = CadencePolicy(
        name="weekly",
        interval_seconds=interval,
        start_at=t0,
        catch_up=True,
    )
    checkpoint = CadenceCheckpoint(
        cadence_id=policy.cadence_id,
        last_scheduled_at=t0,
        last_completed_at=t0 + timedelta(hours=2),
    )

    decision = cadence_decision(policy, checkpoint, now=t0 + timedelta(days=21))

    assert decision.due is True
    assert decision.next_due_at == t0 + timedelta(days=7)
    assert "catch-up" in decision.reason


def test_no_catch_up_schedules_from_actual_completion():
    t0 = datetime(2026, 8, 1, 8, 0, tzinfo=timezone.utc)
    interval = 7 * 24 * 3600
    policy = CadencePolicy(name="weekly", interval_seconds=interval, catch_up=False)
    completed = t0 + timedelta(hours=2)
    checkpoint = CadenceCheckpoint(
        cadence_id=policy.cadence_id,
        last_scheduled_at=t0,
        last_completed_at=completed,
    )

    decision = cadence_decision(policy, checkpoint, now=t0 + timedelta(days=21))

    assert decision.next_due_at == completed + timedelta(days=7)


def test_cadence_store_exclusive_lease_blocks_second_worker(tmp_path):
    store = CadenceStore(tmp_path)
    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)

    assert store.claim("CAD-TEST", claimed_at=now, ttl_seconds=3600) is True
    assert store.claim("CAD-TEST", claimed_at=now, ttl_seconds=3600) is False
    store.release("CAD-TEST")
    assert store.claim("CAD-TEST", claimed_at=now, ttl_seconds=3600) is True
    store.release("CAD-TEST")


def test_expired_cadence_lease_can_be_reclaimed(tmp_path):
    store = CadenceStore(tmp_path)
    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)

    assert store.claim("CAD-TEST", claimed_at=now, ttl_seconds=300) is True
    assert store.claim(
        "CAD-TEST",
        claimed_at=now + timedelta(minutes=6),
        ttl_seconds=300,
    ) is True
    store.release("CAD-TEST")
