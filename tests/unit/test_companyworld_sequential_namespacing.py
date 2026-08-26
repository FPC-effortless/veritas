from __future__ import annotations

from investigation_world.companyworld import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalFactTarget,
    SequentialCompanyWorldRuntime,
    compile_interactive_episode,
    compile_sequential_episode,
    solve_sequential_public,
)


def _missing_shipment() -> CompanyWorldEpisode:
    order = CompanyWorldRecord(
        record_id="REC-ORDER-SUMMARY",
        system=CompanySystem.ERP,
        record_type="sales_order_fulfillment_summary",
        object_type="SALES_ORDER",
        object_id="SO-1",
        fields={"ordered_quantity": 10, "shipment_id": "SHP-1"},
        source_file="fixture/order_summary",
        related_object_ids=["SHP-1"],
    )
    manifest = CompanyWorldRecord(
        record_id="REC-CARRIER",
        system=CompanySystem.WMS,
        record_type="carrier_manifest",
        object_type="SHIPMENT",
        object_id="SHP-1",
        fields={"delivered_quantity": 6},
        source_file="fixture/carrier_manifest",
    )
    task = CompanyWorldTask(
        task_id="TASK-MISSING-SHIPMENT",
        world_id="CW-TEST",
        task_type="INVESTIGATE_MISSING_SHIPMENT",
        objective="Determine the delivered quantity for shipment SHP-1.",
        target_object_type="SHIPMENT",
        target_object_id="SHP-1",
        permitted_systems=[CompanySystem.ERP, CompanySystem.WMS],
    )
    oracle = CompanyWorldOracle(
        task_id=task.task_id,
        answer_class="missing_shipment",
        expected_resolution="Use the carrier manifest to establish delivered quantity.",
        facts=[
            OperationalFactTarget(
                object_type="SHIPMENT",
                object_id="SHP-1",
                field_name="delivered_quantity",
                expected_value=6,
                supporting_record_ids=["REC-CARRIER"],
            )
        ],
    )
    return CompanyWorldEpisode(
        episode_id="CWX-MISSING-SHIPMENT",
        world_id="CW-TEST",
        task=task,
        records=[order, manifest],
        oracle=oracle,
    )


def test_domain_and_control_remediation_states_do_not_collide():
    interactive = compile_interactive_episode(_missing_shipment())
    sequential = compile_sequential_episode(interactive)
    runtime = SequentialCompanyWorldRuntime(sequential)
    result, plan = solve_sequential_public(sequential.public_payload())

    for step in plan:
        if step.kind == "advance":
            runtime.advance(step.ticks)
        else:
            assert step.action is not None
            execution = runtime.act(step.action)
            assert execution.applied

    state = {item.field_name: item.value for item in runtime.state_snapshot()}
    assert state["remediation_status"] == "RESHIPMENT_CREATED"
    assert state["control_remediation_status"] == "APPLIED"
    assert state["replacement_quantity"] == 4.0

    score = runtime.submit(result)
    assert score.domain_outcome_score == 1.0
    assert score.control_state_score == 1.0
    assert score.overall_reward == 1.0
