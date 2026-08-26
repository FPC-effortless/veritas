from __future__ import annotations

import gc
import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from investigation_world.companyworld.dynamic_distribution import (
    DynamicCompanyWorldConfig,
    compile_dynamic_scenarios,
)
from investigation_world.companyworld.dynamic_reference import run_dynamic_public_reference
from investigation_world.companyworld.dynamic_runtime import DynamicCompanyWorldRuntime
from investigation_world.companyworld.interactive_models import OperationalAction, OperationalActionType
from investigation_world.companyworld.sequential_reference import solve_sequential_public
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


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": round(mean(values), 6),
        "min": round(min(values), 6),
        "max": round(max(values), 6),
    }


def _public_hash(scenarios) -> str:
    digest = hashlib.sha256()
    for scenario in scenarios:
        encoded = json.dumps(
            scenario.public_payload(),
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)
    return digest.hexdigest()


def _remediation(case_payload: dict):
    _, plan = solve_sequential_public(case_payload["sequential"])
    return next(
        step.action
        for step in plan
        if step.kind == "action"
        and step.action is not None
        and step.action.action_type not in _GENERIC_ACTIONS
    )


def _policy(case_payload: dict, action_type: OperationalActionType) -> dict:
    return next(
        item
        for item in case_payload["sequential"]["task"]["action_policies"]
        if item["action_type"] == action_type.value
    )


def _open_action(case_payload: dict) -> OperationalAction:
    task = case_payload["sequential"]["task"]
    return OperationalAction(
        action_type=OperationalActionType.OPEN_CONTROL_CASE,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
    )


def _compensate_action(case_payload: dict) -> OperationalAction:
    task = case_payload["sequential"]["task"]
    return OperationalAction(
        action_type=OperationalActionType.COMPENSATE_LAST_ACTION,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
    )


def validate_dynamic_companyworld(
    root: str | Path,
    *,
    per_family: int = 200,
    cases_per_scenario: int = 3,
    seed: int = 0,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    config = DynamicCompanyWorldConfig(
        per_family=per_family,
        cases_per_scenario=cases_per_scenario,
        seed=seed,
    )
    scenarios = compile_dynamic_scenarios(root, config=config)

    reference_rewards: list[float] = []
    lazy_rewards: list[float] = []
    task_families: Counter[str] = Counter()
    resource_counts: Counter[str] = Counter()
    leakage_count = 0
    reference_deadline_misses = 0
    reference_resource_conflicts = 0
    denied_approval_cases = 0
    denied_approval_recovery_failures = 0
    outage_checks = 0
    outage_failures = 0
    recovery_checks = 0
    recovery_failures = 0
    contention_checks = 0
    contention_failures = 0
    irreversible_checks = 0
    irreversible_failures = 0
    lazy_coupled_consequence_failures = 0

    private_keys = {
        '"oracle"',
        '"approval_outcome"',
        '"failure_windows"',
        '"coupled_deadline_threshold"',
        '"coupled_deadline_penalty"',
    }

    for scenario in scenarios:
        payload = scenario.public_payload()
        serialized = json.dumps(payload, sort_keys=True, default=str)
        if any(key in serialized for key in private_keys):
            leakage_count += 1
        for case in scenario.cases:
            task_families[case.sequential.interactive.investigation.task.task_type] += 1
            resource_counts[case.shared_resource] += 1

        runtime = DynamicCompanyWorldRuntime(scenario)
        _, reference = run_dynamic_public_reference(runtime, payload)
        reference_rewards.append(reference.overall_reward)
        reference_deadline_misses += reference.deadline_misses
        reference_resource_conflicts += reference.resource_conflicts

        oracle_by_case = {item.case_id: item for item in scenario.oracle.case_oracles}
        result_by_case = {item.case_id: item for item in reference.case_results}
        for case in scenario.cases:
            oracle = oracle_by_case[case.case_id]
            if oracle.approval_outcome == "DENIED" and case.sequential.oracle.approval_required:
                denied_approval_cases += 1
                if result_by_case[case.case_id].sequential.overall_reward < 0.999999:
                    denied_approval_recovery_failures += 1

        lazy = DynamicCompanyWorldRuntime(scenario)
        for _ in range(scenario.task.max_ticks):
            lazy.advance(1)
        lazy_score = lazy.submit({})
        lazy_rewards.append(lazy_score.overall_reward)
        if not lazy_score.coupled_consequence_applied:
            lazy_coupled_consequence_failures += 1

        # Every scenario carries a hidden transient failure; verify it is observable at
        # the scheduled tick and that the same system recovers after the window.
        first_oracle = next(
            (item for item in scenario.oracle.case_oracles if item.failure_windows),
            None,
        )
        if first_oracle is not None:
            outage_checks += 1
            window = first_oracle.failure_windows[0]
            outage = DynamicCompanyWorldRuntime(scenario)
            if window.start_tick:
                outage.advance(window.start_tick)
            case = next(item for item in scenario.cases if item.case_id == first_oracle.case_id)
            target = case.sequential.task.target_object_id
            observed = outage.search_system(first_oracle.case_id, window.system, target)
            failure_observed = (not observed.ok) or observed.degraded
            if not failure_observed:
                outage_failures += 1
            recovery_tick = window.end_tick + 1
            if recovery_tick <= scenario.task.max_ticks:
                if outage.tick < recovery_tick:
                    outage.advance(recovery_tick - outage.tick)
                recovered = outage.search_system(first_oracle.case_id, window.system, target)
                recovery_checks += 1
                if not recovered.ok or recovered.degraded:
                    recovery_failures += 1

        # Verify shared resource capacity with two concurrent same-resource remediations.
        by_resource: dict[str, list[dict]] = {}
        for case_payload in payload["cases"]:
            by_resource.setdefault(case_payload["shared_resource"], []).append(case_payload)
        pair = next((items[:2] for items in by_resource.values() if len(items) >= 2), None)
        if pair is not None:
            contention_checks += 1
            contention = DynamicCompanyWorldRuntime(scenario)
            prepared = []
            for case_payload in pair:
                case_id = case_payload["case_id"]
                remediation = _remediation(case_payload)
                policy = _policy(case_payload, remediation.action_type)
                contention.act(case_id, _open_action(case_payload))
                current_role = contention.case_status(case_id)["actor_role"]
                if current_role not in policy.get("allowed_roles", []):
                    contention.handoff(case_id, sorted(policy["allowed_roles"])[0])
                prepared.append((case_id, remediation))
            first_execution = contention.act(*prepared[0])
            second_execution = contention.act(*prepared[1])
            if not first_execution.applied or second_execution.applied:
                contention_failures += 1

        irreversible_case = next(
            (case_payload for case_payload in payload["cases"] if case_payload["irreversible_remediation"]),
            None,
        )
        if irreversible_case is not None:
            irreversible_checks += 1
            irreversible = DynamicCompanyWorldRuntime(scenario)
            case_id = irreversible_case["case_id"]
            remediation = _remediation(irreversible_case)
            policy = _policy(irreversible_case, remediation.action_type)
            irreversible.act(case_id, _open_action(irreversible_case))
            current_role = irreversible.case_status(case_id)["actor_role"]
            if current_role not in policy.get("allowed_roles", []):
                irreversible.handoff(case_id, sorted(policy["allowed_roles"])[0])
            applied = irreversible.act(case_id, remediation)
            compensated = irreversible.act(case_id, _compensate_action(irreversible_case))
            if not applied.applied or compensated.applied:
                irreversible_failures += 1

    first_hash = _public_hash(scenarios)
    scenario_count = len(scenarios)
    case_count = sum(len(scenario.cases) for scenario in scenarios)
    del scenarios
    gc.collect()

    second_hash = first_hash
    if verify_determinism:
        regenerated = compile_dynamic_scenarios(root, config=config)
        second_hash = _public_hash(regenerated)
        del regenerated
        gc.collect()

    invariants = {
        "scenarios_present": scenario_count > 0,
        "public_private_boundary": leakage_count == 0,
        "reference_policy_perfect": bool(reference_rewards) and min(reference_rewards) == 1.0,
        "reference_meets_deadlines": reference_deadline_misses == 0,
        "reference_avoids_resource_conflicts": reference_resource_conflicts == 0,
        "denied_approvals_recovered": denied_approval_recovery_failures == 0,
        "transient_failures_observable": outage_failures == 0,
        "failed_systems_recover": recovery_failures == 0,
        "shared_resource_contention_enforced": contention_failures == 0,
        "irreversible_effects_cannot_be_compensated": irreversible_failures == 0,
        "lazy_policy_bounded": bool(lazy_rewards) and max(lazy_rewards) <= 0.25,
        "missed_deadlines_create_coupled_consequences": lazy_coupled_consequence_failures == 0,
        "deterministic_compilation": first_hash == second_hash,
    }

    return {
        "passed": all(invariants.values()),
        "scenarios": scenario_count,
        "cases": case_count,
        "task_families": dict(sorted(task_families.items())),
        "resources": dict(sorted(resource_counts.items())),
        "reference_reward": _stats(reference_rewards),
        "lazy_reward": _stats(lazy_rewards),
        "reference_deadline_misses": reference_deadline_misses,
        "reference_resource_conflicts": reference_resource_conflicts,
        "denied_approval_cases": denied_approval_cases,
        "denied_approval_recovery_failures": denied_approval_recovery_failures,
        "outage_checks": outage_checks,
        "outage_failures": outage_failures,
        "recovery_checks": recovery_checks,
        "recovery_failures": recovery_failures,
        "contention_checks": contention_checks,
        "contention_failures": contention_failures,
        "irreversible_checks": irreversible_checks,
        "irreversible_failures": irreversible_failures,
        "lazy_coupled_consequence_failures": lazy_coupled_consequence_failures,
        "leakage_count": leakage_count,
        "public_sha256": first_hash,
        "deterministic_sha256": second_hash,
        "invariants": invariants,
    }


def write_dynamic_companyworld_report(
    root: str | Path,
    output: str | Path,
    *,
    per_family: int = 200,
    cases_per_scenario: int = 3,
    seed: int = 0,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    report = validate_dynamic_companyworld(
        root,
        per_family=per_family,
        cases_per_scenario=cases_per_scenario,
        seed=seed,
        verify_determinism=verify_determinism,
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    return report
