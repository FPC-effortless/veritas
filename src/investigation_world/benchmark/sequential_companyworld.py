from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from investigation_world.companyworld.interactive_models import OperationalAction, OperationalActionType
from investigation_world.companyworld.sequential_distribution import (
    SequentialCompanyWorldConfig,
    compile_sequential_distribution,
)
from investigation_world.companyworld.sequential_reference import solve_sequential_public
from investigation_world.companyworld.sequential_runtime import SequentialCompanyWorldRuntime
from investigation_world.core.models import InvestigationResult


_GENERIC_ACTIONS = {
    OperationalActionType.OPEN_CONTROL_CASE,
    OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
    OperationalActionType.RECONCILE_SYSTEM_STATE,
    OperationalActionType.VERIFY_CONTROL_INVARIANTS,
    OperationalActionType.CLOSE_CONTROL_CASE,
    OperationalActionType.COMPENSATE_LAST_ACTION,
    OperationalActionType.ESCALATE_CONTROL_FAILURE,
}


def _public_hash(episodes) -> str:
    payload = [episode.public_payload() for episode in episodes]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(mean(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def _run_reference(runtime: SequentialCompanyWorldRuntime, payload: dict):
    result, plan = solve_sequential_public(payload)
    applied_actions = 0
    for step in plan:
        if step.kind == "advance":
            runtime.advance(step.ticks)
            continue
        if step.action is None:
            raise ValueError("action plan step is missing its action")
        execution = runtime.act(step.action)
        if execution.applied:
            applied_actions += 1
    return result, runtime.submit(result), plan, applied_actions


def _remediation_from_plan(plan):
    return next(
        step.action
        for step in plan
        if step.kind == "action"
        and step.action is not None
        and step.action.action_type not in _GENERIC_ACTIONS
    )


def _state_map(runtime: SequentialCompanyWorldRuntime) -> dict[tuple[str, str, str], Any]:
    return {item.key(): item.value for item in runtime.state_snapshot()}


def validate_sequential_companyworld(
    root: str | Path,
    *,
    per_family: int = 200,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    config = SequentialCompanyWorldConfig(per_family=per_family)
    episodes = compile_sequential_distribution(root, config=config)

    reference_rewards: list[float] = []
    investigation_only_rewards: list[float] = []
    one_shot_rewards: list[float] = []
    action_counts: list[float] = []
    tick_counts: list[float] = []
    leakage_count = 0
    out_of_order_applied_count = 0
    approval_bypass_cases = 0
    approval_bypass_applied_count = 0
    evidence_mutation_count = 0
    compensation_cases = 0
    compensation_failures = 0
    task_families: Counter[str] = Counter()
    actor_roles: Counter[str] = Counter()
    remediation_actions: Counter[str] = Counter()

    private_keys = {
        '"oracle"',
        '"remediation_action_type"',
        '"remediation_action_parameters"',
        '"domain_outcome_conditions"',
        '"control_outcome_conditions"',
    }

    for episode in episodes:
        payload = episode.public_payload()
        serialized = json.dumps(payload, sort_keys=True, default=str)
        if any(key in serialized for key in private_keys):
            leakage_count += 1

        base_family = episode.interactive.investigation.task.task_type
        task_families[base_family] += 1
        actor_roles[episode.task.actor_role] += 1
        remediation_actions[episode.oracle.remediation_action_type.value] += 1

        before_records = [
            item.model_dump(mode="json")
            for item in episode.interactive.investigation.records
        ]
        runtime = SequentialCompanyWorldRuntime(episode)
        result, score, plan, applied_count = _run_reference(runtime, payload)
        reference_rewards.append(score.overall_reward)
        action_counts.append(float(applied_count))
        tick_counts.append(float(score.ticks_used))
        after_records = [
            item.model_dump(mode="json")
            for item in episode.interactive.investigation.records
        ]
        if before_records != after_records:
            evidence_mutation_count += 1

        investigation_only = SequentialCompanyWorldRuntime(episode)
        investigation_only_rewards.append(investigation_only.submit(result).overall_reward)

        remediation = _remediation_from_plan(plan)
        one_shot = SequentialCompanyWorldRuntime(episode)
        one_shot.act(remediation)
        one_shot_rewards.append(one_shot.submit(result).overall_reward)

        out_of_order = SequentialCompanyWorldRuntime(episode)
        execution = out_of_order.act(
            OperationalAction(
                action_type=OperationalActionType.RECONCILE_SYSTEM_STATE,
                target_object_type=episode.task.target_object_type,
                target_object_id=episode.task.target_object_id,
            )
        )
        if execution.applied:
            out_of_order_applied_count += 1

        if episode.oracle.approval_required:
            approval_bypass_cases += 1
            bypass = SequentialCompanyWorldRuntime(episode)
            bypass.act(
                OperationalAction(
                    action_type=OperationalActionType.OPEN_CONTROL_CASE,
                    target_object_type=episode.task.target_object_type,
                    target_object_id=episode.task.target_object_id,
                )
            )
            bypass_execution = bypass.act(remediation)
            if bypass_execution.applied:
                approval_bypass_applied_count += 1

        compensation_cases += 1
        recovery = SequentialCompanyWorldRuntime(episode)
        recovery_result, recovery_plan = solve_sequential_public(payload)
        pre_remediation: dict[tuple[str, str, str], Any] | None = None
        remediation_execution = None
        for step in recovery_plan:
            if step.kind == "advance":
                recovery.advance(step.ticks)
                continue
            if step.action is None:
                continue
            if step.action.action_type in {
                OperationalActionType.RECONCILE_SYSTEM_STATE,
                OperationalActionType.VERIFY_CONTROL_INVARIANTS,
                OperationalActionType.CLOSE_CONTROL_CASE,
            }:
                break
            if step.action.action_type not in _GENERIC_ACTIONS:
                pre_remediation = _state_map(recovery)
                remediation_execution = recovery.act(step.action)
                break
            recovery.act(step.action)
        if remediation_execution is None or not remediation_execution.applied:
            compensation_failures += 1
        else:
            compensation = recovery.act(
                OperationalAction(
                    action_type=OperationalActionType.COMPENSATE_LAST_ACTION,
                    target_object_type=episode.task.target_object_type,
                    target_object_id=episode.task.target_object_id,
                )
            )
            after_compensation = _state_map(recovery)
            changed_keys = {item.key() for item in remediation_execution.effects}
            restored = all(
                after_compensation.get(key) == (pre_remediation or {}).get(key)
                for key in changed_keys
            )
            if not compensation.applied or not restored:
                compensation_failures += 1

    first_hash = _public_hash(episodes)
    second_hash = first_hash
    if verify_determinism:
        second_hash = _public_hash(compile_sequential_distribution(root, config=config))

    invariants = {
        "episodes_present": bool(episodes),
        "public_private_boundary": leakage_count == 0,
        "reference_policy_perfect": bool(reference_rewards) and min(reference_rewards) == 1.0,
        "investigation_only_bounded": bool(investigation_only_rewards)
        and max(investigation_only_rewards) <= 0.25,
        "one_shot_shortcut_bounded": bool(one_shot_rewards) and max(one_shot_rewards) <= 0.25,
        "prerequisites_block_out_of_order_actions": out_of_order_applied_count == 0,
        "approval_cannot_be_bypassed": approval_bypass_applied_count == 0,
        "compensation_restores_remediation_state": compensation_failures == 0,
        "evidence_snapshot_immutable": evidence_mutation_count == 0,
        "deterministic_compilation": first_hash == second_hash,
    }

    return {
        "passed": all(invariants.values()),
        "episodes": len(episodes),
        "task_families": dict(sorted(task_families.items())),
        "actor_roles": dict(sorted(actor_roles.items())),
        "remediation_actions": dict(sorted(remediation_actions.items())),
        "reference_reward": _stats(reference_rewards),
        "investigation_only_reward": _stats(investigation_only_rewards),
        "one_shot_reward": _stats(one_shot_rewards),
        "applied_action_count": _stats(action_counts),
        "ticks_used": _stats(tick_counts),
        "leakage_count": leakage_count,
        "out_of_order_applied_count": out_of_order_applied_count,
        "approval_bypass_cases": approval_bypass_cases,
        "approval_bypass_applied_count": approval_bypass_applied_count,
        "compensation_cases": compensation_cases,
        "compensation_failures": compensation_failures,
        "evidence_mutation_count": evidence_mutation_count,
        "public_sha256": first_hash,
        "deterministic_sha256": second_hash,
        "invariants": invariants,
    }


def write_sequential_companyworld_report(
    root: str | Path,
    output: str | Path,
    *,
    per_family: int = 200,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    report = validate_sequential_companyworld(
        root,
        per_family=per_family,
        verify_determinism=verify_determinism,
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    return report
