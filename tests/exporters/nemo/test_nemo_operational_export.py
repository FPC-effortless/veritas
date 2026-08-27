import asyncio
import json

from pydantic import BaseModel, PrivateAttr

from investigation_world.exporters.nemo import (
    NeMoOperationalAdapter,
    bind_gymnasium_server,
    compile_nemo_surface,
    compile_nemo_task_row,
)
from investigation_world.operational.models import (
    ActionKind,
    HiddenActionEffect,
    HiddenOracle,
    OperationalEpisode,
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
from investigation_world.portable_runtime import (
    PortableOperationalRuntime,
    PortableRuntimeFailureCode,
)


def _episode(*, max_cost: int = 10) -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="nemo-episode-001",
        world_id="nemo-world-001",
        task=TaskContract(
            task_id="nemo-task-001",
            world_id="nemo-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the valid order.",
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
            ],
            constraints=["Use the ERP only."],
            success_description="The order is approved after preparation.",
            metadata={"fixture": "nemo-export"},
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending"},
                searchable_text="pending order",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id="nemo-task-001",
            initial_state={
                "order.status": "pending",
                "evaluator.secret": "PRIVATE-RUNTIME-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value="approved",
                )
            ],
            invariants=[],
            required_actions=["approve_order"],
            required_action_order=["prepare_order", "approve_order"],
            forbidden_actions=[],
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
            ],
            max_cost=max_cost,
            max_tool_calls=8,
            metadata={"expected_answer": "PRIVATE-ANSWER-OMEGA"},
        ),
        metadata={"public_episode": True},
    )


def _contract(*, max_cost: int = 10):
    return compile_operational_episode(_episode(max_cost=max_cost))


def _adapter(contract):
    return NeMoOperationalAdapter(
        contract.public,
        lambda: PortableOperationalRuntime(contract),
    )


def _typed_contract() -> PortableOperationalContract:
    baseline = _contract()
    public_payload = baseline.public.model_dump(mode="python", exclude={"public_id"})
    actions = list(public_payload["actions"])
    approve_index = next(
        index
        for index, action in enumerate(actions)
        if action["name"] == "approve_order"
    )
    approve = dict(actions[approve_index])
    approve["input_schema"] = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "note": {"type": "string"},
        },
        "required": ["order_id", "note"],
        "additionalProperties": False,
    }
    approve["additional_parameters_allowed"] = False
    actions[approve_index] = approve
    public_payload["actions"] = tuple(actions)
    public = PortablePublicContract(**public_payload)
    return PortableOperationalContract(
        schema_version=baseline.schema_version,
        public=public,
        private=baseline.private,
    )


def _tool_name(adapter: NeMoOperationalAdapter, canonical_name: str) -> str:
    return next(
        binding.transport_name
        for binding in adapter.surface.tool_bindings
        if binding.canonical_name == canonical_name
    )


def _call(tool_name: str, arguments: dict, *, call_id: str = "call-1") -> dict:
    return {
        "output": [
            {
                "type": "function_call",
                "call_id": call_id,
                "name": tool_name,
                "arguments": json.dumps(arguments, sort_keys=True),
            }
        ]
    }


def _reset_metadata(contract, *, seed: int) -> dict:
    return compile_nemo_task_row(contract.public, seed=seed)["veritas"]


def test_surface_preserves_exact_public_schemas_and_metadata() -> None:
    contract = _contract()
    surface = compile_nemo_surface(contract.public)
    task_row = compile_nemo_task_row(contract.public, seed=17)

    public_schemas = {
        ("action", action.name): (action.input_schema, action.output_schema)
        for action in contract.public.actions
    }
    public_schemas.update(
        {
            ("operation", operation.name): (
                operation.input_schema,
                operation.output_schema,
            )
            for operation in contract.public.runtime.builtin_operations
        }
    )

    assert task_row["responses_create_params"]["parallel_tool_calls"] is False
    assert task_row["veritas"]["public_contract_id"] == contract.public.public_id
    assert task_row["veritas"]["environment_id"] == surface.environment_id
    assert task_row["veritas"]["task_identity"]["task_id"] == "nemo-task-001"
    assert task_row["veritas"]["seed"] == 17

    tool_by_name = {
        tool["name"]: tool for tool in task_row["responses_create_params"]["tools"]
    }
    for binding in surface.tool_bindings:
        expected_input, expected_output = public_schemas[
            (binding.source_kind, binding.canonical_name)
        ]
        assert binding.input_schema == expected_input
        assert binding.output_schema == expected_output
        assert tool_by_name[binding.transport_name]["parameters"] == expected_input
        metadata = next(
            item
            for item in task_row["veritas"]["tool_bindings"]
            if item["transport_name"] == binding.transport_name
        )
        assert metadata["output_schema"] == expected_output


def test_reset_is_deterministic_and_sessions_are_isolated() -> None:
    contract = _contract()
    adapter = _adapter(contract)
    metadata = {"veritas": _reset_metadata(contract, seed=23)}

    first_obs, first_info = asyncio.run(adapter.reset(metadata, "session-a"))
    prepare = _tool_name(adapter, "prepare_order")
    asyncio.run(adapter.step(_call(prepare, {}, call_id="prepare-a"), {}, "session-a"))

    second_obs, second_info = asyncio.run(adapter.reset(metadata, "session-b"))

    assert second_obs == first_obs
    assert second_info["veritas"]["state_digest"] == first_info["veritas"]["state_digest"]
    assert second_info["veritas"]["state"] == first_info["veritas"]["state"]


def test_native_step_and_submit_match_direct_portable_runtime() -> None:
    contract = _contract()
    adapter = _adapter(contract)
    direct = PortableOperationalRuntime(contract)
    metadata = {"veritas": _reset_metadata(contract, seed=31)}
    asyncio.run(adapter.reset(metadata, "session"))
    direct.reset(seed=31)

    prepare = _tool_name(adapter, "prepare_order")
    approve = _tool_name(adapter, "approve_order")
    submit = _tool_name(adapter, "submit")

    direct_prepare = direct.step("prepare_order")
    native_prepare = asyncio.run(adapter.step(_call(prepare, {}), {}, "session"))
    assert native_prepare[1] == 0.0
    assert native_prepare[2] == direct_prepare.terminated
    assert native_prepare[3] == direct_prepare.truncated
    assert native_prepare[4]["veritas"]["state_digest"] == direct_prepare.state_digest

    approval_args = {"order_id": "ORDER-001", "note": "approve"}
    direct_approve = direct.step("approve_order", approval_args)
    native_approve = asyncio.run(
        adapter.step(_call(approve, approval_args, call_id="approve"), {}, "session")
    )
    assert native_approve[1] == 0.0
    assert native_approve[2] == direct_approve.terminated
    assert native_approve[3] == direct_approve.truncated
    assert native_approve[4]["veritas"]["state_digest"] == direct_approve.state_digest

    submission = {
        "conclusion": "Order approved.",
        "claimed_state": {"order.status": "approved"},
        "evidence_ids": ["record-001"],
        "confidence": 0.9,
    }
    direct_submit = direct.submit(submission)
    native_submit = asyncio.run(
        adapter.step(_call(submit, submission, call_id="submit"), {}, "session")
    )
    assert native_submit[1] == direct_submit.reward
    assert native_submit[2] == direct_submit.terminated is True
    assert native_submit[3] == direct_submit.truncated is False
    assert native_submit[4]["veritas"]["state_digest"] == direct_submit.state_digest
    assert native_submit[4]["veritas"]["reward_components"] == (
        direct_submit.reward_components.model_dump(mode="json")
    )


def test_budget_exhaustion_remains_truncation_not_termination() -> None:
    contract = _contract(max_cost=1)
    adapter = _adapter(contract)
    direct = PortableOperationalRuntime(contract)
    metadata = {"veritas": _reset_metadata(contract, seed=5)}
    asyncio.run(adapter.reset(metadata, "session"))
    direct.reset(seed=5)

    approve = _tool_name(adapter, "approve_order")
    arguments = {"order_id": "ORDER-001", "note": "approve"}
    direct_result = direct.step("approve_order", arguments)
    native = asyncio.run(adapter.step(_call(approve, arguments), {}, "session"))

    assert direct_result.failure is not None
    assert direct_result.failure.code == PortableRuntimeFailureCode.BUDGET_EXHAUSTED
    assert native[1] == 0.0
    assert native[2] is False
    assert native[3] is True
    assert native[4]["veritas"]["failure"]["code"] == "budget_exhausted"
    assert native[4]["veritas"]["state_digest"] == direct_result.state_digest


def test_private_evaluator_state_never_reaches_nemo_surfaces() -> None:
    contract = _contract()
    adapter = _adapter(contract)
    row = compile_nemo_task_row(contract.public, seed=7)
    metadata = {"veritas": row["veritas"]}
    reset = asyncio.run(adapter.reset(metadata, "session"))
    prepare = _tool_name(adapter, "prepare_order")
    step = asyncio.run(adapter.step(_call(prepare, {}), {}, "session"))

    encoded = json.dumps({"row": row, "reset": reset, "step": step}, sort_keys=True)
    for private_value in (
        "PRIVATE-RUNTIME-OMEGA",
        "PRIVATE-ANSWER-OMEGA",
        "evaluator.secret",
        "oracle",
        "initial_state",
    ):
        assert private_value not in encoded


def test_invalid_typed_input_is_runtime_failure_and_non_mutating() -> None:
    contract = _typed_contract()
    adapter = _adapter(contract)
    metadata = {"veritas": _reset_metadata(contract, seed=11)}
    _, reset_info = asyncio.run(adapter.reset(metadata, "session"))
    before = reset_info["veritas"]["state_digest"]
    approve = _tool_name(adapter, "approve_order")

    native = asyncio.run(
        adapter.step(
            _call(
                approve,
                {"order_id": "ORDER-001", "note": 7},
                call_id="bad-type",
            ),
            {},
            "session",
        )
    )

    assert native[2] is False
    assert native[3] is False
    assert native[4]["veritas"]["failure"]["code"] == "invalid_action_input"
    assert native[4]["veritas"]["state_digest"] == before


def test_parallel_tool_calls_fail_closed_without_partial_execution() -> None:
    contract = _contract()
    adapter = _adapter(contract)
    metadata = {"veritas": _reset_metadata(contract, seed=13)}
    _, reset_info = asyncio.run(adapter.reset(metadata, "session"))
    before = reset_info["veritas"]["state_digest"]
    prepare = _tool_name(adapter, "prepare_order")
    action = {
        "output": [
            {
                "type": "function_call",
                "call_id": "one",
                "name": prepare,
                "arguments": "{}",
            },
            {
                "type": "function_call",
                "call_id": "two",
                "name": prepare,
                "arguments": "{}",
            },
        ]
    }

    native = asyncio.run(adapter.step(action, {}, "session"))

    assert native[1] == 0.0
    assert native[2] is False
    assert native[3] is True
    assert native[4]["veritas"]["adapter_failure"]["code"] == (
        "PARALLEL_TOOL_CALLS_UNSUPPORTED"
    )
    assert native[4]["veritas"]["state_digest"] == before


def test_bind_gymnasium_server_delegates_native_methods_and_cleanup() -> None:
    contract = _contract()

    class FakeGymnasiumServer(BaseModel):
        _closed: list[str | None] = PrivateAttr(default_factory=list)

        async def close_session(self, session_id: str | None) -> None:
            self._closed.append(session_id)

    Bound = bind_gymnasium_server(FakeGymnasiumServer, lambda: _adapter(contract))
    server = Bound()
    metadata = {"veritas": _reset_metadata(contract, seed=19)}
    asyncio.run(server.reset(metadata, "session"))
    asyncio.run(server.close_session("session"))

    assert server._closed == ["session"]
