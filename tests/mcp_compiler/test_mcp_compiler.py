import json

import pytest

from investigation_world.mcp_compiler import (
    MCPCompilerError,
    MCPDispatchMode,
    MCPToolCallError,
    MCPToolSourceKind,
    compile_mcp_surface,
    dispatch_mcp_tool,
    resolve_mcp_tool_call,
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
from investigation_world.portable_runtime import PortableOperationalRuntime


def _episode() -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="mcp-episode-001",
        world_id="mcp-world-001",
        task=TaskContract(
            task_id="mcp-task-001",
            world_id="mcp-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the order and cite the public record.",
            role="operations_controller",
            permitted_systems=["ERP"],
            available_actions=[
                PublicActionSpec(
                    name="approve_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Approve the selected order.",
                    parameter_names=["order_id"],
                    cost=1,
                )
            ],
            constraints=["Do not invent evidence."],
            success_description="The order is approved.",
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending"},
                searchable_text="pending order ORDER-001",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id="mcp-task-001",
            initial_state={
                "order.status": "pending",
                "private.secret": "MCP-PRIVATE-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value="approved",
                )
            ],
            required_actions=["approve_order"],
            required_evidence_ids=["record-001"],
            action_effects=[
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": "ORDER-001"},
                    set_state={"order.status": "approved"},
                    observable_result={"accepted": True, "status": "approved"},
                )
            ],
            max_cost=10,
            max_tool_calls=8,
            metadata={"expected_answer": "MCP-PRIVATE-ANSWER"},
        ),
    )


def _contract() -> PortableOperationalContract:
    return compile_operational_episode(_episode())


def _tool_for(surface, *, kind: MCPToolSourceKind, canonical_name: str):
    provenance = next(
        item
        for item in surface.catalog.provenance
        if item.source_kind is kind and item.canonical_name == canonical_name
    )
    tool = next(item for item in surface.catalog.tools if item.name == provenance.transport_name)
    return provenance, tool


def test_compilation_is_deterministic_and_wire_catalog_is_current_mcp_shape() -> None:
    contract = _contract()
    first = compile_mcp_surface(contract.public)
    second = compile_mcp_surface(contract.public)

    assert first.catalog.catalog_id == second.catalog.catalog_id
    assert first.surface_id == second.surface_id
    assert first.catalog.tools_list_result() == second.catalog.tools_list_result()
    assert first.catalog.protocol_version == "2026-07-28"
    wire = first.catalog.tools_list_result()
    assert wire["ttlMs"] == 0
    assert wire["cacheScope"] == "private"
    assert set(wire) == {"tools", "ttlMs", "cacheScope"}
    assert all(
        set(tool) == {"name", "description", "inputSchema", "outputSchema"}
        for tool in wire["tools"]
    )


def test_action_and_operation_schemas_are_lossless_and_identity_is_not_alias() -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)

    action_provenance, action_tool = _tool_for(
        surface,
        kind=MCPToolSourceKind.ACTION,
        canonical_name="approve_order",
    )
    source_action = contract.public.actions[0]
    assert action_tool.input_schema == source_action.input_schema
    assert action_tool.output_schema == source_action.output_schema
    assert action_provenance.canonical_identity == "portable-action:approve_order"
    assert action_provenance.transport_name != action_provenance.canonical_name

    operation_provenance, operation_tool = _tool_for(
        surface,
        kind=MCPToolSourceKind.OPERATION,
        canonical_name="search",
    )
    source_operation = next(
        item for item in contract.public.runtime.builtin_operations if item.name == "search"
    )
    assert operation_tool.input_schema == source_operation.input_schema
    assert operation_tool.output_schema == source_operation.output_schema
    assert operation_provenance.canonical_identity == "portable-operation:search"


def test_aliases_remain_unique_for_normalization_and_action_operation_collisions() -> None:
    contract = _contract()
    payload = contract.public.model_dump(mode="python", exclude={"public_id"})
    base = payload["actions"][0]
    first = dict(base)
    second = dict(base)
    third = dict(base)
    first["name"] = "alpha-beta"
    second["name"] = "alpha_beta"
    third["name"] = "search"
    payload["actions"] = (first, second, third)
    public = PortablePublicContract(**payload)

    surface = compile_mcp_surface(public)
    aliases = [tool.name for tool in surface.catalog.tools]
    assert len(aliases) == len(set(aliases))

    search_aliases = {
        item.source_kind: item.transport_name
        for item in surface.catalog.provenance
        if item.canonical_name == "search"
    }
    assert search_aliases[MCPToolSourceKind.ACTION] != search_aliases[MCPToolSourceKind.OPERATION]


def test_compiler_rejects_evaluator_private_contract_input_and_public_wire_has_no_secret() -> None:
    contract = _contract()
    with pytest.raises(MCPCompilerError) as exc_info:
        compile_mcp_surface(contract)  # type: ignore[arg-type]
    assert exc_info.value.code == "PUBLIC_CONTRACT_REQUIRED"

    surface = compile_mcp_surface(contract.public)
    serialized = json.dumps(surface.catalog.tools_list_result(), sort_keys=True)
    assert "MCP-PRIVATE-OMEGA" not in serialized
    assert "MCP-PRIVATE-ANSWER" not in serialized
    assert contract.contract_id not in serialized


def test_non_object_input_schema_fails_closed() -> None:
    contract = _contract()
    payload = contract.public.model_dump(mode="python", exclude={"public_id"})
    actions = list(payload["actions"])
    action = dict(actions[0])
    action["input_schema"] = {"type": "string"}
    actions[0] = action
    payload["actions"] = tuple(actions)
    public = PortablePublicContract(**payload)

    with pytest.raises(MCPCompilerError) as exc_info:
        compile_mcp_surface(public)
    assert exc_info.value.code == "MCP_INPUT_ROOT_NOT_OBJECT"


def test_compiled_schemas_are_nested_immutable_and_identity_cannot_go_stale() -> None:
    surface = compile_mcp_surface(_contract().public)
    before = surface.catalog.catalog_id
    tool = surface.catalog.tools[0]
    with pytest.raises(TypeError):
        tool.input_schema["x"] = "mutated"
    assert surface.catalog.catalog_id == before


def test_mcp_action_dispatch_matches_direct_portable_runtime() -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)
    provenance, _ = _tool_for(
        surface,
        kind=MCPToolSourceKind.ACTION,
        canonical_name="approve_order",
    )
    direct = PortableOperationalRuntime(contract)
    via_mcp = PortableOperationalRuntime(contract)
    direct.reset(seed=41)
    via_mcp.reset(seed=41)

    expected = direct.step("approve_order", {"order_id": "ORDER-001"})
    actual = dispatch_mcp_tool(
        via_mcp,
        surface,
        provenance.transport_name,
        {"order_id": "ORDER-001"},
    )
    assert actual == expected


def test_mcp_operation_and_submit_dispatch_match_direct_runtime() -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)

    search_provenance, _ = _tool_for(
        surface,
        kind=MCPToolSourceKind.OPERATION,
        canonical_name="search",
    )
    direct_search = PortableOperationalRuntime(contract)
    mcp_search = PortableOperationalRuntime(contract)
    assert dispatch_mcp_tool(
        mcp_search,
        surface,
        search_provenance.transport_name,
        {"system": "ERP", "query": "pending"},
    ) == direct_search.step(
        {
            "kind": "operation",
            "name": "search",
            "arguments": {"system": "ERP", "query": "pending"},
        }
    )

    submit_provenance, _ = _tool_for(
        surface,
        kind=MCPToolSourceKind.OPERATION,
        canonical_name="submit",
    )
    target, _ = resolve_mcp_tool_call(surface, submit_provenance.transport_name, {})
    assert target.dispatch_mode is MCPDispatchMode.SUBMIT
    direct_submit = PortableOperationalRuntime(contract)
    mcp_submit = PortableOperationalRuntime(contract)
    assert dispatch_mcp_tool(
        mcp_submit,
        surface,
        submit_provenance.transport_name,
        {},
    ) == direct_submit.submit({})


def test_invalid_and_unknown_mcp_calls_do_not_mutate_runtime() -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)
    runtime = PortableOperationalRuntime(contract)
    provenance, _ = _tool_for(
        surface,
        kind=MCPToolSourceKind.ACTION,
        canonical_name="approve_order",
    )
    before_digest = runtime.state_digest()
    before_budget = runtime.budget_state()

    with pytest.raises(MCPToolCallError) as invalid:
        dispatch_mcp_tool(runtime, surface, provenance.transport_name, {})
    assert invalid.value.json_rpc_code == -32602
    assert runtime.state_digest() == before_digest
    assert runtime.budget_state() == before_budget

    with pytest.raises(MCPToolCallError) as unknown:
        dispatch_mcp_tool(runtime, surface, "not_a_compiled_tool", {})
    assert unknown.value.code == "UNKNOWN_TOOL"
    assert runtime.state_digest() == before_digest
    assert runtime.budget_state() == before_budget
