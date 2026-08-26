from __future__ import annotations

from typing import Any

from investigation_world.foundry.models import CounterfactualBranch, StateSnapshot, stable_hash


def make_snapshot(trace_id: str, step: int, state: dict[str, Any], *, retain_payload: bool = False) -> StateSnapshot:
    return StateSnapshot(
        trace_id=trace_id,
        step=step,
        state_hash=stable_hash(state),
        state_payload=state if retain_payload else None,
    )


def branch_from_snapshot(snapshot: StateSnapshot, alternate_action: dict[str, Any]) -> CounterfactualBranch:
    branch_id = f"CF-{stable_hash([snapshot.trace_id, snapshot.step, snapshot.state_hash, alternate_action])[:16].upper()}"
    return CounterfactualBranch(
        branch_id=branch_id,
        parent_trace_id=snapshot.trace_id,
        branch_step=snapshot.step,
        snapshot_hash=snapshot.state_hash,
        alternate_action=alternate_action,
    )
