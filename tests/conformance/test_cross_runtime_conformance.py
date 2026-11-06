from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from pathlib import Path

from investigation_world.conformance import (
    EVALUATOR_PRIVATE_FIELDS,
    REQUIRED_SEMANTIC_FIELDS,
    AdapterConformanceReport,
    build_semantic_snapshot,
    compare_adapter_semantics,
)
from investigation_world.exporters.harbor import RuntimeControl
from investigation_world.exporters.hud import HudOperationalAdapter
from investigation_world.exporters.nemo import (
    NeMoOperationalAdapter,
    compile_nemo_task_row,
)
from investigation_world.exporters.openenv import compile_openenv_export
from investigation_world.exporters.prime import (
    PrimeReplayRequest,
    replay_portable_requests_for_conformance,
)
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
    compile_operational_episode,
)
from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableOperationalRuntime,
    PortableStepRequest,
)

VECTOR_PATH = Path(__file__).parent / "fixtures" / "canonical_vector.json"
VECTOR = json.loads(VECTOR_PATH.read_text(encoding="utf-8"))


def _episode() -> OperationalEpisode:
    """Synthetic public-safe episode; no benchmark row or sealed evaluator data is reused."""

    return OperationalEpisode(
        episode_id="conformance-episode-001",
        world_id="conformance-world-001",
        task=TaskContract(
            task_id="conformance-task-001",
            world_id="conformance-world-001",
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
            metadata={"fixture": "cross-runtime-conformance"},
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
            task_id="conformance-task-001",
            initial_state={
                "order.status": "pending",
                "order.risk": 0,
                "synthetic.private": "CONFORMANCE-PRIVATE-ONLY",
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
                    observable_result={"accepted": True, "receipt": "approval-recorded"},
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
            max_cost=10,
            max_tool_calls=8,
            metadata={"synthetic_expected": "CONFORMANCE-PRIVATE-ANSWER"},
        ),
        metadata={"public_episode": True},
    )


def _contract() -> PortableOperationalContract:
    return compile_operational_episode(_episode())


def _run_portable(runtime: PortableOperationalRuntime, contract: PortableOperationalContract):
    reset = runtime.reset(seed=VECTOR["seed"])
    results = []
    for call in VECTOR["actions"]:
        arguments = deepcopy(call["arguments"])
        if call["kind"] == "operation" and call["name"] == "submit":
            result = runtime.submit(arguments)
        else:
            result = runtime.step(
                PortableStepRequest(
                    kind=PortableInvocationKind(call["kind"]),
                    name=call["name"],
                    arguments=arguments,
                )
            )
        assert result.failure is None
        results.append(result)
    return build_semantic_snapshot(contract, VECTOR["actions"], reset, results)


def _transport_name(surface, kind: str, canonical_name: str) -> str:
    return next(
        item.transport_name
        for item in surface.catalog.provenance
        if getattr(item.source_kind, "value", item.source_kind) == kind
        and item.canonical_name == canonical_name
    )


def _mapping(adapter: str) -> dict[str, str]:
    public = {
        "observations": f"{adapter}.native_observation",
        "state_digests": f"{adapter}.native_state_digest",
        "evidence": f"{adapter}.public_evidence+retrieval_observation",
        "action_parameters": f"{adapter}.typed_tool_arguments+operator.transition_requirements",
        "action_outcomes": f"{adapter}.tool_result+operator.transition_observable_result",
        "termination": f"{adapter}.terminated+public.termination_contract",
        "truncation": f"{adapter}.truncated",
        "budgets": f"{adapter}.operator.budget_contract+budget_status",
        "invariants": f"{adapter}.operator.private.semantic_state.invariants",
        "target_assertions": f"{adapter}.operator.private.semantic_state.target_assertions",
        "process_requirements": f"{adapter}.operator.private.process",
        "evidence_requirements": f"{adapter}.operator.private.required_evidence_ids",
        "reward_weights": f"{adapter}.operator.private.evaluator.reward",
        "verifier_components": f"{adapter}.operator.verifier.reward_components",
        "aggregate_reward": f"{adapter}.native_or_operator.aggregate_reward",
    }
    assert set(public) == set(REQUIRED_SEMANTIC_FIELDS)
    return public


def _report(expected, actual, adapter: str, generated_fields=()) -> AdapterConformanceReport:
    return compare_adapter_semantics(
        expected,
        actual,
        test_vector=VECTOR,
        mapped_fields=_mapping(adapter),
        generated_fields=generated_fields,
    )


def _nemo_snapshot(contract: PortableOperationalContract):
    adapter = NeMoOperationalAdapter(
        contract.public,
        lambda: PortableOperationalRuntime(contract),
    )
    row = compile_nemo_task_row(contract.public, seed=VECTOR["seed"])
    reset_observation, reset_info = asyncio.run(
        adapter.reset({"veritas": row["veritas"]}, "conformance")
    )
    assert reset_observation is not None
    reset = {
        "observation": json.loads(reset_observation),
        "state_digest": reset_info["veritas"]["state_digest"],
        "budget_status": reset_info["veritas"]["budget_status"],
    }
    results = []
    for index, call in enumerate(VECTOR["actions"]):
        binding = next(
            item
            for item in adapter.surface.tool_bindings
            if item.source_kind == call["kind"] and item.canonical_name == call["name"]
        )
        native = asyncio.run(
            adapter.step(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": f"call-{index}",
                            "name": binding.transport_name,
                            "arguments": json.dumps(call["arguments"], sort_keys=True),
                        }
                    ]
                },
                {},
                "conformance",
            )
        )
        tool_output = json.loads(native[4]["tool_outputs"][0]["output"])
        results.append(
            {
                "observation": tool_output,
                "reward": native[1] if call["name"] == "submit" else None,
                "reward_components": native[4]["veritas"].get("reward_components"),
                "terminated": native[2],
                "truncated": native[3],
                "state_digest": native[4]["veritas"]["state_digest"],
                "budget_status": native[4]["veritas"]["budget_status"],
            }
        )
    runtime = adapter._sessions["conformance"].runtime
    assert isinstance(runtime, PortableOperationalRuntime)
    return build_semantic_snapshot(runtime._contract, VECTOR["actions"], reset, results)


def _openenv_snapshot(contract: PortableOperationalContract):
    export = compile_openenv_export(contract)
    trace = export.replay_for_conformance(VECTOR["actions"], seed=VECTOR["seed"])
    return build_semantic_snapshot(
        contract,
        trace.invocations,
        trace.reset_result,
        trace.step_results,
    )


def _hud_snapshot(contract: PortableOperationalContract):
    adapter = HudOperationalAdapter(contract)
    started = adapter.start(seed=VECTOR["seed"], session_id="conformance")
    results = []
    for call in VECTOR["actions"]:
        tool = _transport_name(adapter.surface, call["kind"], call["name"])
        results.append(adapter.call_tool(tool, deepcopy(call["arguments"])))
    return build_semantic_snapshot(
        adapter.runtime._contract,
        VECTOR["actions"],
        started.reset,
        results,
    )


def _harbor_snapshot(contract: PortableOperationalContract):
    control = RuntimeControl(contract, seed=VECTOR["seed"])
    # RuntimeControl resets in its constructor. Capture the equivalent reset result before any
    # tool call; the second reset is deterministic and keeps the adapter at the same initial state.
    reset = control.runtime.reset(seed=VECTOR["seed"])
    results = []
    for call in VECTOR["actions"]:
        tool = _transport_name(control.surface, call["kind"], call["name"])
        results.append(control.call_tool(tool, deepcopy(call["arguments"])))
    return build_semantic_snapshot(control.contract, VECTOR["actions"], reset, results)


def _prime_snapshot(
    contract: PortableOperationalContract,
):
    requests = [PrimeReplayRequest(**call) for call in VECTOR["actions"]]
    trace = replay_portable_requests_for_conformance(
        contract,
        requests,
        seed=VECTOR["seed"],
    )
    return build_semantic_snapshot(
        contract,
        trace.invocations,
        trace.reset_result,
        trace.step_results,
    )


def test_all_c_wave_runtime_adapters_preserve_one_canonical_semantics() -> None:
    contract = _contract()
    expected = _run_portable(PortableOperationalRuntime(contract), contract)

    snapshots = {
        "nemo": (_nemo_snapshot(contract), ("environment_id", "task_identity")),
        "openenv": (_openenv_snapshot(contract), ("done", "step_count")),
        "hud": (_hud_snapshot(contract), ("session_id", "prompt")),
        "harbor": (_harbor_snapshot(contract), ("trajectory_record", "mcp_surface_id")),
        "prime": (
            _prime_snapshot(contract),
            ("package_id", "portable_public_id"),
        ),
    }

    reports = {
        name: _report(expected, snapshot, name, generated)
        for name, (snapshot, generated) in snapshots.items()
    }

    for name, report in reports.items():
        assert report.passed, f"{name} semantic losses: {report.semantic_losses}"
        assert report.unsupported_fields == ()
        assert set(report.preserved_fields) == set(REQUIRED_SEMANTIC_FIELDS)
        assert report.excluded_private_fields == tuple(sorted(EVALUATOR_PRIVATE_FIELDS))
        assert len(report.test_vector_hash) == 64


def test_report_serializes_exact_required_accounting_fields() -> None:
    contract = _contract()
    expected = _run_portable(PortableOperationalRuntime(contract), contract)
    report = _report(expected, expected, "direct")

    assert set(report.model_dump(mode="json")) == {
        "mapped_fields",
        "preserved_fields",
        "generated_fields",
        "excluded_private_fields",
        "unsupported_fields",
        "semantic_losses",
        "test_vector_hash",
    }
