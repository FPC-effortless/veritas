from __future__ import annotations

from investigation_world.companyworld.dynamic_distribution import _case_oracle, _role_roster
from investigation_world.companyworld.dynamic_models import (
    DynamicCaseSpec,
    DynamicCompanyWorldScenario,
    DynamicScenarioOracle,
    DynamicScenarioTask,
)
from investigation_world.companyworld.interactive_distribution import compile_interactive_episode
from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.companyworld.sequential_distribution import compile_sequential_episode


def build_o2c_episode(index: int, *, delay_days: int) -> CompanyWorldEpisode:
    suffix = f"{index:03d}"
    order_id = f"SO-CAL-{suffix}"
    shipment_id = f"SHP-CAL-{suffix}"
    order_record_id = f"REC-CAL-ORDER-{suffix}"
    shipment_record_id = f"REC-CAL-SHIP-{suffix}"
    requested = "2025-01-03T00:00:00"
    ship_day = 3 + delay_days
    shipment = f"2025-01-{ship_day:02d}T00:00:00"
    delivered = f"2025-01-{min(ship_day + 2, 28):02d}T00:00:00"

    records = [
        CompanyWorldRecord(
            record_id=order_record_id,
            system=CompanySystem.ERP,
            record_type="sales_order_commitment",
            object_type="SALES_ORDER",
            object_id=order_id,
            fields={
                "requested_ship_date": requested,
                "order_date": "2025-01-01T00:00:00",
            },
            source_file="calibration/orders",
        ),
        CompanyWorldRecord(
            record_id=shipment_record_id,
            system=CompanySystem.WMS,
            record_type="shipment_timeline",
            object_type="SHIPMENT",
            object_id=shipment_id,
            fields={
                "sales_order_id": order_id,
                "ship_date": shipment,
                "delivered_date": delivered,
            },
            source_file="calibration/shipments",
            related_object_ids=[order_id],
        ),
    ]
    task = CompanyWorldTask(
        task_id=f"TASK-CAL-{suffix}",
        world_id="CW-CALIBRATION",
        task_type="O2C_FULFILLMENT_TIMING",
        objective=f"Reconstruct fulfillment timing for {order_id} and support the conclusion with records.",
        target_object_type="SALES_ORDER",
        target_object_id=order_id,
        permitted_systems=[CompanySystem.ERP, CompanySystem.WMS],
    )
    status = "ON_TIME" if delay_days == 0 else "LATE"
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="o2c_fulfillment_timing",
        expected_resolution="Reconcile the order commitment with the shipment timeline.",
        facts=[
            OperationalFactTarget(
                object_type="SALES_ORDER",
                object_id=order_id,
                field_name="fulfillment_delay_days",
                expected_value=float(delay_days),
                supporting_record_ids=[order_record_id, shipment_record_id],
                support_mode="listed_count",
                minimum_support_records=2,
            ),
            OperationalFactTarget(
                object_type="SALES_ORDER",
                object_id=order_id,
                field_name="ship_commitment_status",
                expected_value=status,
                supporting_record_ids=[order_record_id, shipment_record_id],
                support_mode="listed_count",
                minimum_support_records=2,
            ),
        ],
    )
    return CompanyWorldEpisode(
        episode_id=f"CW-CAL-{suffix}",
        world_id="CW-CALIBRATION",
        task=task,
        records=records,
        oracle=oracle,
    )


def diagnostic_fixture() -> list[CompanyWorldEpisode]:
    return [
        build_o2c_episode(1, delay_days=0),
        build_o2c_episode(2, delay_days=2),
        build_o2c_episode(3, delay_days=5),
    ]


def interactive_fixture():
    return [compile_interactive_episode(item) for item in diagnostic_fixture()]


def sequential_fixture():
    # Generate enough IDs to include both direct-authority and delegated-authority cases.
    episodes = [
        compile_sequential_episode(
            compile_interactive_episode(build_o2c_episode(index, delay_days=index % 4))
        )
        for index in range(10, 30)
    ]
    direct = [item for item in episodes if not item.oracle.approval_required]
    delegated = [item for item in episodes if item.oracle.approval_required]
    chosen = [*direct[:2], *delegated[:1]]
    if len(chosen) < 3:
        chosen = episodes[:3]
    return chosen


def dynamic_fixture(seed: int = 7) -> DynamicCompanyWorldScenario:
    episodes = sequential_fixture()
    scenario_id = "DYN-CAL-000"
    cases = []
    oracles = []
    systems: set[str] = set()
    for position, episode in enumerate(episodes):
        case_id = f"{scenario_id}-C{position + 1}"
        systems.update(system.value for system in episode.task.permitted_systems)
        cases.append(
            DynamicCaseSpec(
                case_id=case_id,
                sequential=episode,
                deadline_tick=4 + position,
                priority_weight=float(3 - position),
                shared_resource="OPS_CONTROL",
                irreversible_remediation=False,
                role_roster=_role_roster(episode),
                late_penalty=round(0.10 + 0.02 * (3 - position), 4),
                metadata={"base_task_type": "O2C_FULFILLMENT_TIMING", "calibration": True},
            )
        )
        oracles.append(_case_oracle(case_id, episode, seed=seed))

    return DynamicCompanyWorldScenario(
        scenario_id=scenario_id,
        world_id="CW-CALIBRATION",
        task=DynamicScenarioTask(
            scenario_id=scenario_id,
            world_id="CW-CALIBRATION",
            objective=(
                "Manage the three concurrent fulfillment cases to verified end states while "
                "respecting authority, the shared operations-control resource, deadlines, "
                "stochastic approval outcomes, and the global budget."
            ),
            max_ticks=6,
            total_budget=120,
            shared_resource_capacities={"OPS_CONTROL": 1},
            system_failure_risk={system: 0.25 for system in sorted(systems)},
            constraints={
                "approval_outcomes_are_stochastic": True,
                "system_failures_are_stochastic": True,
                "shared_resources_have_capacity": True,
                "private_random_draws_are_evaluator_only": True,
            },
            metadata={"seed": seed, "calibration": True},
        ),
        cases=cases,
        oracle=DynamicScenarioOracle(
            scenario_id=scenario_id,
            case_oracles=oracles,
            coupled_deadline_threshold=2,
            coupled_deadline_penalty=0.15,
        ),
        metadata={"seed": seed, "case_count": len(cases), "calibration": True},
    )
