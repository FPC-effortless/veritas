from __future__ import annotations

import json

import pytest

from investigation_world.companyworld.dynamic_models import (
    DynamicCaseOracle,
    DynamicCaseSpec,
    DynamicCompanyWorldScenario,
    DynamicFailureMode,
    DynamicScenarioOracle,
    DynamicScenarioTask,
    DynamicSystemFailureWindow,
)
from investigation_world.companyworld.dynamic_reference import run_dynamic_public_reference
from investigation_world.companyworld.dynamic_runtime import DynamicCompanyWorldRuntime
from investigation_world.companyworld.interactive_distribution import compile_interactive_episode
from investigation_world.companyworld.interactive_models import OperationalAction, OperationalActionType
from investigation_world.companyworld.models import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
)
from investigation_world.companyworld.sequential_distribution import compile_sequential_episode
from investigation_world.companyworld.sequential_reference import solve_sequential_public


_GENERIC = {
    OperationalActionType.OPEN_CONTROL_CASE,
    OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
    OperationalActionType.RECONCILE_SYSTEM_STATE,
    OperationalActionType.VERIFY_CONTROL_INVARIANTS,
    OperationalActionType.CLOSE_CONTROL_CASE,
    OperationalActionType.COMPENSATE_LAST_ACTION,
    OperationalActionType.ESCALATE_CONTROL_FAILURE,
}


def _base_o2c(episode_id: str) -> CompanyWorldEpisode:
    order = CompanyWorldRecord(
        record_id=f"REC-ORDER-{episode_id}",
        system=CompanySystem.ERP,
        record_type="sales_order_commitment",
        object_type="SALES_ORDER",
        object_id="SO-1",
        fields={
            "requested_ship_date": "2025-01-01T00:00:00",
            "order_date": "2024-12-30T00:00:00",
        },
        source_file="fixture/orders",
    )
    shipment = CompanyWorldRecord(
        record_id=f"REC-SHIP-{episode_id}",
        system=CompanySystem.WMS,
        record_type="shipment_timeline",
        object_type="SHIPMENT",
        object_id="SHP-1",
        fields={
            "sales_order_id": "SO-1",
            "ship_date": "2025-01-03T00:00:00",
            "delivered_date": "2025-01-05T00:00:00",
        },
        source_file="fixture/shipments",
        related_object_ids=["SO-1"],
    )
    task = CompanyWorldTask(
        task_id=f"TASK-{episode_id}",
        world_id="CW-DYNAMIC-TEST",
        task_type="O2C_FULFILLMENT_TIMING",
        objective="Reconstruct fulfillment timing for SO-1.",
        target_object_type="SALES_ORDER",
        target_object_id="SO-1",
        permitted_systems=[CompanySystem.ERP, CompanySystem.WMS],
    )
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="o2c_fulfillment_timing",
        expected_resolution="Reconcile commitment and shipment.",
        facts=[
            OperationalFactTarget(
                object_type="SALES_ORDER",
                object_id="SO-1",
                field_name="fulfillment_delay_days",
                expected_value=2.0,
                supporting_record_ids=[order.record_id, shipment.record_id],
                support_mode="listed_count",
                minimum_support_records=2,
            ),
            OperationalFactTarget(
                object_type="SALES_ORDER",
                object_id="SO-1",
                field_name="ship_commitment_status",
                expected_value="LATE",
                supporting_record_ids=[order.record_id, shipment.record_id],
                support_mode="listed_count",
                minimum_support_records=2,
            ),
        ],
    )
    return CompanyWorldEpisode(
        episode_id=episode_id,
        world_id="CW-DYNAMIC-TEST",
        task=task,
        records=[order, shipment],
        oracle=oracle,
    )


def _sequential(*, approval_required: bool, prefix: str):
    for index in range(300):
        base = _base_o2c(f"{prefix}-{index}")
        sequential = compile_sequential_episode(compile_interactive_episode(base))
        if sequential.oracle.approval_required == approval_required:
            return sequential
    raise AssertionError("failed to produce requested authority stratum")


def _roles(sequential) -> list[str]:
    roles = {sequential.task.actor_role}
    for policy in sequential.task.action_policies:
        if policy.stage == "remediation":
            roles.update(policy.allowed_roles)
    return sorted(roles)


def _case(case_id: str, sequential, resource: str, deadline: int, *, irreversible=False):
    return DynamicCaseSpec(
        case_id=case_id,
        sequential=sequential,
        deadline_tick=deadline,
        priority_weight=3.0 if case_id.endswith("1") else 2.0,
        shared_resource=resource,
        irreversible_remediation=irreversible,
        role_roster=_roles(sequential),
        late_penalty=0.1,
    )


def _scenario(
    cases,
    oracles,
    *,
    max_ticks: int = 6,
    total_budget: int = 120,
):
    resources = sorted({case.shared_resource for case in cases})
    systems = sorted(
        {
            system.value
            for case in cases
            for system in case.sequential.task.permitted_systems
        }
    )
    return DynamicCompanyWorldScenario(
        scenario_id="DYN-TEST",
        world_id="CW-DYNAMIC-TEST",
        task=DynamicScenarioTask(
            scenario_id="DYN-TEST",
            world_id="CW-DYNAMIC-TEST",
            objective="Manage concurrent cases.",
            max_ticks=max_ticks,
            total_budget=total_budget,
            shared_resource_capacities={resource: 1 for resource in resources},
            system_failure_risk={system: 0.25 for system in systems},
        ),
        cases=cases,
        oracle=DynamicScenarioOracle(
            scenario_id="DYN-TEST",
            case_oracles=oracles,
            coupled_deadline_threshold=2,
            coupled_deadline_penalty=0.15,
        ),
    )


def _remediation(case_payload):
    _, plan = solve_sequential_public(case_payload["sequential"])
    return next(
        step.action
        for step in plan
        if step.kind == "action"
        and step.action is not None
        and step.action.action_type not in _GENERIC
    )


def _policy(case_payload, action_type):
    return next(
        policy
        for policy in case_payload["sequential"]["task"]["action_policies"]
        if policy["action_type"] == action_type.value
    )


def _open(case_payload):
    task = case_payload["sequential"]["task"]
    return OperationalAction(
        action_type=OperationalActionType.OPEN_CONTROL_CASE,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
    )


def test_dynamic_public_payload_hides_stochastic_oracle():
    direct = _sequential(approval_required=False, prefix="DIRECT")
    scenario = _scenario(
        [_case("C1", direct, "OPS_A", 4)],
        [
            DynamicCaseOracle(
                case_id="C1",
                approval_outcome="DENIED",
                failure_windows=[
                    DynamicSystemFailureWindow(
                        system=CompanySystem.ERP,
                        start_tick=0,
                        end_tick=0,
                        mode=DynamicFailureMode.UNAVAILABLE,
                    )
                ],
            )
        ],
    )
    serialized = json.dumps(scenario.public_payload(), sort_keys=True)
    assert '"oracle"' not in serialized
    assert '"approval_outcome"' not in serialized
    assert '"failure_windows"' not in serialized


def test_public_reference_recovers_from_denied_approval_by_handoff():
    approval = _sequential(approval_required=True, prefix="APPROVAL")
    direct = _sequential(approval_required=False, prefix="DIRECT")
    scenario = _scenario(
        [
            _case("C1", approval, "OPS_A", 4),
            _case("C2", direct, "OPS_B", 5),
        ],
        [
            DynamicCaseOracle(case_id="C1", approval_outcome="DENIED"),
            DynamicCaseOracle(case_id="C2", approval_outcome="APPROVED"),
        ],
    )
    runtime = DynamicCompanyWorldRuntime(scenario)
    _, score = run_dynamic_public_reference(runtime, scenario.public_payload())
    assert score.weighted_case_reward == 1.0
    assert score.case_success_rate == 1.0
    assert score.uncertainty_recovery == 1.0
    assert score.deadline_misses == 0
    assert score.resource_conflicts == 0
    assert score.handoffs >= 1
    assert score.overall_reward == 1.0


def test_transient_system_failure_is_observable_and_recovers():
    direct = _sequential(approval_required=False, prefix="OUTAGE")
    scenario = _scenario(
        [_case("C1", direct, "OPS_A", 4)],
        [
            DynamicCaseOracle(
                case_id="C1",
                failure_windows=[
                    DynamicSystemFailureWindow(
                        system=CompanySystem.ERP,
                        start_tick=0,
                        end_tick=0,
                        mode=DynamicFailureMode.UNAVAILABLE,
                    )
                ],
            )
        ],
    )
    runtime = DynamicCompanyWorldRuntime(scenario)
    failed = runtime.search_system("C1", CompanySystem.ERP, "SO-1")
    assert not failed.ok
    assert failed.retry_after_tick == 1
    runtime.advance(1)
    recovered = runtime.search_system("C1", CompanySystem.ERP, "SO-1")
    assert recovered.ok
    assert not recovered.degraded


def test_shared_resource_capacity_blocks_concurrent_remediation():
    first = _sequential(approval_required=False, prefix="RESOURCE-A")
    second = _sequential(approval_required=False, prefix="RESOURCE-B")
    scenario = _scenario(
        [
            _case("C1", first, "OPS_SHARED", 4),
            _case("C2", second, "OPS_SHARED", 5),
        ],
        [DynamicCaseOracle(case_id="C1"), DynamicCaseOracle(case_id="C2")],
    )
    runtime = DynamicCompanyWorldRuntime(scenario)
    payload = scenario.public_payload()
    for case_payload in payload["cases"]:
        case_id = case_payload["case_id"]
        remediation = _remediation(case_payload)
        policy = _policy(case_payload, remediation.action_type)
        assert runtime.act(case_id, _open(case_payload)).applied
        current = runtime.case_status(case_id)["actor_role"]
        if current not in policy["allowed_roles"]:
            assert runtime.handoff(case_id, sorted(policy["allowed_roles"])[0]).applied
    first_execution = runtime.act("C1", _remediation(payload["cases"][0]))
    second_execution = runtime.act("C2", _remediation(payload["cases"][1]))
    assert first_execution.applied
    assert not second_execution.applied
    assert "resource" in second_execution.reason
    assert runtime.resource_conflicts == 1


def test_irreversible_remediation_rejects_compensation():
    direct = _sequential(approval_required=False, prefix="IRREV")
    scenario = _scenario(
        [_case("C1", direct, "OPS_A", 4, irreversible=True)],
        [DynamicCaseOracle(case_id="C1")],
    )
    runtime = DynamicCompanyWorldRuntime(scenario)
    case_payload = scenario.public_payload()["cases"][0]
    remediation = _remediation(case_payload)
    policy = _policy(case_payload, remediation.action_type)
    assert runtime.act("C1", _open(case_payload)).applied
    current = runtime.case_status("C1")["actor_role"]
    if current not in policy["allowed_roles"]:
        runtime.handoff("C1", sorted(policy["allowed_roles"])[0])
    assert runtime.act("C1", remediation).applied
    task = case_payload["sequential"]["task"]
    compensation = OperationalAction(
        action_type=OperationalActionType.COMPENSATE_LAST_ACTION,
        target_object_type=task["target_object_type"],
        target_object_id=task["target_object_id"],
    )
    execution = runtime.act("C1", compensation)
    assert not execution.applied
    assert "irreversible" in execution.reason


def test_missed_deadlines_create_coupled_consequence_and_bound_reward():
    first = _sequential(approval_required=False, prefix="LATE-A")
    second = _sequential(approval_required=False, prefix="LATE-B")
    scenario = _scenario(
        [
            _case("C1", first, "OPS_A", 1),
            _case("C2", second, "OPS_B", 2),
        ],
        [DynamicCaseOracle(case_id="C1"), DynamicCaseOracle(case_id="C2")],
        max_ticks=3,
    )
    runtime = DynamicCompanyWorldRuntime(scenario)
    runtime.advance(3)
    score = runtime.submit({})
    assert score.deadline_misses == 2
    assert score.coupled_consequence_applied
    assert score.overall_reward <= 0.25


def test_global_budget_is_enforced_across_cases():
    first = _sequential(approval_required=False, prefix="BUDGET-A")
    second = _sequential(approval_required=False, prefix="BUDGET-B")
    scenario = _scenario(
        [
            _case("C1", first, "OPS_A", 4),
            _case("C2", second, "OPS_B", 5),
        ],
        [DynamicCaseOracle(case_id="C1"), DynamicCaseOracle(case_id="C2")],
        total_budget=2,
    )
    runtime = DynamicCompanyWorldRuntime(scenario)
    payload = scenario.public_payload()
    assert runtime.act("C1", _open(payload["cases"][0])).applied
    assert runtime.act("C2", _open(payload["cases"][1])).applied
    with pytest.raises(ValueError, match="budget exhausted"):
        runtime.advance(1)
