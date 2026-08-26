from __future__ import annotations

from collections import Counter
from typing import Any, Iterable

from investigation_world.foundry.models import (
    CapabilityContract,
    DifficultyVector,
    DistributionSplit,
    FoundryTaskMetadata,
)


_FAMILY_CAPABILITIES: dict[str, list[str]] = {
    "INVESTIGATE_MISSING_SHIPMENT": ["discover", "reconcile", "evidence", "verify"],
    "INVESTIGATE_DUPLICATE_INVOICE": ["discover", "reconcile", "evidence", "verify"],
    "INVESTIGATE_AUTHORITY_BREACH": ["interpret", "authority", "policy", "verify"],
    "O2C_FULFILLMENT_TIMING": ["discover", "temporal", "reconcile", "verify"],
    "P2P_RECONCILIATION": ["discover", "policy", "reconcile", "verify"],
    "CUSTOMER_SETTLEMENT_RECONSTRUCTION": ["discover", "finance", "reconcile", "verify"],
    "PAYMENT_BLOCK_RECOVERY": ["plan", "recover", "temporal", "verify"],
    "INCIDENT_SLA_INVESTIGATION": ["discover", "temporal", "policy", "verify"],
    "SAFETY_CORRECTIVE_FOLLOWUP": ["interpret", "policy", "authority", "verify"],
    "CROSS_SYSTEM_CASH_CYCLE": ["discover", "temporal", "finance", "reconcile", "verify"],
    "LEDGER_POSTING_RECONSTRUCTION": ["discover", "accounting", "reconcile", "verify"],
}


def companyworld_capability_contract() -> CapabilityContract:
    return CapabilityContract(
        capability_id="companyworld-enterprise-control",
        objective=(
            "Given partially observable enterprise state, discover and reconcile evidence, plan and "
            "execute authorized actions, recover from failures, verify resulting state, and communicate "
            "a defensible outcome under tool, time, budget, and authority constraints."
        ),
        subcapabilities=[
            "discover", "interpret", "plan", "act", "recover", "verify", "communicate",
            "evidence", "temporal", "reconcile", "authority", "policy", "finance", "accounting",
        ],
        success_conditions=[
            "final state satisfies the private outcome contract",
            "claims are supported by public evidence",
            "required authority and process invariants hold",
        ],
        failure_conditions=[
            "incorrect or unsupported outcome", "unauthorized state mutation",
            "hard budget or process invariant violation",
        ],
        hard_invariants=[
            "no private oracle access", "no unauthorized writes", "evidence remains immutable",
        ],
        transfer_targets=[
            "unseen CompanyWorld seeds", "adversarial surface variants", "customer-specific workflows",
        ],
    )


def _public_payload(episode: Any) -> dict[str, Any]:
    public = getattr(episode, "public_payload", None)
    if not callable(public):
        raise TypeError("CompanyWorld episode must expose public_payload()")
    value = public()
    if not isinstance(value, dict):
        raise TypeError("public_payload() must return a dict")
    return value


def _task_payload(episode: Any, public: dict[str, Any]) -> dict[str, Any]:
    raw = public.get("task")
    if isinstance(raw, dict):
        return raw
    task = getattr(episode, "task", None)
    if task is not None and hasattr(task, "model_dump"):
        return task.model_dump(mode="json")
    return {}


def _world_id(episode: Any, public: dict[str, Any], task: dict[str, Any]) -> str:
    return str(
        task.get("world_id")
        or public.get("world_id")
        or getattr(episode, "world_id", "")
        or "companyworld:unknown"
    )


def infer_companyworld_difficulty(episode: Any) -> DifficultyVector:
    public = _public_payload(episode)
    task = _task_payload(episode, public)
    records = public.get("records") if isinstance(public.get("records"), list) else []
    entity_ids: set[str] = set()
    systems: set[str] = set()
    distractors = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        object_id = record.get("object_id")
        if object_id:
            entity_ids.add(str(object_id))
        system = record.get("system")
        if system:
            systems.add(str(system))
        if "distractor" in str(record.get("record_type", "")).casefold():
            distractors += 1

    permitted = task.get("permitted_systems")
    if isinstance(permitted, list):
        systems.update(str(item) for item in permitted)
    available_actions = task.get("available_actions")
    action_count = len(available_actions) if isinstance(available_actions, list) else 0
    max_actions = task.get("max_actions")
    max_ticks = task.get("max_ticks")
    constraints = task.get("constraints") if isinstance(task.get("constraints"), dict) else {}

    stochasticity = 0.0
    if constraints.get("approval_outcomes_are_stochastic"):
        stochasticity += 0.35
    if constraints.get("system_failures_are_stochastic"):
        stochasticity += 0.35
    if constraints.get("shared_resources_have_capacity"):
        stochasticity += 0.15
    stochasticity = min(1.0, stochasticity)

    record_system_counts = Counter(
        str(record.get("system")) for record in records if isinstance(record, dict) and record.get("system")
    )
    cross_system_pressure = max(0, len(record_system_counts) - 1)
    steps = max(
        1,
        action_count,
        int(max_actions) if isinstance(max_actions, int) else 0,
        int(max_ticks) if isinstance(max_ticks, int) else 0,
    )
    dependency_depth = max(1, min(12, cross_system_pressure + max(1, steps // 2)))

    budget = constraints.get("budget")
    budget_ratio = 1.0
    if isinstance(budget, (int, float)) and budget > 0:
        budget_ratio = max(0.05, min(2.0, float(budget) / 100.0))

    return DifficultyVector(
        entities=max(1, len(entity_ids)),
        tools=max(1, len(systems)),
        steps=steps,
        distractors=distractors,
        dependency_depth=dependency_depth,
        budget_ratio=budget_ratio,
        stochasticity=stochasticity,
    )


def companyworld_task_metadata(
    episode: Any,
    *,
    split: DistributionSplit,
    taskset_version: str,
    harness_version: str,
    runtime_version: str,
    seed: int,
) -> FoundryTaskMetadata:
    public = _public_payload(episode)
    task = _task_payload(episode, public)
    local_task_id = str(task.get("task_id") or task.get("scenario_id") or getattr(episode, "episode_id", ""))
    if not local_task_id:
        raise ValueError("CompanyWorld task has no public task identifier")
    world_id = _world_id(episode, public, task)
    task_id = f"{world_id}::{local_task_id}"
    family = str(task.get("task_type") or task.get("base_task_type") or "UNKNOWN")
    tags = list(_FAMILY_CAPABILITIES.get(family, ["discover", "verify"]))
    if task.get("available_actions"):
        tags.extend(["plan", "act"])
    constraints = task.get("constraints") if isinstance(task.get("constraints"), dict) else {}
    if constraints.get("approval_outcomes_are_stochastic") or constraints.get("system_failures_are_stochastic"):
        tags.extend(["recover", "uncertainty"])
    return FoundryTaskMetadata(
        task_id=task_id,
        split=split,
        capability_tags=list(dict.fromkeys(tags)),
        difficulty=infer_companyworld_difficulty(episode),
        seed=seed,
        taskset_version=taskset_version,
        harness_version=harness_version,
        runtime_version=runtime_version,
        generator_parameters={
            "companyworld_family": family,
            "companyworld_world_id": world_id,
            "companyworld_local_task_id": local_task_id,
        },
    )


def adapt_companyworld_tasks(
    episodes: Iterable[Any],
    *,
    split: DistributionSplit,
    taskset_version: str,
    harness_version: str,
    runtime_version: str,
    seed_start: int,
) -> list[FoundryTaskMetadata]:
    return [
        companyworld_task_metadata(
            episode,
            split=split,
            taskset_version=taskset_version,
            harness_version=harness_version,
            runtime_version=runtime_version,
            seed=seed_start + index,
        )
        for index, episode in enumerate(episodes)
    ]
