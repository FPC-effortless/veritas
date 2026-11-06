"""Conservative, read-only manager brief from Research Lab OS controller state.

This projects the durable queue; it neither executes jobs nor certifies liveness,
scientific quality, independent sessions or remote compute availability.
"""

from __future__ import annotations

from collections import Counter, defaultdict


def _next_action(phase, round_row, tasks):
    """Give an actionable, bounded next step without granting authority."""
    if phase == "budget_exhausted":
        return "STOP: budget envelope exhausted; seek a newly authorized amendment"
    if phase == "blocked":
        return "REPAIR: investigate recorded blocker; never auto-recover unknown execution"
    if phase == "complete":
        return "STOP: preserve results; new scientific work requires a new admitted lane"
    if not round_row:
        return "DISPATCH: prepare the preregistered first round; no execution implied"
    if not tasks:
        return "DISPATCH: register the frozen round; no execution implied"
    states = {task["status"] for task in tasks}
    if states & {"failed", "lost", "blocked"}:
        return "STOP: investigate failed/lost tasks; confirm process stopped before recovery"
    if "running" in states:
        return "OBSERVE: inspect current lease and actual worker/process receipts"
    pending = [task for task in tasks if task["status"] != "succeeded"]
    if pending:
        roles = {task["role"] for task in pending}
        if "experiment" in roles:
            return "EXECUTE: admit queued primary work only on proven available resources"
        if "replication" in roles:
            return "REPLICATE: use a genuine independent principal and frozen inputs"
        if "review" in roles:
            return "REVIEW: obtain a fresh independent exact-evidence review receipt"
        if "director" in roles:
            return "DIRECT: use only admitted profiles; require validated proposal output"
        return "EXECUTE: inspect dependencies and role-specific pending work"
    return "DISPATCH: synthesize reviewed evidence and select the admitted next step"


def manager_brief(state):
    """Generate an audit-friendly local coordination snapshot from Controller.status().

    No raw task results, artifacts, secrets, error strings or scientific verdicts are
    copied into the brief. A recent heartbeat is not verified process liveness.
    """
    tasks = state.get("tasks", [])
    task_counts = Counter(task["status"] for task in tasks)
    by_protocol = defaultdict(list)
    for task in tasks:
        by_protocol[task["protocol"]].append(task)

    rounds = defaultdict(list)
    for row in state.get("autonomous_rounds", []):
        rounds[row["lane"]].append(row)

    lanes = []
    for lane in sorted(state.get("autonomous_lanes", []), key=lambda x: x["id"]):
        latest = max(rounds[lane["id"]], key=lambda x: x["n"], default=None)
        current_tasks = by_protocol[latest["protocol"]] if latest else []
        counts = Counter(task["status"] for task in current_tasks)
        lanes.append({
            "id": lane["id"],
            "phase": lane["phase"],
            "round": latest["n"] if latest else None,
            "protocol": latest["protocol"] if latest else None,
            "tasks": {key: counts[key] for key in sorted(counts)},
            "next_action": _next_action(lane["phase"], latest, current_tasks),
        })

    budgets = []
    for program in sorted(state.get("programs", []), key=lambda x: x["id"]):
        remaining_seconds = max(
            0, program["cap_seconds"] - program["charged_seconds"] - program["reserved_seconds"]
        )
        remaining_micro = max(
            0, program["cap_microusd"] - program["charged_microusd"]
            - program["reserved_microusd"]
        )
        budgets.append({
            "id": program["id"],
            "remaining_declared_slot_seconds": remaining_seconds,
            "remaining_declared_microusd": remaining_micro,
            "paid_execution_authorized": bool(program["allow_paid"]),
        })

    heartbeat_counts = Counter(w["liveness"] for w in state.get("workers", []))
    return {
        "schema": "research_lab.manager_brief.v1",
        "authority": "READ_ONLY; NOT_AN_EXECUTION_OR_SCIENTIFIC_APPROVAL",
        "hosting": "UNVERIFIED_FROM_CONTROLLER_STATE",
        "model_fits": "UNKNOWN_FROM_TASK_RECORDS",
        "task_counts": {key: task_counts[key] for key in sorted(task_counts)},
        "registered_worker_count": len(state.get("workers", [])),
        "worker_observations": {key: heartbeat_counts[key] for key in sorted(heartbeat_counts)},
        "program_budgets": budgets,
        "lanes": lanes,
        "coordination_policy": (
            "One accountable lead per outcome; fan out only proven independent work "
            "with disjoint write scope and frozen acceptance checks. Reuse the owning "
            "builder for bounded repair; demand independent scientific review. "
            "Do not create agents or experiments from this read-only brief."
        ),
    }
