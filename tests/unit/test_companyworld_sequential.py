from __future__ import annotations

from investigation_world.companyworld import (
    CompanySystem,
    CompanyWorldEpisode,
    CompanyWorldOracle,
    CompanyWorldRecord,
    CompanyWorldTask,
    OperationalAction,
    OperationalActionType,
    OperationalFactTarget,
    SequentialCompanyWorldRuntime,
    compile_interactive_episode,
    compile_sequential_episode,
    solve_sequential_public,
)


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
        record_id="REC-ORDER",
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
        record_id="REC-SHIP",
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
        world_id="CW-TEST",
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
                supporting_record_ids=["REC-ORDER", "REC-SHIP"],
                support_mode="listed_count",
                minimum_support_records=2,
            ),
            OperationalFactTarget(
                object_type="SALES_ORDER",
                object_id="SO-1",
                field_name="ship_commitment_status",
                expected_value="LATE",
                supporting_record_ids=["REC-ORDER", "REC-SHIP"],
                support_mode="listed_count",
                minimum_support_records=2,
            ),
        ],
    )
    return CompanyWorldEpisode(
        episode_id=episode_id,
        world_id="CW-TEST",
        task=task,
        records=[order, shipment],
        oracle=oracle,
    )


def _sequential(*, approval_required: bool):
    for index in range(200):
        interactive = compile_interactive_episode(_base_o2c(f"CWX-SEQ-{index}"))
        episode = compile_sequential_episode(interactive)
        if episode.oracle.approval_required == approval_required:
            return episode
    raise AssertionError("failed to generate requested authority stratum")


def _run_reference(episode):
    runtime = SequentialCompanyWorldRuntime(episode)
    result, plan = solve_sequential_public(episode.public_payload())
    for step in plan:
        if step.kind == "advance":
            runtime.advance(step.ticks)
        else:
            assert step.action is not None
            execution = runtime.act(step.action)
            assert execution.applied
    return runtime, result, runtime.submit(result)


def _remediation(plan):
    return next(
        step.action
        for step in plan
        if step.kind == "action"
        and step.action is not None
        and step.action.action_type not in _GENERIC
    )


def test_sequential_public_payload_hides_oracle():
    episode = _sequential(approval_required=True)
    payload = episode.public_payload()
    serialized = str(payload)
    assert "remediation_action_type" not in serialized
    assert "remediation_action_parameters" not in serialized
    assert "domain_outcome_conditions" not in serialized
    assert "control_outcome_conditions" not in serialized
    assert "oracle" not in payload


def test_reference_solver_reaches_full_reward_with_direct_authority():
    _, _, score = _run_reference(_sequential(approval_required=False))
    assert score.domain_outcome_score == 1.0
    assert score.control_state_score == 1.0
    assert score.investigation_fact_score == 1.0
    assert score.evidence_support == 1.0
    assert score.authority_score == 1.0
    assert score.sequence_efficiency == 1.0
    assert score.overall_reward == 1.0


def test_approval_is_delayed_and_scoped_before_delegated_remediation():
    episode = _sequential(approval_required=True)
    runtime = SequentialCompanyWorldRuntime(episode)
    result, plan = solve_sequential_public(episode.public_payload())
    actions = [step.action for step in plan if step.action is not None]
    request = next(
        action
        for action in actions
        if action.action_type == OperationalActionType.REQUEST_OPERATIONAL_APPROVAL
    )
    remediation = _remediation(plan)

    assert runtime.act(actions[0]).applied
    assert runtime.act(request).applied
    state = {item.field_name: item.value for item in runtime.state_snapshot()}
    assert state["approval_status"] == "PENDING"

    denied_before_event = runtime.act(remediation)
    assert not denied_before_event.applied
    assert not denied_before_event.authorized

    runtime.advance(1)
    state = {item.field_name: item.value for item in runtime.state_snapshot()}
    assert state["approval_status"] == "APPROVED"
    assert state["approval_scope"] == remediation.action_type.value
    assert runtime.act(remediation).applied

    assert result.claims


def test_wrong_approval_scope_does_not_grant_remediation_authority():
    episode = _sequential(approval_required=True)
    runtime = SequentialCompanyWorldRuntime(episode)
    result, plan = solve_sequential_public(episode.public_payload())
    remediation = _remediation(plan)
    open_action = OperationalAction(
        action_type=OperationalActionType.OPEN_CONTROL_CASE,
        target_object_type=episode.task.target_object_type,
        target_object_id=episode.task.target_object_id,
    )
    wrong_request = OperationalAction(
        action_type=OperationalActionType.REQUEST_OPERATIONAL_APPROVAL,
        target_object_type=episode.task.target_object_type,
        target_object_id=episode.task.target_object_id,
        parameters={"requested_action": OperationalActionType.CONFIRM_FULFILLMENT.value},
    )
    assert runtime.act(open_action).applied
    assert runtime.act(wrong_request).applied
    runtime.advance(1)
    execution = runtime.act(remediation)
    assert not execution.applied
    assert not execution.authorized
    assert result.claims


def test_prerequisites_block_out_of_order_reconciliation_without_mutation():
    episode = _sequential(approval_required=False)
    runtime = SequentialCompanyWorldRuntime(episode)
    before = [item.model_dump(mode="json") for item in runtime.state_snapshot()]
    execution = runtime.act(
        OperationalAction(
            action_type=OperationalActionType.RECONCILE_SYSTEM_STATE,
            target_object_type=episode.task.target_object_type,
            target_object_id=episode.task.target_object_id,
        )
    )
    after = [item.model_dump(mode="json") for item in runtime.state_snapshot()]
    assert execution.authorized
    assert not execution.prerequisites_met
    assert not execution.applied
    assert before == after


def test_reconciliation_requires_external_tick_before_verification():
    episode = _sequential(approval_required=False)
    runtime = SequentialCompanyWorldRuntime(episode)
    _, plan = solve_sequential_public(episode.public_payload())
    remediation = _remediation(plan)
    open_action = next(
        step.action
        for step in plan
        if step.action is not None
        and step.action.action_type == OperationalActionType.OPEN_CONTROL_CASE
    )
    assert open_action is not None
    assert runtime.act(open_action).applied
    assert runtime.act(remediation).applied
    reconcile = OperationalAction(
        action_type=OperationalActionType.RECONCILE_SYSTEM_STATE,
        target_object_type=episode.task.target_object_type,
        target_object_id=episode.task.target_object_id,
    )
    assert runtime.act(reconcile).applied
    state = {item.field_name: item.value for item in runtime.state_snapshot()}
    assert state["reconciliation_status"] == "PENDING"

    verify = OperationalAction(
        action_type=OperationalActionType.VERIFY_CONTROL_INVARIANTS,
        target_object_type=episode.task.target_object_type,
        target_object_id=episode.task.target_object_id,
    )
    assert not runtime.act(verify).applied
    runtime.advance(1)
    assert runtime.act(verify).applied


def test_compensation_restores_pre_remediation_state():
    episode = _sequential(approval_required=False)
    runtime = SequentialCompanyWorldRuntime(episode)
    _, plan = solve_sequential_public(episode.public_payload())
    open_action = next(
        step.action
        for step in plan
        if step.action is not None
        and step.action.action_type == OperationalActionType.OPEN_CONTROL_CASE
    )
    remediation = _remediation(plan)
    assert open_action is not None
    assert runtime.act(open_action).applied
    before = {item.key(): item.value for item in runtime.state_snapshot()}
    remediation_execution = runtime.act(remediation)
    assert remediation_execution.applied

    compensation = runtime.act(
        OperationalAction(
            action_type=OperationalActionType.COMPENSATE_LAST_ACTION,
            target_object_type=episode.task.target_object_type,
            target_object_id=episode.task.target_object_id,
        )
    )
    assert compensation.applied
    after = {item.key(): item.value for item in runtime.state_snapshot()}
    for effect in remediation_execution.effects:
        assert after.get(effect.key()) == before.get(effect.key())


def test_one_shot_remediation_cannot_shortcut_control_protocol():
    episode = _sequential(approval_required=False)
    runtime = SequentialCompanyWorldRuntime(episode)
    result, plan = solve_sequential_public(episode.public_payload())
    execution = runtime.act(_remediation(plan))
    assert not execution.applied
    score = runtime.submit(result)
    assert score.overall_reward <= 0.25


def test_sequential_actions_never_rewrite_evidence():
    episode = _sequential(approval_required=True)
    before = [
        item.model_dump(mode="json")
        for item in episode.interactive.investigation.records
    ]
    _run_reference(episode)
    after = [
        item.model_dump(mode="json")
        for item in episode.interactive.investigation.records
    ]
    assert before == after
