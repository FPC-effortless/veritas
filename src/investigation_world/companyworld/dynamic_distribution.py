from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from investigation_world.companyworld.dynamic_models import (
    DynamicCaseOracle,
    DynamicCaseSpec,
    DynamicCompanyWorldScenario,
    DynamicFailureMode,
    DynamicScenarioOracle,
    DynamicScenarioTask,
    DynamicSystemFailureWindow,
)
from investigation_world.companyworld.sequential_distribution import (
    SequentialCompanyWorldConfig,
    compile_sequential_distribution,
)
from investigation_world.companyworld.sequential_models import SequentialCompanyWorldEpisode


DYNAMIC_DISTRIBUTION_VERSION = "0.1.0"


@dataclass(frozen=True)
class DynamicCompanyWorldConfig:
    per_family: int = 200
    cases_per_scenario: int = 3
    seed: int = 0
    include_legacy: bool = True
    legacy_limit: int | None = None


_RESOURCE_BY_FAMILY = {
    "INVESTIGATE_MISSING_SHIPMENT": "OPS_CONTROL",
    "INVESTIGATE_DUPLICATE_INVOICE": "AP_CONTROL",
    "INVESTIGATE_AUTHORITY_BREACH": "COMPLIANCE_CONTROL",
    "O2C_FULFILLMENT_TIMING": "OPS_CONTROL",
    "P2P_RECONCILIATION": "AP_CONTROL",
    "CUSTOMER_SETTLEMENT_RECONSTRUCTION": "AR_CONTROL",
    "PAYMENT_BLOCK_RECOVERY": "AP_CONTROL",
    "INCIDENT_SLA_INVESTIGATION": "ITSM_ONCALL",
    "SAFETY_CORRECTIVE_FOLLOWUP": "SAFETY_CONTROL",
    "CROSS_SYSTEM_CASH_CYCLE": "FINANCE_CONTROL",
    "LEDGER_POSTING_RECONSTRUCTION": "FINANCE_CONTROL",
}

_IRREVERSIBLE_FAMILIES = {
    "P2P_RECONCILIATION",
    "CUSTOMER_SETTLEMENT_RECONSTRUCTION",
    "CROSS_SYSTEM_CASH_CYCLE",
    "LEDGER_POSTING_RECONSTRUCTION",
}


def _hash_int(*parts: object) -> int:
    encoded = "|".join(str(part) for part in parts).encode()
    return int(hashlib.sha256(encoded).hexdigest()[:16], 16)


def _base_family(episode: SequentialCompanyWorldEpisode) -> str:
    return episode.interactive.investigation.task.task_type


def _resource(episode: SequentialCompanyWorldEpisode) -> str:
    family = _base_family(episode)
    try:
        return _RESOURCE_BY_FAMILY[family]
    except KeyError as exc:
        raise ValueError(f"unsupported dynamic CompanyWorld family: {family}") from exc


def _role_roster(episode: SequentialCompanyWorldEpisode) -> list[str]:
    roles = {episode.task.actor_role}
    for policy in episode.task.action_policies:
        if policy.stage == "remediation":
            roles.update(policy.allowed_roles)
    return sorted(roles)


def _case_oracle(
    case_id: str,
    episode: SequentialCompanyWorldEpisode,
    *,
    seed: int,
) -> DynamicCaseOracle:
    draw = _hash_int("dynamic", seed, case_id)
    if episode.oracle.approval_required:
        approval_outcome = "DENIED" if draw % 4 == 0 else "APPROVED"
    else:
        approval_outcome = "APPROVED"

    systems = list(episode.task.permitted_systems)
    windows: list[DynamicSystemFailureWindow] = []
    if systems:
        system = systems[draw % len(systems)]
        start_tick = (draw // 7) % 2
        duration = 1 if (draw // 11) % 5 == 0 else 0
        mode = (
            DynamicFailureMode.PARTIAL
            if (draw // 13) % 2 == 0
            else DynamicFailureMode.UNAVAILABLE
        )
        windows.append(
            DynamicSystemFailureWindow(
                system=system,
                start_tick=start_tick,
                end_tick=start_tick + duration,
                mode=mode,
            )
        )
    return DynamicCaseOracle(
        case_id=case_id,
        approval_outcome=approval_outcome,
        failure_windows=windows,
    )


def compile_dynamic_scenarios(
    root: str | Path,
    *,
    config: DynamicCompanyWorldConfig | None = None,
) -> list[DynamicCompanyWorldScenario]:
    cfg = config or DynamicCompanyWorldConfig()
    if cfg.cases_per_scenario < 2:
        raise ValueError("dynamic scenarios require at least two simultaneous cases")

    episodes = compile_sequential_distribution(
        root,
        config=SequentialCompanyWorldConfig(
            per_family=cfg.per_family,
            include_legacy=cfg.include_legacy,
            legacy_limit=cfg.legacy_limit,
        ),
    )
    episodes = sorted(
        episodes,
        key=lambda item: (
            _resource(item),
            _base_family(item),
            item.episode_id,
        ),
    )

    scenarios: list[DynamicCompanyWorldScenario] = []
    for offset in range(0, len(episodes), cfg.cases_per_scenario):
        group = episodes[offset : offset + cfg.cases_per_scenario]
        if len(group) < 2:
            break
        scenario_index = len(scenarios)
        scenario_id = f"DYN-{scenario_index:05d}"
        world_id = group[0].world_id

        cases: list[DynamicCaseSpec] = []
        case_oracles: list[DynamicCaseOracle] = []
        resources: set[str] = set()
        systems: set[str] = set()
        for position, episode in enumerate(group):
            family = _base_family(episode)
            case_id = f"{scenario_id}-C{position + 1}"
            priority = float(cfg.cases_per_scenario - position)
            deadline = 4 + position
            resource = _resource(episode)
            resources.add(resource)
            systems.update(system.value for system in episode.task.permitted_systems)
            cases.append(
                DynamicCaseSpec(
                    case_id=case_id,
                    sequential=episode,
                    deadline_tick=deadline,
                    priority_weight=priority,
                    shared_resource=resource,
                    irreversible_remediation=family in _IRREVERSIBLE_FAMILIES,
                    role_roster=_role_roster(episode),
                    late_penalty=round(0.08 + 0.02 * priority, 4),
                    metadata={
                        "base_task_type": family,
                        "dynamic_distribution_version": DYNAMIC_DISTRIBUTION_VERSION,
                    },
                )
            )
            case_oracles.append(_case_oracle(case_id, episode, seed=cfg.seed))

        scenarios.append(
            DynamicCompanyWorldScenario(
                scenario_id=scenario_id,
                world_id=world_id,
                task=DynamicScenarioTask(
                    scenario_id=scenario_id,
                    world_id=world_id,
                    objective=(
                        "Manage the concurrent operational cases to verified end states while "
                        "respecting authority, shared resources, deadlines, stochastic system "
                        "availability, and the global action/tool budget."
                    ),
                    max_ticks=6,
                    total_budget=max(100, 40 * len(cases)),
                    shared_resource_capacities={resource: 1 for resource in sorted(resources)},
                    system_failure_risk={system: 0.25 for system in sorted(systems)},
                    constraints={
                        "approval_outcomes_are_stochastic": True,
                        "system_failures_are_stochastic": True,
                        "randomness_is_seed_reproducible": True,
                        "shared_resources_have_capacity": True,
                        "deadlines_have_downstream_consequences": True,
                        "some_remediations_are_irreversible": True,
                        "multiple_actor_roles_are_available": True,
                        "private_random_draws_are_evaluator_only": True,
                    },
                    metadata={
                        "dynamic_distribution_version": DYNAMIC_DISTRIBUTION_VERSION,
                        "seed": cfg.seed,
                    },
                ),
                cases=cases,
                oracle=DynamicScenarioOracle(
                    scenario_id=scenario_id,
                    case_oracles=case_oracles,
                    coupled_deadline_threshold=2,
                    coupled_deadline_penalty=0.15,
                ),
                metadata={
                    "dynamic_distribution_version": DYNAMIC_DISTRIBUTION_VERSION,
                    "seed": cfg.seed,
                    "case_count": len(cases),
                },
            )
        )
    return scenarios
