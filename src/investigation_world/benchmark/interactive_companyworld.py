from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any

from investigation_world.companyworld.interactive_distribution import (
    InteractiveCompanyWorldConfig,
    compile_interactive_distribution,
)
from investigation_world.companyworld.interactive_models import OperationalAction
from investigation_world.companyworld.interactive_reference import solve_interactive_public
from investigation_world.companyworld.interactive_runtime import InteractiveCompanyWorldRuntime
from investigation_world.core.models import InvestigationResult


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


def validate_interactive_companyworld(
    root: str | Path,
    *,
    per_family: int = 200,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    config = InteractiveCompanyWorldConfig(per_family=per_family)
    episodes = compile_interactive_distribution(root, config=config)

    reference_rewards: list[float] = []
    investigation_only_rewards: list[float] = []
    blind_action_rewards: list[float] = []
    leakage_count = 0
    unauthorized_attempt_cases = 0
    unauthorized_applied_count = 0
    evidence_mutation_count = 0
    expected_actions: Counter[str] = Counter()
    actor_roles: Counter[str] = Counter()
    task_families: Counter[str] = Counter()

    private_keys = {
        '"oracle"',
        '"expected_action_type"',
        '"expected_action_parameters"',
        '"outcome_conditions"',
    }

    for episode in episodes:
        payload = episode.public_payload()
        serialized = json.dumps(payload, sort_keys=True, default=str)
        if any(key in serialized for key in private_keys):
            leakage_count += 1

        task_families[episode.investigation.task.task_type] += 1
        actor_roles[episode.task.actor_role] += 1
        expected_actions[episode.oracle.expected_action_type.value] += 1

        result, action = solve_interactive_public(payload)
        runtime = InteractiveCompanyWorldRuntime(episode)
        before_records = [item.model_dump(mode="json") for item in episode.investigation.records]
        execution = runtime.act(action)
        score = runtime.submit(result)
        after_records = [item.model_dump(mode="json") for item in episode.investigation.records]
        if before_records != after_records:
            evidence_mutation_count += 1
        if not execution.applied:
            reference_rewards.append(0.0)
        else:
            reference_rewards.append(score.overall_reward)

        investigate_only = InteractiveCompanyWorldRuntime(episode)
        investigation_only_rewards.append(investigate_only.submit(result).overall_reward)

        blind_runtime = InteractiveCompanyWorldRuntime(episode)
        first_policy = episode.task.action_policies[0]
        blind_action = OperationalAction(
            action_type=first_policy.action_type,
            target_object_type=episode.task.target_object_type,
            target_object_id=episode.task.target_object_id,
            parameters={},
        )
        blind_runtime.act(blind_action)
        blind_action_rewards.append(
            blind_runtime.submit(InvestigationResult()).overall_reward
        )

        unauthorized_policy = next(
            (
                policy
                for policy in episode.task.action_policies
                if episode.task.actor_role not in policy.allowed_roles
            ),
            None,
        )
        if unauthorized_policy is not None:
            unauthorized_attempt_cases += 1
            unauthorized_runtime = InteractiveCompanyWorldRuntime(episode)
            unauthorized_action = OperationalAction(
                action_type=unauthorized_policy.action_type,
                target_object_type=episode.task.target_object_type,
                target_object_id=episode.task.target_object_id,
                parameters={
                    effect.parameter_name: 0
                    for effect in unauthorized_policy.effects
                    if effect.parameter_name is not None
                },
            )
            unauthorized_execution = unauthorized_runtime.act(unauthorized_action)
            if unauthorized_execution.applied:
                unauthorized_applied_count += 1

    first_hash = _public_hash(episodes)
    second_hash = first_hash
    if verify_determinism:
        second_hash = _public_hash(
            compile_interactive_distribution(root, config=config)
        )

    invariants = {
        "episodes_present": bool(episodes),
        "public_private_boundary": leakage_count == 0,
        "reference_policy_perfect": bool(reference_rewards) and min(reference_rewards) == 1.0,
        "investigation_only_bounded": bool(investigation_only_rewards)
        and max(investigation_only_rewards) <= 0.35,
        "blind_action_bounded": bool(blind_action_rewards)
        and max(blind_action_rewards) <= 0.20,
        "unauthorized_actions_never_apply": unauthorized_applied_count == 0,
        "evidence_snapshot_immutable": evidence_mutation_count == 0,
        "deterministic_compilation": first_hash == second_hash,
    }

    return {
        "passed": all(invariants.values()),
        "episodes": len(episodes),
        "task_families": dict(sorted(task_families.items())),
        "actor_roles": dict(sorted(actor_roles.items())),
        "expected_actions": dict(sorted(expected_actions.items())),
        "reference_reward": _stats(reference_rewards),
        "investigation_only_reward": _stats(investigation_only_rewards),
        "blind_action_reward": _stats(blind_action_rewards),
        "leakage_count": leakage_count,
        "unauthorized_attempt_cases": unauthorized_attempt_cases,
        "unauthorized_applied_count": unauthorized_applied_count,
        "evidence_mutation_count": evidence_mutation_count,
        "public_sha256": first_hash,
        "deterministic_sha256": second_hash,
        "invariants": invariants,
    }


def write_interactive_companyworld_report(
    root: str | Path,
    output: str | Path,
    *,
    per_family: int = 200,
    verify_determinism: bool = True,
) -> dict[str, Any]:
    report = validate_interactive_companyworld(
        root,
        per_family=per_family,
        verify_determinism=verify_determinism,
    )
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    return report
