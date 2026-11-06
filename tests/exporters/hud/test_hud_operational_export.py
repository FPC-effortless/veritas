import json
from pathlib import Path

import pytest

from investigation_world.exporters.hud import (
    HudOperationalAdapter,
    HudOperationalExportError,
    build_hud_operational_export,
)
from investigation_world.mcp_compiler import (
    MCPToolSourceKind,
    compile_mcp_surface,
    dispatch_mcp_tool,
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
from investigation_world.portable_contract import compile_operational_episode
from investigation_world.portable_runtime import PortableOperationalRuntime, PortableSubmission


def _episode() -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="hud-generic-episode-001",
        world_id="hud-generic-world-001",
        task=TaskContract(
            task_id="hud-generic-task-001",
            world_id="hud-generic-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Prepare and approve the valid order using public evidence.",
            role="operations_controller",
            permitted_systems=["ERP"],
            available_actions=[
                PublicActionSpec(
                    name="prepare_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Prepare the order.",
                    parameter_names=[],
                    cost=1,
                ),
                PublicActionSpec(
                    name="approve_order",
                    kind=ActionKind.WRITE,
                    system="ERP",
                    description="Approve the prepared order.",
                    parameter_names=["order_id"],
                    cost=1,
                ),
            ],
            constraints=["Use only the authoritative order record."],
            success_description="The prepared order is approved.",
            metadata={"fixture": "generic-hud"},
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
            task_id="hud-generic-task-001",
            initial_state={
                "order.status": "pending",
                "evaluator.secret": "HUD-PRIVATE-OMEGA",
            },
            target_state=[
                StateAssertion(
                    object_id="order",
                    field_name="status",
                    expected_value="approved",
                )
            ],
            required_actions=["approve_order"],
            required_action_order=["prepare_order", "approve_order"],
            required_evidence_ids=["record-001"],
            action_effects=[
                HiddenActionEffect(
                    action_name="prepare_order",
                    set_state={"order.status": "ready"},
                    observable_result={"accepted": True, "status": "ready"},
                ),
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": "ORDER-001"},
                    required_prior_actions=["prepare_order"],
                    set_state={"order.status": "approved"},
                    observable_result={"accepted": True, "status": "approved"},
                ),
            ],
            max_cost=10,
            max_tool_calls=8,
            metadata={"expected_answer": "HUD-PRIVATE-ANSWER"},
        ),
        metadata={"public_episode": True},
    )


def _contract():
    return compile_operational_episode(_episode())


def _tool(surface, kind: MCPToolSourceKind, canonical_name: str) -> str:
    return next(
        item.transport_name
        for item in surface.catalog.provenance
        if item.source_kind is kind and item.canonical_name == canonical_name
    )


def test_tasks_start_is_exact_portable_reset() -> None:
    contract = _contract()
    direct = PortableOperationalRuntime(contract)
    adapter = HudOperationalAdapter(contract)

    expected = direct.reset(seed=17)
    actual = adapter.start(seed=17, session_id="sess-a")

    assert actual.reset == expected
    assert json.loads(actual.prompt)["initial_observation"] == expected.observation
    assert "HUD-PRIVATE-OMEGA" not in actual.prompt
    assert "HUD-PRIVATE-ANSWER" not in actual.prompt


def test_compiled_capability_catalog_and_schemas_are_unchanged() -> None:
    contract = _contract()
    expected = compile_mcp_surface(contract.public)
    adapter = HudOperationalAdapter(contract)

    assert adapter.surface == expected
    actual_tools = [
        tool.model_dump(mode="json", by_alias=True) for tool in adapter.surface.catalog.tools
    ]
    assert actual_tools == [
        tool.model_dump(mode="json", by_alias=True) for tool in expected.catalog.tools
    ]


def test_hud_tool_execution_and_grade_match_direct_runtime_reward() -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)
    prepare = _tool(surface, MCPToolSourceKind.ACTION, "prepare_order")
    approve = _tool(surface, MCPToolSourceKind.ACTION, "approve_order")

    direct = PortableOperationalRuntime(contract)
    direct.reset(seed=9)
    adapter = HudOperationalAdapter(contract)
    adapter.start(seed=9, session_id="sess-a")

    assert adapter.call_tool(prepare, {}) == dispatch_mcp_tool(direct, surface, prepare, {})
    assert adapter.call_tool(approve, {"order_id": "ORDER-001"}) == dispatch_mcp_tool(
        direct, surface, approve, {"order_id": "ORDER-001"}
    )

    submission = PortableSubmission(evidence_ids=["record-001"], confidence=1.0)
    expected = direct.verify(submission)
    actual = adapter.grade(submission, session_id="sess-a")
    assert actual == expected
    assert actual.reward == expected.reward
    assert actual.reward_components == expected.reward_components


def test_terminal_mcp_submit_reward_is_reused_by_tasks_grade() -> None:
    contract = _contract()
    adapter = HudOperationalAdapter(contract)
    adapter.start(seed=3, session_id="sess-a")
    submit = _tool(adapter.surface, MCPToolSourceKind.OPERATION, "submit")

    terminal = adapter.call_tool(submit, {})
    graded = adapter.grade(
        "this answer must not trigger a second verification",
        session_id="sess-a",
    )
    assert terminal.reward is not None
    assert graded == terminal


def test_metering_failure_cannot_change_semantics() -> None:
    contract = _contract()

    def broken_meter(_):
        raise RuntimeError("meter unavailable")

    adapter = HudOperationalAdapter(contract, meter=broken_meter)
    started = adapter.start(seed=1, session_id="sess-a")
    assert started.reset.state_digest == adapter.runtime.state_digest()


def test_second_concurrent_session_fails_closed() -> None:
    adapter = HudOperationalAdapter(_contract())
    adapter.start(seed=0, session_id="sess-a")
    with pytest.raises(HudOperationalExportError) as exc_info:
        adapter.start(seed=0, session_id="sess-b")
    assert exc_info.value.code == "HUD_CONCURRENT_SESSION_UNSUPPORTED"


def test_public_package_has_no_hidden_truth_and_operator_is_self_contained(tmp_path: Path) -> None:
    contract = _contract()
    result = build_hud_operational_export(contract, tmp_path)

    public_text = "\n".join(
        (tmp_path / item.path).read_text(encoding="utf-8")
        for item in result.files
        if item.path.startswith("public/")
    )
    assert "HUD-PRIVATE-OMEGA" not in public_text
    assert "HUD-PRIVATE-ANSWER" not in public_text
    assert contract.contract_id not in public_text
    assert contract.public.public_id in public_text

    operator_contract = (tmp_path / "operator/contract.json").read_text(encoding="utf-8")
    assert "HUD-PRIVATE-OMEGA" in operator_contract
    assert contract.contract_id in operator_contract

    dockerfile = (tmp_path / "operator/Dockerfile").read_text(encoding="utf-8")
    pyproject = (tmp_path / "operator/pyproject.toml").read_text(encoding="utf-8")
    assert "@sha256:" in dockerfile
    assert "hud==0.6.15" in pyproject
    assert "mcp==1.24.0" in pyproject
    assert "pip install -e" not in dockerfile
    assert "PYTHONPATH" not in dockerfile
    assert "/workspace" not in dockerfile
    assert (tmp_path / "operator/vendor/investigation_world/portable_runtime/runtime.py").is_file()
    assert (
        tmp_path / "operator/vendor/investigation_world/portable_runtime/validation.py"
    ).is_file()
    assert (tmp_path / "operator/vendor/investigation_world/mcp_compiler/compiler.py").is_file()

    public_metadata = json.loads((tmp_path / "public/package.json").read_text(encoding="utf-8"))
    operator_metadata = json.loads((tmp_path / "operator/package.json").read_text(encoding="utf-8"))
    assert "contract_id" not in public_metadata
    assert operator_metadata["contract_id"] == contract.contract_id
    assert operator_metadata["operator_package_id"] == result.operator_package_id


def test_package_generation_is_deterministic(tmp_path: Path) -> None:
    contract = _contract()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = build_hud_operational_export(contract, first_dir)
    second = build_hud_operational_export(contract, second_dir)

    assert first.public_package_id == second.public_package_id
    assert first.operator_package_id == second.operator_package_id
    assert first.export_id == second.export_id
    assert [(item.path, item.sha256, item.bytes) for item in first.files] == [
        (item.path, item.sha256, item.bytes) for item in second.files
    ]


def test_exact_hud_mcp_gaps_are_reported() -> None:
    adapter = HudOperationalAdapter(_contract())
    gaps = {gap.code: gap for gap in adapter.compatibility_gaps}
    assert "HUD_MCP_PROTOCOL_VERSION_LAG" in gaps
    assert "HUD_MCP_LEGACY_STRUCTURED_OUTPUT_OBJECT_ONLY" in gaps
    assert "PORTABLE_MCP_SUBMIT_RESULT_ENVELOPE_GAP" in gaps

    search_tool = _tool(adapter.surface, MCPToolSourceKind.OPERATION, "search")
    assert search_tool in gaps["HUD_MCP_LEGACY_STRUCTURED_OUTPUT_OBJECT_ONLY"].affected_tools


def test_nonempty_output_directory_fails_closed(tmp_path: Path) -> None:
    (tmp_path / "unrelated.txt").write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(RuntimeError, match="must be empty"):
        build_hud_operational_export(_contract(), tmp_path)
    assert (tmp_path / "unrelated.txt").read_text(encoding="utf-8") == "do not overwrite"
