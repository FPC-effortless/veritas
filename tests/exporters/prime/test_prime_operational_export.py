from __future__ import annotations

import json
from pathlib import Path

import pytest

from investigation_world.exporters.prime import (
    DEFAULT_VERITAS_REQUIREMENT,
    PrimeReplayRequest,
    build_prime_operational_package,
    replay_portable_requests,
    replay_portable_requests_for_conformance,
)
from investigation_world.operational.models import (
    ActionKind,
    EpisodeSubmission,
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


def _episode(suffix: str = "001") -> OperationalEpisode:
    task_id = f"generic-prime-task-{suffix}"
    world_id = f"generic-prime-world-{suffix}"
    return OperationalEpisode(
        episode_id=f"generic-prime-episode-{suffix}",
        world_id=world_id,
        task=TaskContract(
            task_id=task_id,
            world_id=world_id,
            domain=WorldDomain.ENTERPRISE_OPERATIONS,
            objective="Prepare and approve the requested order using the available systems.",
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
            constraints=["Do not approve an order before preparation."],
            success_description="The requested order is approved after preparation.",
            metadata={"fixture": "generic-prime"},
        ),
        records=[
            OperationalRecord(
                record_id=f"record-{suffix}",
                system="ERP",
                record_type="order",
                object_id="order",
                fields={"status": "pending"},
                searchable_text="pending order awaiting approval",
                source_authority="authoritative",
                freshness="current",
            )
        ],
        oracle=HiddenOracle(
            task_id=task_id,
            initial_state={
                "order.status": "pending",
                "evaluator.secret": f"PRIVATE-PRIME-{suffix}",
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
            required_evidence_ids=[f"record-{suffix}"],
            action_effects=[
                HiddenActionEffect(
                    action_name="prepare_order",
                    set_state={"order.status": "ready"},
                    observable_result={"accepted": True, "status": "ready"},
                ),
                HiddenActionEffect(
                    action_name="approve_order",
                    required_parameters={"order_id": f"ORDER-{suffix}"},
                    required_state=[
                        StateAssertion(
                            object_id="order",
                            field_name="status",
                            expected_value="ready",
                        )
                    ],
                    required_prior_actions=["prepare_order"],
                    set_state={"order.status": "approved"},
                    observable_result={"accepted": True, "receipt": f"approval-{suffix}"},
                ),
            ],
            max_cost=20,
            max_tool_calls=20,
            metadata={"expected_answer": f"PRIVATE-ANSWER-{suffix}"},
        ),
        metadata={"public_episode": True},
    )


def _typed_contract(suffix: str = "001") -> PortableOperationalContract:
    baseline = compile_operational_episode(_episode(suffix))
    public_payload = baseline.public.model_dump(mode="python", exclude={"public_id"})
    actions = list(public_payload["actions"])
    approve = dict(actions[1])
    approve["input_schema"] = {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "minLength": 1},
            "note": {"type": "string", "maxLength": 200},
        },
        "required": ["order_id"],
        "additionalProperties": True,
    }
    actions[1] = approve
    public_payload["actions"] = tuple(actions)
    public = PortablePublicContract(**public_payload)
    return PortableOperationalContract(
        schema_version=baseline.schema_version,
        public=public,
        private=baseline.private,
    )


def _file_map(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_export_is_generic_and_does_not_embed_sre_causal_labels(tmp_path: Path) -> None:
    output = tmp_path / "prime"
    build_prime_operational_package(output, contracts=[_typed_contract()])
    rendered = "\n".join(
        path.read_text(encoding="utf-8")
        for path in output.rglob("*")
        if path.is_file() and path.suffix in {".py", ".md", ".toml"}
    ).casefold()

    for forbidden in (
        "causal_class",
        "regression",
        "infrastructure",
        "capacity",
        "transient",
        "sretask",
    ):
        assert forbidden not in rendered


def test_public_task_rows_preserve_typed_action_semantics_without_private_truth(
    tmp_path: Path,
) -> None:
    contract = _typed_contract()
    output = tmp_path / "prime"
    build_prime_operational_package(output, contracts=[contract])

    rows = json.loads(
        (output / "veritas_prime_operational" / "public_tasks.json").read_text(
            encoding="utf-8"
        )
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["portable_public_id"] == contract.public.public_id
    assert row["public_contract"] == contract.public.model_dump(mode="json")

    approve_schema = next(
        action["input_schema"]
        for action in row["public_contract"]["actions"]
        if action["name"] == "approve_order"
    )
    assert approve_schema == contract.public.actions[1].input_schema
    binding = next(
        item
        for item in row["tool_bindings"].values()
        if item["kind"] == "action" and item["name"] == "approve_order"
    )
    assert binding["input_schema"] == approve_schema
    assert binding["output_schema"] == contract.public.actions[1].output_schema

    public_bytes = json.dumps(rows, sort_keys=True)
    assert "PRIVATE-PRIME-001" not in public_bytes
    assert "PRIVATE-ANSWER-001" not in public_bytes
    assert '"oracle"' not in public_bytes
    assert '"private"' not in public_bytes

    private_bytes = (
        output / "veritas_prime_operational" / "private_contracts.json"
    ).read_text(encoding="utf-8")
    assert "PRIVATE-PRIME-001" in private_bytes
    assert "PRIVATE-ANSWER-001" in private_bytes


def test_task_identity_and_package_contents_are_deterministic_across_input_order(
    tmp_path: Path,
) -> None:
    first_contract = _typed_contract("001")
    second_contract = _typed_contract("002")
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"

    first = build_prime_operational_package(
        first_dir,
        contracts=[first_contract, second_contract],
    )
    second = build_prime_operational_package(
        second_dir,
        contracts=[second_contract, first_contract],
    )

    assert first.package_id == second.package_id
    assert _file_map(first_dir) == _file_map(second_dir)

    rows = json.loads(
        (first_dir / "veritas_prime_operational" / "public_tasks.json").read_text(
            encoding="utf-8"
        )
    )
    assert [row["portable_public_id"] for row in rows] == sorted(
        [first_contract.public.public_id, second_contract.public.public_id]
    )
    taskset_source = (
        first_dir / "veritas_prime_operational" / "taskset.py"
    ).read_text(encoding="utf-8")
    assert 'return f"poc:{self.data.portable_public_id}"' in taskset_source


def test_replay_reward_is_exactly_portable_runtime_reward() -> None:
    contract = _typed_contract()
    requests = [
        PrimeReplayRequest(kind="action", name="prepare_order", arguments={}),
        PrimeReplayRequest(
            kind="action",
            name="approve_order",
            arguments={"order_id": "ORDER-001"},
        ),
        PrimeReplayRequest(
            kind="operation",
            name="submit",
            arguments={
                "conclusion": "Order approved after preparation.",
                "claimed_state": {"order.status": "approved"},
                "evidence_ids": ["record-001"],
                "confidence": 0.9,
            },
        ),
    ]

    replayed = replay_portable_requests(contract, requests, seed=17)
    assert replayed is not None
    assert replayed.reward is not None

    runtime = PortableOperationalRuntime(contract)
    runtime.reset(seed=17)
    runtime.step("prepare_order")
    runtime.step("approve_order", {"order_id": "ORDER-001"})
    direct = runtime.submit(
        EpisodeSubmission(
            conclusion="Order approved after preparation.",
            claimed_state={"order.status": "approved"},
            evidence_ids=["record-001"],
            confidence=0.9,
        ).model_dump(mode="json")
    )

    assert replayed.reward == direct.reward
    assert replayed.reward_components == direct.reward_components
    assert replayed.terminated == direct.terminated
    assert replayed.truncated == direct.truncated


def test_prime_conformance_replay_retains_each_actual_evaluator_result() -> None:
    contract = _typed_contract()
    requests = [
        PrimeReplayRequest(kind="action", name="prepare_order", arguments={}),
        PrimeReplayRequest(
            kind="action",
            name="approve_order",
            arguments={"order_id": "ORDER-001"},
        ),
        PrimeReplayRequest(
            kind="operation",
            name="submit",
            arguments={
                "conclusion": "Order approved after preparation.",
                "claimed_state": {"order.status": "approved"},
                "evidence_ids": ["record-001"],
                "confidence": 0.9,
            },
        ),
    ]

    trace = replay_portable_requests_for_conformance(contract, requests, seed=17)
    terminal = replay_portable_requests(contract, requests, seed=17)

    assert trace.adapter == "prime"
    assert trace.invocations == tuple(request.model_dump(mode="python") for request in requests)
    assert len(trace.step_results) == len(requests)
    assert trace.step_results[-1] == terminal
    assert trace.step_results[-1].reward_components is not None
    assert trace.step_results[-1].reward is not None


def test_generated_package_has_declared_remote_dependencies_and_no_local_paths(
    tmp_path: Path,
) -> None:
    output = tmp_path / "prime"
    result = build_prime_operational_package(output, contracts=[_typed_contract()])
    pyproject = (output / "pyproject.toml").read_text(encoding="utf-8")

    assert DEFAULT_VERITAS_REQUIREMENT in pyproject
    assert "verifiers>=0.2,<0.3" in pyproject
    assert "mcp>=1.24,<2" in pyproject
    assert "file://" not in pyproject
    assert "../" not in pyproject
    assert "-e " not in pyproject
    assert all(Path(item.path).is_absolute() is False for item in result.files)
    assert {
        "veritas_prime_operational/public_tasks.json",
        "veritas_prime_operational/private_contracts.json",
    }.issubset({item.path for item in result.files})


def test_generated_taskset_is_valid_python_and_keeps_reward_private(tmp_path: Path) -> None:
    output = tmp_path / "prime"
    build_prime_operational_package(output, contracts=[_typed_contract()])
    source = (output / "veritas_prime_operational" / "taskset.py").read_text(
        encoding="utf-8"
    )

    compile(source, "taskset.py", "exec")
    assert "PortableOperationalRuntime" in source
    assert "result.reward" in source
    assert "reward_components" not in source
    assert '"budget_status"' not in source
    assert 'getattr(mcp, "_tool_manager", None)' in source
    assert "manager.get_tool(tool_name)" in source
    assert 'await self._push_state(b"")' in source
    assert 'tool.parameters = copy.deepcopy(binding["input_schema"])' in source


def test_nonempty_output_directory_is_rejected_instead_of_packaging_stale_files(
    tmp_path: Path,
) -> None:
    output = tmp_path / "prime"
    output.mkdir()
    (output / "undeclared.txt").write_text("stale", encoding="utf-8")

    with pytest.raises(ValueError, match="output directory must be empty"):
        build_prime_operational_package(output, contracts=[_typed_contract()])
