from __future__ import annotations

import json
from pathlib import Path

import pytest

from investigation_world.exporters.harbor import RuntimeControl
from investigation_world.mcp_compiler import MCPToolSourceKind
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
from tools import world_portability

PRIVATE_SECRET = "WORLD-CLI-PRIVATE-OMEGA"
PRIVATE_ANSWER = "WORLD-CLI-PRIVATE-ANSWER"


def _episode() -> OperationalEpisode:
    return OperationalEpisode(
        episode_id="world-cli-episode-001",
        world_id="world-cli-world-001",
        task=TaskContract(
            task_id="world-cli-task-001",
            world_id="world-cli-world-001",
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Approve the order after checking the public record.",
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
            constraints=["Use public evidence."],
            success_description="The order is approved.",
        ),
        records=[
            OperationalRecord(
                record_id="record-001",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending"},
                searchable_text="pending ORDER-001",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id="world-cli-task-001",
            initial_state={
                "order.status": "pending",
                "private.secret": PRIVATE_SECRET,
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
            metadata={"expected_answer": PRIVATE_ANSWER},
        ),
    )


def _contract_path(tmp_path: Path) -> Path:
    path = tmp_path / "contract.json"
    path.write_bytes(compile_operational_episode(_episode()).canonical_bytes())
    return path


def _vector_path(tmp_path: Path) -> Path:
    path = tmp_path / "vector.json"
    path.write_text(
        json.dumps(
            {
                "seed": 17,
                "actions": [
                    {
                        "kind": "action",
                        "name": "approve_order",
                        "arguments": {"order_id": "ORDER-001"},
                    },
                    {
                        "kind": "operation",
                        "name": "submit",
                        "arguments": {
                            "conclusion": "approved",
                            "claimed_state": {"order.status": "approved"},
                            "evidence_ids": ["record-001"],
                            "confidence": 1.0,
                        },
                    },
                ],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def _assert_no_private_output(capsys: pytest.CaptureFixture[str]) -> tuple[str, str]:
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert PRIVATE_SECRET not in combined
    assert PRIVATE_ANSWER not in combined
    return captured.out, captured.err


def test_compile_writes_full_and_public_contract_without_printing_private_truth(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    episode_path = tmp_path / "episode.json"
    episode_path.write_text(_episode().model_dump_json(), encoding="utf-8")
    full_path = tmp_path / "portable.json"
    public_path = tmp_path / "portable-public.json"

    code = world_portability.main(
        [
            "compile",
            "--episode",
            str(episode_path),
            "--output",
            str(full_path),
            "--public-output",
            str(public_path),
        ]
    )

    assert code == 0
    _assert_no_private_output(capsys)
    assert PRIVATE_SECRET in full_path.read_text(encoding="utf-8")
    assert PRIVATE_ANSWER in full_path.read_text(encoding="utf-8")
    assert PRIVATE_SECRET not in public_path.read_text(encoding="utf-8")
    assert PRIVATE_ANSWER not in public_path.read_text(encoding="utf-8")


def test_inspect_and_partition_are_public_safe_by_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract_path = _contract_path(tmp_path)

    assert world_portability.main(["inspect", "--contract", str(contract_path)]) == 0
    inspect_out, _ = _assert_no_private_output(capsys)
    inspect_payload = json.loads(inspect_out)
    assert "operator_identities" not in inspect_payload
    assert inspect_payload["partition"]["valid"] is True

    assert (
        world_portability.main(["validate-partition", "--contract", str(contract_path)])
        == 0
    )
    partition_out, _ = _assert_no_private_output(capsys)
    assert json.loads(partition_out)["valid"] is True


def test_run_omits_private_budget_and_verifier_components_by_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract_path = _contract_path(tmp_path)
    vector_path = _vector_path(tmp_path)

    assert (
        world_portability.main(
            [
                "run",
                "--contract",
                str(contract_path),
                "--vector",
                str(vector_path),
            ]
        )
        == 0
    )
    output, _ = _assert_no_private_output(capsys)
    payload = json.loads(output)
    assert "operator" not in payload
    assert payload["steps"][-1]["terminated"] is True
    assert "budget_status" not in payload["steps"][-1]
    assert "reward_components" not in payload["steps"][-1]


def test_nemo_export_is_public_only_and_stdout_is_public_safe(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract_path = _contract_path(tmp_path)
    output = tmp_path / "nemo"

    assert (
        world_portability.main(
            [
                "export",
                "--adapter",
                "nemo",
                "--contract",
                str(contract_path),
                "--output",
                str(output),
            ]
        )
        == 0
    )
    _assert_no_private_output(capsys)
    materialized = "\n".join(
        path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file()
    )
    assert PRIVATE_SECRET not in materialized
    assert PRIVATE_ANSWER not in materialized


def test_harbor_conformance_passes_without_printing_private_truth(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract_path = _contract_path(tmp_path)
    vector_path = _vector_path(tmp_path)

    assert (
        world_portability.main(
            [
                "conformance",
                "--adapter",
                "harbor",
                "--contract",
                str(contract_path),
                "--vector",
                str(vector_path),
            ]
        )
        == 0
    )
    output, _ = _assert_no_private_output(capsys)
    payload = json.loads(output)
    assert payload["passed"] is True
    assert payload["semantic_losses"] == []
    assert set(payload["preserved_fields"]) == set(world_portability.REQUIRED_SEMANTIC_FIELDS)


@pytest.mark.parametrize("adapter", ["openenv", "prime"])
def test_full_operator_conformance_passes_without_exposing_private_truth(
    adapter: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = world_portability.main(
        [
            "conformance",
            "--adapter",
            adapter,
            "--contract",
            str(_contract_path(tmp_path)),
            "--vector",
            str(_vector_path(tmp_path)),
        ]
    )
    assert code == 0
    output, err = _assert_no_private_output(capsys)
    assert err == ""
    payload = json.loads(output)
    assert payload["adapter"] == adapter
    assert payload["passed"] is True
    assert payload["semantic_losses"] == []
    assert payload["unsupported_fields"] == []
    assert set(payload["preserved_fields"]) == set(world_portability.REQUIRED_SEMANTIC_FIELDS)


def test_trajectory_identity_and_reverification_inspection_is_private_safe_by_default(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    contract = compile_operational_episode(_episode())
    contract_path = tmp_path / "contract.json"
    contract_path.write_bytes(contract.canonical_bytes())
    trajectory = tmp_path / "trajectory.jsonl"
    control = RuntimeControl(contract, seed=17, trajectory_path=trajectory)
    action_alias = next(
        item.transport_name
        for item in control.surface.catalog.provenance
        if item.source_kind is MCPToolSourceKind.ACTION
        and item.canonical_name == "approve_order"
    )
    control.call_tool(action_alias, {"order_id": "ORDER-001"})

    assert (
        world_portability.main(
            [
                "trajectory",
                "--trajectory",
                str(trajectory),
                "--contract",
                str(contract_path),
                "--reverify",
            ]
        )
        == 0
    )
    output, _ = _assert_no_private_output(capsys)
    payload = json.loads(output)
    assert payload["identity_match"] is True
    assert payload["reverified"] is True
    assert "contract_id" not in payload
    assert "operator" not in payload
    assert "reward" not in payload


def test_validation_errors_do_not_echo_private_input_values(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad = tmp_path / "bad-contract.json"
    bad.write_text(
        json.dumps({"schema_version": PRIVATE_SECRET, "private": PRIVATE_ANSWER}),
        encoding="utf-8",
    )

    assert world_portability.main(["inspect", "--contract", str(bad)]) == 2
    _, err = _assert_no_private_output(capsys)
    assert "CONTRACT_INVALID" in err
