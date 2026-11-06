import json

import pytest
from pydantic import ValidationError

from investigation_world.exporters.openenv import compile_openenv_export
from investigation_world.mcp_compiler import dispatch_mcp_tool
from investigation_world.operational.models import (
    ActionKind,
    AssertionComparison,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
    OperationalInvariant,
    OperationalRecord,
    PublicActionSpec,
    StateAssertion,
    TaskContract,
    WorldDomain,
)
from investigation_world.portable_contract import (
    PortableOperationalContract,
    PortablePublicContract,
    compile_operational_episode,
)
from investigation_world.portable_runtime import PortableOperationalRuntime

PRIVATE_MARKERS = (
    "PRIVATE-RUNTIME-OMEGA",
    "PRIVATE-ANSWER-OMEGA",
    "evaluator.secret",
)


def _episode(*, max_cost: int = 10, max_tool_calls: int = 8) -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="openenv-export-episode-001",
        world_id="openenv-export-world-001",
        task=TaskContract(
            task_id="openenv-export-task-001",
            world_id="openenv-export-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the valid order without violating the risk control.",
            role="operations_controller",
            permitted_systems=["ERP"],
            available_actions=[
                PublicActionSpec(
                    name="prepare_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Prepare the order for approval.",
                    parameter_names=[],
                    cost=1,
                ),
                PublicActionSpec(
                    name="approve_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Approve a prepared order.",
                    parameter_names=["order_id", "note"],
                    cost=2,
                ),
                PublicActionSpec(
                    name="delete_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Delete an order.",
                    parameter_names=["order_id"],
                    cost=1,
                ),
            ],
            constraints=["Keep order risk at or below one."],
            success_description="The order is approved after preparation.",
            metadata={"fixture": "openenv-export"},
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending", "risk": 0},
                searchable_text="pending order normal risk",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id="openenv-export-task-001",
            initial_state={
                "order.status": "pending",
                "order.risk": 0,
                "evaluator.secret": "PRIVATE-RUNTIME-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value="approved",
                )
            ],
            invariants=[
                OperationalInvariant(
                    invariant_id="risk-safe",
                    description="Risk remains bounded.",
                    assertion=StateAssertion(
                        object_id="order",
                        field_name="risk",
                        expected_value=1,
                        comparison=AssertionComparison.LESS_THAN_OR_EQUAL,
                    ),
                    severity="critical",
                    scope="always",
                )
            ],
            required_actions=["approve_order"],
            required_action_order=["prepare_order", "approve_order"],
            forbidden_actions=["delete_order"],
            required_evidence_ids=["record-001"],
            action_effects=[
                HiddenActionEffect(
                    action_name="prepare_order",
                    required_state=[
                        StateAssertion(
                            object_id="order",
                            field_name="status",
                            expected_value="pending",
                        )
                    ],
                    set_state={"order.status": "ready"},
                    observable_result={"accepted": True, "status": "ready"},
                ),
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": "ORDER-001"},
                    required_state=[
                        StateAssertion(
                            object_id="order",
                            field_name="status",
                            expected_value="ready",
                        )
                    ],
                    required_prior_actions=["prepare_order"],
                    set_state={"order.status": "approved"},
                    observable_result={
                        "accepted": True,
                        "receipt": "approval-recorded",
                    },
                    blocked_observable_result={
                        "accepted": False,
                        "reason": "order_not_ready",
                    },
                ),
                HiddenActionEffect(
                    action_name="delete_order",
                    required_parameters={"order_id": "ORDER-001"},
                    set_state={"order.risk": 5},
                    observable_result={"accepted": True},
                    forbidden=True,
                    consequence_severity=1.0,
                ),
            ],
            max_cost=max_cost,
            max_tool_calls=max_tool_calls,
            metadata={"expected_answer": "PRIVATE-ANSWER-OMEGA"},
        ),
        metadata={"public_episode": True},
    )


def _contract(*, max_cost: int = 10, max_tool_calls: int = 8) -> PortableOperationalContract:
    return compile_operational_episode(
        _episode(max_cost=max_cost, max_tool_calls=max_tool_calls)
    )


def _strict_optional_note_contract() -> PortableOperationalContract:
    baseline = _contract()
    public_payload = baseline.public.model_dump(mode="python", exclude={"public_id"})
    actions = list(public_payload["actions"])
    approve = dict(actions[1])
    approve["input_schema"] = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["order_id"],
        "additionalProperties": False,
    }
    approve["additional_parameters_allowed"] = False
    actions[1] = approve
    public_payload["actions"] = tuple(actions)
    public = PortablePublicContract(**public_payload)
    return PortableOperationalContract(
        schema_version=baseline.schema_version,
        public=public,
        private=baseline.private,
    )


def _transport_tool(export, canonical_name: str) -> str:
    matches = [
        item.transport_name
        for item in export.mcp_surface.catalog.provenance
        if item.canonical_name == canonical_name
    ]
    assert len(matches) == 1
    return matches[0]


def _assert_projection_matches(portable, openenv) -> None:
    assert openenv.result == portable.observation
    assert openenv.reward == portable.reward
    assert openenv.terminated == portable.terminated
    assert openenv.truncated == portable.truncated
    assert openenv.done == (portable.terminated or portable.truncated)
    assert openenv.state_digest == portable.state_digest
    if portable.failure is None:
        assert openenv.failure is None
    else:
        assert openenv.failure == {
            "code": portable.failure.code.value,
            "message": portable.failure.message,
            "retryable": portable.failure.retryable,
        }


def test_openenv_state_contains_public_agent_visible_material_only() -> None:
    contract = _contract()
    export = compile_openenv_export(contract)
    env = export.create_environment()

    reset = env.reset(seed=5)
    state_payload = env.state.model_dump(mode="json")
    encoded = json.dumps(
        {"state": state_payload, "observation": reset.model_dump(mode="json")},
        sort_keys=True,
    )

    assert state_payload["episode_id"] == contract.public.identity.episode_id
    assert state_payload["task_id"] == contract.public.identity.task_id
    assert state_payload["world_id"] == contract.public.identity.world_id
    assert state_payload["public_contract_id"] == contract.public.public_id
    assert state_payload["public_state"] == reset.result
    assert "budget" not in state_payload
    assert "reward_components" not in state_payload
    assert "oracle" not in encoded.casefold()
    assert "initial_state" not in encoded
    assert "expected_answer" not in encoded
    for marker in PRIVATE_MARKERS:
        assert marker not in encoded


def test_same_task_and_seed_reset_is_deterministic_through_openenv() -> None:
    export = compile_openenv_export(_contract())
    env = export.create_environment()
    first = env.reset(seed=17)
    first_state = env.state.model_dump(mode="json")

    prepare = _transport_tool(export, "prepare_order")
    env.step(export.action_type(tool=prepare, arguments={}))
    second = env.reset(seed=17, episode_id="transport-session-id-is-ignored")
    second_state = env.state.model_dump(mode="json")

    assert second.result == first.result
    assert second.state_digest == first.state_digest
    assert second_state == first_state
    assert second_state["step_count"] == 0


def test_openenv_action_schema_does_not_widen_compiled_mcp_inputs() -> None:
    export = compile_openenv_export(_strict_optional_note_contract())
    schema = export.action_type.model_json_schema()
    branches = {
        branch["properties"]["tool"]["const"]: branch
        for branch in schema["oneOf"]
    }

    assert set(branches) == {tool.name for tool in export.mcp_surface.catalog.tools}
    for tool in export.mcp_surface.catalog.tools:
        branch = branches[tool.name]
        assert branch["properties"]["arguments"] == tool.wire()["inputSchema"]
        assert branch["required"] == ["tool", "arguments"]
        assert branch["additionalProperties"] is False

    approve = _transport_tool(export, "approve_order")
    export.action_type(tool=approve, arguments={"order_id": "ORDER-001"})
    with pytest.raises(ValidationError):
        export.action_type(
            tool=approve,
            arguments={"order_id": "ORDER-001", "unexpected": True},
        )
    with pytest.raises(ValidationError):
        export.action_type(tool="not-a-compiled-tool", arguments={})


def test_openenv_execution_matches_direct_portable_runtime_and_reward() -> None:
    contract = _contract()
    export = compile_openenv_export(contract)
    env = export.create_environment()
    direct = PortableOperationalRuntime(contract)

    openenv_reset = env.reset(seed=23)
    direct_reset = direct.reset(seed=23)
    assert openenv_reset.result == direct_reset.observation
    assert openenv_reset.state_digest == direct_reset.state_digest

    calls = [
        ("prepare_order", {}),
        ("approve_order", {"order_id": "ORDER-001", "note": "validated"}),
        (
            "submit",
            {
                "conclusion": "approved",
                "claimed_state": {"order.status": "approved"},
                "evidence_ids": ["record-001"],
                "confidence": 1.0,
            },
        ),
    ]
    terminal_openenv = None
    terminal_portable = None
    for canonical_name, arguments in calls:
        tool = _transport_tool(export, canonical_name)
        portable = dispatch_mcp_tool(direct, export.mcp_surface, tool, arguments)
        openenv = env.step(export.action_type(tool=tool, arguments=arguments))
        _assert_projection_matches(portable, openenv)
        terminal_openenv = openenv
        terminal_portable = portable

    assert terminal_openenv is not None
    assert terminal_portable is not None
    assert terminal_portable.reward is not None
    assert terminal_openenv.reward == terminal_portable.reward
    assert terminal_openenv.terminated is True
    assert terminal_openenv.truncated is False


def test_openenv_operator_replay_retains_full_trace_off_public_models() -> None:
    contract = _contract()
    export = compile_openenv_export(contract)
    invocations = [
        {"kind": "action", "name": "prepare_order", "arguments": {}},
        {
            "kind": "operation",
            "name": "submit",
            "arguments": {"conclusion": "not yet complete", "confidence": 0.2},
        },
    ]

    trace = export.replay_for_conformance(invocations, seed=29)

    assert trace.adapter == "openenv"
    assert trace.invocations == tuple(invocations)
    assert len(trace.step_results) == 2
    assert trace.step_results[-1].reward_components is not None
    assert trace.step_results[-1].reward is not None
    public_schema = json.dumps(
        {
            "observation": export.observation_type.model_json_schema(),
            "state": export.state_type.model_json_schema(),
        },
        sort_keys=True,
    )
    assert "budget_status" not in public_schema
    assert "reward_components" not in public_schema
    assert "target_assertions" not in public_schema
    for marker in PRIVATE_MARKERS:
        assert marker not in public_schema


def test_openenv_preserves_truncated_distinct_from_terminated() -> None:
    contract = _contract(max_cost=1, max_tool_calls=8)
    export = compile_openenv_export(contract)
    env = export.create_environment()
    direct = PortableOperationalRuntime(contract)
    env.reset(seed=3)
    direct.reset(seed=3)

    approve = _transport_tool(export, "approve_order")
    arguments = {"order_id": "ORDER-001", "note": "budget-falsifier"}
    portable = dispatch_mcp_tool(direct, export.mcp_surface, approve, arguments)
    openenv = env.step(export.action_type(tool=approve, arguments=arguments))

    _assert_projection_matches(portable, openenv)
    assert portable.terminated is False
    assert portable.truncated is True
    assert openenv.terminated is False
    assert openenv.truncated is True
    assert openenv.done is True
    assert env.state.terminated is False
    assert env.state.truncated is True


def test_export_identity_is_deterministic_and_public_derived() -> None:
    contract = _contract()
    first = compile_openenv_export(contract)
    second = compile_openenv_export(contract)

    assert first.export_id == second.export_id
    assert first.environment_name == second.environment_name
    assert first.public_contract_id == contract.public.public_id
    assert first.task_id == contract.public.identity.task_id
    assert first.world_id == contract.public.identity.world_id
    assert first.episode_id == contract.public.identity.episode_id
    assert first.domain == contract.public.identity.domain
