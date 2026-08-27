import json
import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from investigation_world.exporters.harbor import (
    HarborArtifactVisibility,
    HarborExportConfig,
    HarborExportError,
    RuntimeControl,
    export_harbor_package,
    render_harbor_package,
    replay_harbor_trajectory,
)
from investigation_world.exporters.harbor.mcp_service import (
    _tool_wire_result,
    _validate_runtime_control_url,
)
from investigation_world.exporters.harbor.verifier import (
    HarborVerificationResult,
    _write_outputs,
)
from investigation_world.mcp_compiler import MCPToolSourceKind, compile_mcp_surface
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
from investigation_world.portable_runtime import PortableOperationalRuntime


def _contract():
    episode = OperationalEpisode(
        episode_id="harbor-episode-001",
        world_id="harbor-world-001",
        task=TaskContract(
            task_id="harbor-task-001",
            world_id="harbor-world-001",
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
            task_id="harbor-task-001",
            initial_state={
                "order.status": "pending",
                "private.secret": "HARBOR-PRIVATE-OMEGA",
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
            metadata={"expected_answer": "HARBOR-PRIVATE-ANSWER"},
        ),
    )
    return compile_operational_episode(episode)


def _config() -> HarborExportConfig:
    return HarborExportConfig(
        task_name="veritas/harbor-test",
        agent_image="example.invalid/agent@sha256:" + "a" * 64,
        runtime_image="example.invalid/runtime@sha256:" + "b" * 64,
        verifier_image="example.invalid/verifier@sha256:" + "c" * 64,
        seed=41,
    )


def _alias(surface, kind: MCPToolSourceKind, canonical_name: str) -> str:
    return next(
        item.transport_name
        for item in surface.catalog.provenance
        if item.source_kind is kind and item.canonical_name == canonical_name
    )


def test_render_is_deterministic_and_public_files_exclude_private_truth() -> None:
    contract = _contract()
    first = render_harbor_package(contract, _config())
    second = render_harbor_package(contract, _config())
    assert {path: item.payload for path, item in first.items()} == {
        path: item.payload for path, item in second.items()
    }

    public = b"\n".join(
        item.payload
        for item in first.values()
        if item.visibility is HarborArtifactVisibility.AGENT_PUBLIC
    )
    assert b"HARBOR-PRIVATE-OMEGA" not in public
    assert b"HARBOR-PRIVATE-ANSWER" not in public
    assert contract.canonical_bytes() not in public
    assert "environment/main/Dockerfile" in first
    assert "environment/Dockerfile" not in first
    assert b"HARBOR-PRIVATE-OMEGA" in first[
        "environment/runtime-control/contract.json"
    ].payload
    assert b"HARBOR-PRIVATE-ANSWER" in first["tests/contract.json"].payload


def test_harbor_task_and_compose_enforce_native_mcp_and_separate_verifier_boundaries() -> None:
    contract = _contract()
    rendered = render_harbor_package(contract, _config())
    task = tomllib.loads(rendered["task.toml"].payload.decode())
    surface = compile_mcp_surface(contract.public)

    assert task["schema_version"] == "1.4"
    assert task["verifier"]["environment_mode"] == "separate"
    assert task["verifier"]["environment"]["network_mode"] == "no-network"
    assert task["environment"]["mcp_servers"] == [
        {
            "name": "veritas-operational",
            "transport": "streamable-http",
            "url": "http://mcp-server:8000/mcp",
        }
    ]
    assert task["metadata"]["veritas_mcp_surface_id"] == surface.surface_id
    assert task["metadata"]["veritas_public_contract_id"] == contract.public.public_id
    assert task["artifacts"] == [
        {
            "source": "/tmp/veritas-runtime/trajectory.jsonl",
            "service": "runtime-control",
        }
    ]

    compose = rendered["environment/docker-compose.yaml"].payload.decode()
    main_service, after_main = compose.split("\n  mcp-server:\n", maxsplit=1)
    mcp_service, after_mcp = after_main.split("\n  runtime-control:\n", maxsplit=1)
    runtime_service = after_mcp.split("\nnetworks:\n", maxsplit=1)[0]
    assert "      context: ./main\n" in main_service
    assert "      context: .\n" not in main_service
    assert "      - runtime-control\n" not in main_service
    assert "      - runtime-control\n" in mcp_service
    assert "      - agent-mcp\n" not in runtime_service
    assert "ports:" not in compose
    assert "internal: true" in compose


def test_runtime_control_and_offline_verifier_match_direct_portable_runtime(
    tmp_path: Path,
) -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)
    action = _alias(surface, MCPToolSourceKind.ACTION, "approve_order")
    submit = _alias(surface, MCPToolSourceKind.OPERATION, "submit")

    direct = PortableOperationalRuntime(contract)
    direct.reset(seed=41)
    expected_action = direct.step("approve_order", {"order_id": "ORDER-001"})
    expected_submit = direct.submit({})

    trajectory = tmp_path / "trajectory.jsonl"
    control = RuntimeControl(contract, seed=41, trajectory_path=trajectory)
    assert control.call_tool(action, {"order_id": "ORDER-001"}) == expected_action
    actual_submit = control.call_tool(submit, {})
    assert actual_submit == expected_submit

    records = [json.loads(line) for line in trajectory.read_text().splitlines()]
    verified = replay_harbor_trajectory(contract, records)
    assert verified.reward == expected_submit.reward
    assert verified.reward_components == expected_submit.reward_components.model_dump(mode="json")
    assert verified.replayed_tool_calls == 2


def test_verifier_natively_scores_unsubmitted_trajectory(tmp_path: Path) -> None:
    contract = _contract()
    surface = compile_mcp_surface(contract.public)
    action = _alias(surface, MCPToolSourceKind.ACTION, "approve_order")
    trajectory = tmp_path / "trajectory.jsonl"
    control = RuntimeControl(contract, seed=41, trajectory_path=trajectory)
    control.call_tool(action, {"order_id": "ORDER-001"})

    expected = PortableOperationalRuntime(contract)
    expected.reset(seed=41)
    expected.step("approve_order", {"order_id": "ORDER-001"})
    expected_final = expected.verify()

    records = [json.loads(line) for line in trajectory.read_text().splitlines()]
    verified = replay_harbor_trajectory(contract, records)
    assert verified.reward == expected_final.reward
    assert verified.reward_components == expected_final.reward_components.model_dump(mode="json")


def test_mcp_wire_response_does_not_publish_reward_or_private_runtime_metadata() -> None:
    step = {
        "observation": {"accepted": True},
        "reward": 0.9375,
        "reward_components": {"outcome": 1.0},
        "terminated": True,
        "truncated": False,
        "state_digest": "private-digest",
        "budget_status": {"resources": []},
        "failure": None,
    }
    wire = _tool_wire_result(step)
    serialized = json.dumps(wire, sort_keys=True)
    assert wire["structuredContent"] == {"accepted": True}
    assert "0.9375" not in serialized
    assert "private-digest" not in serialized
    assert "reward" not in serialized


def test_mcp_wire_does_not_wrap_non_object_observations() -> None:
    wire = _tool_wire_result({"observation": ["a", "b"], "failure": None})
    assert "structuredContent" not in wire
    assert wire["content"][0]["text"] == '["a","b"]'


def test_runtime_control_url_is_fixed_to_private_compose_service() -> None:
    assert (
        _validate_runtime_control_url("http://runtime-control:8081")
        == "http://runtime-control:8081"
    )
    for value in (
        "file:///tmp/runtime.sock",
        "http://localhost:8081",
        "http://runtime-control:8082",
        "https://runtime-control:8081",
        "http://runtime-control:8081/tool",
    ):
        with pytest.raises(ValueError, match="runtime-control"):
            _validate_runtime_control_url(value)


def test_verifier_reward_output_round_trips_native_float_exactly(tmp_path: Path) -> None:
    native_reward = 0.12345678912345678
    reward_path = tmp_path / "reward.txt"
    details_path = tmp_path / "details.json"
    result = HarborVerificationResult(
        reward=native_reward,
        reward_components={"outcome": native_reward},
        final_result={"reward": native_reward},
        replayed_tool_calls=1,
    )
    _write_outputs(result, reward_path, details_path)
    assert float(reward_path.read_text().strip()) == native_reward
    assert json.loads(details_path.read_text())["reward"] == native_reward


def test_export_materializes_only_declared_files_and_refuses_stale_output(
    tmp_path: Path,
) -> None:
    contract = _contract()
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    first = export_harbor_package(contract, first_dir, _config())
    second = export_harbor_package(contract, second_dir, _config())
    assert first.package_id == second.package_id
    assert [(item.path, item.sha256, item.visibility) for item in first.files] == [
        (item.path, item.sha256, item.visibility) for item in second.files
    ]
    assert {item.path for item in first.files} == {
        path.relative_to(first_dir).as_posix()
        for path in first_dir.rglob("*")
        if path.is_file()
    }

    with pytest.raises(HarborExportError, match="absent or empty"):
        export_harbor_package(contract, first_dir, _config())


def test_mutable_image_references_fail_closed() -> None:
    with pytest.raises(ValidationError, match="immutable sha256"):
        HarborExportConfig(
            task_name="veritas/harbor-test",
            agent_image="python:3.12-slim",
            runtime_image="example.invalid/runtime@sha256:" + "b" * 64,
        )
