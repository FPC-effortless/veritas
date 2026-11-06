from __future__ import annotations

import argparse
import asyncio
import json
import sys
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping, Sequence

from pydantic import ValidationError

from investigation_world.conformance import (
    EVALUATOR_PRIVATE_FIELDS,
    REQUIRED_SEMANTIC_FIELDS,
    build_semantic_snapshot,
    compare_adapter_semantics,
)
from investigation_world.exporters.harbor import (
    HarborExportConfig,
    RuntimeControl,
    export_harbor_package,
    replay_harbor_trajectory,
)
from investigation_world.exporters.hud import (
    HudOperationalAdapter,
    build_hud_operational_export,
)
from investigation_world.exporters.nemo import (
    NeMoOperationalAdapter,
    compile_nemo_surface,
    compile_nemo_task_row,
)
from investigation_world.exporters.openenv import compile_openenv_export
from investigation_world.exporters.prime import (
    DEFAULT_VERITAS_REQUIREMENT,
    PrimeReplayRequest,
    build_prime_operational_package,
    replay_portable_requests_for_conformance,
)
from investigation_world.mcp_compiler import compile_mcp_surface
from investigation_world.operational import OperationalEpisode
from investigation_world.portable_contract import (
    PortableOperationalContract,
    PortableVisibility,
    compile_operational_episode,
    serialize_portable_contract,
    serialize_public_contract,
)
from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableOperationalRuntime,
    PortableStepRequest,
)


class WorldPortabilityCLIError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _print_json(value: Any) -> None:
    sys.stdout.write(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    )


def _safe_validation_error(exc: ValidationError) -> str:
    parts: list[str] = []
    for item in exc.errors(include_url=False, include_input=False):
        location = ".".join(str(value) for value in item.get("loc", ())) or "$"
        parts.append(f"{location}:{item.get('type', 'validation_error')}")
    return ", ".join(parts) or "validation_error"


def _safe_exception_message(exc: Exception) -> str:
    """Return diagnostic identity without forwarding arbitrary evaluator-bearing text."""

    if isinstance(exc, ValidationError):
        return _safe_validation_error(exc)
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code:
        return code
    return type(exc).__name__


def _load_episode(path: Path) -> OperationalEpisode:
    try:
        return OperationalEpisode.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldPortabilityCLIError("EPISODE_READ_FAILED", str(path)) from exc
    except ValidationError as exc:
        raise WorldPortabilityCLIError(
            "EPISODE_INVALID",
            _safe_validation_error(exc),
        ) from exc


def _load_contract(path: Path) -> PortableOperationalContract:
    try:
        return PortableOperationalContract.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldPortabilityCLIError("CONTRACT_READ_FAILED", str(path)) from exc
    except ValidationError as exc:
        raise WorldPortabilityCLIError(
            "CONTRACT_INVALID",
            _safe_validation_error(exc),
        ) from exc


def _require_new_paths(*paths: Path | None) -> None:
    selected = [path.resolve() for path in paths if path is not None]
    if len(selected) != len(set(selected)):
        raise WorldPortabilityCLIError("OUTPUT_PATH_COLLISION", "output paths must be distinct")
    for path in selected:
        if path.exists():
            raise WorldPortabilityCLIError("OUTPUT_EXISTS", str(path))


def _write_new_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _require_empty_directory(path: Path) -> Path:
    root = path.resolve()
    if root.exists() and any(root.iterdir()):
        raise WorldPortabilityCLIError("OUTPUT_NOT_EMPTY", str(root))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _preflight_executable(contract: PortableOperationalContract) -> None:
    try:
        PortableOperationalRuntime(contract)
        compile_mcp_surface(contract.public)
    except Exception as exc:
        raise WorldPortabilityCLIError(
            "PORTABLE_RUNTIME_UNSUPPORTED_SEMANTICS",
            _safe_exception_message(exc),
        ) from exc


def _public_contract_summary(contract: PortableOperationalContract) -> dict[str, Any]:
    public = contract.public
    return {
        "schema_version": contract.schema_version,
        "public_contract_id": public.public_id,
        "identity": public.identity.model_dump(mode="json"),
        "objective": public.objective,
        "role": public.role,
        "permitted_systems": list(public.permitted_systems),
        "constraints": list(public.constraints),
        "success_description": public.success_description,
        "actions": [
            {
                "name": action.name,
                "kind": action.kind,
                "system": action.system,
                "interaction_mode": action.interaction_mode.value,
            }
            for action in public.actions
        ],
        "runtime_operations": [
            {
                "name": operation.name,
                "interaction_mode": operation.interaction_mode.value,
            }
            for operation in public.runtime.builtin_operations
        ],
        "deterministic_reset": public.runtime.deterministic_reset,
        "terminal_operation": public.runtime.termination.terminal_operation,
    }


def _private_identity_summary(contract: PortableOperationalContract) -> dict[str, Any]:
    return {
        "contract_id": contract.contract_id,
        "reset_identity": contract.private.reset_identity,
        "evaluator_semantics_id": contract.private.evaluator.semantics_id,
        "evaluator_entrypoint": contract.private.evaluator.entrypoint,
    }


def _partition_report(contract: PortableOperationalContract) -> dict[str, Any]:
    issues: list[str] = []
    if contract.public.visibility is not PortableVisibility.PUBLIC:
        issues.append("public.visibility")
    if contract.private.visibility is not PortableVisibility.EVALUATOR_PRIVATE:
        issues.append("private.visibility")
    if contract.private.semantic_state.visibility is not PortableVisibility.EVALUATOR_PRIVATE:
        issues.append("private.semantic_state.visibility")
    if contract.private.process.visibility is not PortableVisibility.EVALUATOR_PRIVATE:
        issues.append("private.process.visibility")
    if contract.private.budgets.visibility is not PortableVisibility.EVALUATOR_PRIVATE:
        issues.append("private.budgets.visibility")
    if contract.private.evaluator.visibility is not PortableVisibility.EVALUATOR_PRIVATE:
        issues.append("private.evaluator.visibility")
    if contract.public.state.state_snapshot_agent_visible:
        issues.append("public.state.state_snapshot_agent_visible")
    if contract.public.state.hidden_state_updates_agent_visible:
        issues.append("public.state.hidden_state_updates_agent_visible")

    try:
        compile_mcp_surface(contract.public)
    except Exception as exc:
        issues.append(f"public.mcp_surface:{type(exc).__name__}")

    try:
        public_document = json.loads(serialize_public_contract(contract).decode("utf-8"))
    except Exception as exc:
        issues.append(f"public.serialization:{type(exc).__name__}")
        public_document = {}
    if "private" in public_document:
        issues.append("serialized_public.private")
    if public_document.get("visibility") != PortableVisibility.PUBLIC.value:
        issues.append("serialized_public.visibility")

    return {
        "valid": not issues,
        "public_contract_id": contract.public.public_id,
        "private_section_in_public_serialization": "private" in public_document,
        "issues": issues,
    }


def _public_failure(result: Any) -> dict[str, Any] | None:
    failure = getattr(result, "failure", None)
    if failure is None:
        return None
    return {
        "code": getattr(failure.code, "value", failure.code),
        "retryable": failure.retryable,
    }


def _public_reset(result: Any) -> dict[str, Any]:
    return {
        "observation": result.observation,
        "state_digest": result.state_digest,
    }


def _public_step(result: Any) -> dict[str, Any]:
    return {
        "observation": result.observation,
        "reward": result.reward,
        "terminated": result.terminated,
        "truncated": result.truncated,
        "state_digest": result.state_digest,
        "failure": _public_failure(result),
    }


def _operator_reset(result: Any) -> dict[str, Any]:
    payload = _public_reset(result)
    payload["budget_status"] = result.budget_status.model_dump(mode="json")
    return payload


def _operator_step(result: Any) -> dict[str, Any]:
    payload = _public_step(result)
    payload["budget_status"] = result.budget_status.model_dump(mode="json")
    payload["reward_components"] = (
        result.reward_components.model_dump(mode="json")
        if result.reward_components is not None
        else None
    )
    return payload


def _load_vector(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise WorldPortabilityCLIError("VECTOR_READ_FAILED", str(path)) from exc
    except json.JSONDecodeError as exc:
        raise WorldPortabilityCLIError("VECTOR_JSON_INVALID", f"line {exc.lineno}") from exc
    if not isinstance(value, dict):
        raise WorldPortabilityCLIError("VECTOR_INVALID", "root must be an object")
    seed = value.get("seed", 0)
    actions = value.get("actions", [])
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise WorldPortabilityCLIError("VECTOR_INVALID", "seed must be an integer")
    if not isinstance(actions, list):
        raise WorldPortabilityCLIError("VECTOR_INVALID", "actions must be an array")
    normalized: list[dict[str, Any]] = []
    for index, call in enumerate(actions):
        if not isinstance(call, dict):
            raise WorldPortabilityCLIError("VECTOR_INVALID", f"actions[{index}] must be an object")
        kind = call.get("kind")
        name = call.get("name")
        arguments = call.get("arguments", {})
        if kind not in {"action", "operation"}:
            raise WorldPortabilityCLIError(
                "VECTOR_INVALID", f"actions[{index}].kind must be action or operation"
            )
        if not isinstance(name, str) or not name:
            raise WorldPortabilityCLIError("VECTOR_INVALID", f"actions[{index}].name")
        if not isinstance(arguments, dict):
            raise WorldPortabilityCLIError("VECTOR_INVALID", f"actions[{index}].arguments")
        normalized.append({"kind": kind, "name": name, "arguments": arguments})
    return {"seed": seed, "actions": normalized}


def _execute_direct(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    runtime = PortableOperationalRuntime(contract)
    reset = runtime.reset(seed=vector["seed"])
    steps = []
    for call in vector["actions"]:
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
        steps.append(result)
    return runtime, reset, steps


def _transport_name(surface: Any, kind: str, canonical_name: str) -> str:
    try:
        return next(
            item.transport_name
            for item in surface.catalog.provenance
            if getattr(item.source_kind, "value", item.source_kind) == kind
            and item.canonical_name == canonical_name
        )
    except StopIteration as exc:
        raise WorldPortabilityCLIError(
            "VECTOR_TOOL_UNSUPPORTED",
            f"{kind}:{canonical_name}",
        ) from exc


def _conformance_mapping(adapter: str) -> dict[str, str]:
    mapping = {
        "observations": f"{adapter}.native_observation",
        "state_digests": f"{adapter}.native_state_digest",
        "evidence": f"{adapter}.public_evidence+retrieval_observation",
        "action_parameters": f"{adapter}.typed_arguments+operator.transition_requirements",
        "action_outcomes": f"{adapter}.tool_result+operator.transition_contract",
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
    if set(mapping) != set(REQUIRED_SEMANTIC_FIELDS):
        raise WorldPortabilityCLIError("CONFORMANCE_MAPPING_BUG", adapter)
    return mapping


def _baseline_snapshot(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    _, reset, steps = _execute_direct(contract, vector)
    return build_semantic_snapshot(contract, vector["actions"], reset, steps)


def _harbor_snapshot(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    control = RuntimeControl(contract, seed=vector["seed"])
    reset = control.runtime.reset(seed=vector["seed"])
    results = []
    for call in vector["actions"]:
        tool = _transport_name(control.surface, call["kind"], call["name"])
        results.append(control.call_tool(tool, deepcopy(call["arguments"])))
    return build_semantic_snapshot(contract, vector["actions"], reset, results)


def _hud_snapshot(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    adapter = HudOperationalAdapter(contract)
    started = adapter.start(seed=vector["seed"], session_id="world-portability-cli")
    results = []
    for call in vector["actions"]:
        tool = _transport_name(adapter.surface, call["kind"], call["name"])
        results.append(adapter.call_tool(tool, deepcopy(call["arguments"])))
    return build_semantic_snapshot(contract, vector["actions"], started.reset, results)


def _nemo_snapshot(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    adapter = NeMoOperationalAdapter(
        contract.public,
        lambda: PortableOperationalRuntime(contract),
    )
    row = compile_nemo_task_row(contract.public, seed=vector["seed"])
    reset_observation, reset_info = asyncio.run(
        adapter.reset({"veritas": row["veritas"]}, "world-portability-cli")
    )
    if reset_observation is None:
        raise WorldPortabilityCLIError("CONFORMANCE_EXECUTION_FAILED", "nemo reset observation")
    reset = {
        "observation": json.loads(reset_observation),
        "state_digest": reset_info["veritas"]["state_digest"],
        "budget_status": reset_info["veritas"]["budget_status"],
    }
    results = []
    for index, call in enumerate(vector["actions"]):
        binding = next(
            (
                item
                for item in adapter.surface.tool_bindings
                if item.source_kind == call["kind"] and item.canonical_name == call["name"]
            ),
            None,
        )
        if binding is None:
            raise WorldPortabilityCLIError(
                "VECTOR_TOOL_UNSUPPORTED",
                f"{call['kind']}:{call['name']}",
            )
        native = asyncio.run(
            adapter.step(
                {
                    "output": [
                        {
                            "type": "function_call",
                            "call_id": f"world-cli-{index}",
                            "name": binding.transport_name,
                            "arguments": json.dumps(call["arguments"], sort_keys=True),
                        }
                    ]
                },
                {},
                "world-portability-cli",
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
    return build_semantic_snapshot(contract, vector["actions"], reset, results)


def _openenv_snapshot(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    export = compile_openenv_export(contract)
    trace = export.replay_for_conformance(vector["actions"], seed=vector["seed"])
    return build_semantic_snapshot(
        contract,
        trace.invocations,
        trace.reset_result,
        trace.step_results,
    )


def _prime_snapshot(contract: PortableOperationalContract, vector: Mapping[str, Any]):
    requests = [PrimeReplayRequest.model_validate(call) for call in vector["actions"]]
    trace = replay_portable_requests_for_conformance(
        contract,
        requests,
        seed=vector["seed"],
    )
    return build_semantic_snapshot(
        contract,
        trace.invocations,
        trace.reset_result,
        trace.step_results,
    )


def _adapter_snapshot(
    adapter: str,
    contract: PortableOperationalContract,
    vector: Mapping[str, Any],
):
    if adapter == "harbor":
        return _harbor_snapshot(contract, vector), ("trajectory_record", "mcp_surface_id")
    if adapter == "hud":
        return _hud_snapshot(contract, vector), ("session_id", "prompt")
    if adapter == "nemo":
        return _nemo_snapshot(contract, vector), ("environment_id", "task_identity")
    if adapter == "openenv":
        return _openenv_snapshot(contract, vector), ("done", "step_count")
    if adapter == "prime":
        return _prime_snapshot(contract, vector), ("package_id", "portable_public_id")
    raise WorldPortabilityCLIError("ADAPTER_UNSUPPORTED", adapter)


def _read_trajectory(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise WorldPortabilityCLIError("TRAJECTORY_READ_FAILED", str(path)) from exc
    if not lines:
        raise WorldPortabilityCLIError("TRAJECTORY_EMPTY", str(path))
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise WorldPortabilityCLIError("TRAJECTORY_INVALID", f"line {index}") from exc
        if not isinstance(record, dict):
            raise WorldPortabilityCLIError("TRAJECTORY_INVALID", f"line {index}")
        records.append(record)
    if records[0].get("kind") != "reset":
        raise WorldPortabilityCLIError("TRAJECTORY_INVALID", "first record must be reset")
    return records


def _command_compile(args: argparse.Namespace) -> int:
    _require_new_paths(args.output, args.public_output)
    episode = _load_episode(args.episode)
    try:
        contract = compile_operational_episode(episode)
    except Exception as exc:
        raise WorldPortabilityCLIError(
            "COMPILE_UNSUPPORTED_SEMANTICS",
            _safe_exception_message(exc),
        ) from exc
    _preflight_executable(contract)
    _write_new_file(args.output, serialize_portable_contract(contract) + b"\n")
    if args.public_output is not None:
        _write_new_file(args.public_output, serialize_public_contract(contract) + b"\n")
    _print_json(
        {
            "compiled": True,
            "output": str(args.output),
            "public_output": str(args.public_output) if args.public_output is not None else None,
            **_public_contract_summary(contract),
        }
    )
    return 0


def _command_inspect(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    payload = _public_contract_summary(contract)
    payload["partition"] = _partition_report(contract)
    if args.include_private_identities:
        payload["operator_identities"] = _private_identity_summary(contract)
    _print_json(payload)
    return 0


def _command_validate_partition(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    report = _partition_report(contract)
    _print_json(report)
    if not report["valid"]:
        raise WorldPortabilityCLIError(
            "PARTITION_INVALID",
            ",".join(report["issues"]),
        )
    return 0


def _command_run(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    vector = {"seed": args.seed, "actions": []}
    if args.vector is not None:
        vector = _load_vector(args.vector)
        if args.seed is not None:
            vector["seed"] = args.seed
    elif args.seed is None:
        vector["seed"] = 0
    try:
        runtime, reset, steps = _execute_direct(contract, vector)
    except Exception as exc:
        raise WorldPortabilityCLIError(
            "RUNTIME_UNSUPPORTED_SEMANTICS",
            _safe_exception_message(exc),
        ) from exc
    payload: dict[str, Any] = {
        "public_contract_id": contract.public.public_id,
        "seed": vector["seed"],
        "reset": _public_reset(reset),
        "steps": [_public_step(result) for result in steps],
        "final_public_state": runtime.public_state(),
    }
    if args.include_operator_metadata:
        payload["operator"] = {
            "reset": _operator_reset(reset),
            "steps": [_operator_step(result) for result in steps],
            "budget_status": runtime.budget_state().model_dump(mode="json"),
            **_private_identity_summary(contract),
        }
    _print_json(payload)
    return 0


def _command_export(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    _preflight_executable(contract)
    output = args.output
    try:
        if args.adapter == "nemo":
            root = _require_empty_directory(output)
            surface = compile_nemo_surface(contract.public)
            row = compile_nemo_task_row(contract.public, seed=args.seed)
            (root / "task-row.json").write_bytes(_json_bytes(row))
            metadata = surface.metadata(seed=args.seed)
            (root / "metadata.json").write_bytes(_json_bytes(metadata))
            result: dict[str, Any] = {
                "adapter": "nemo",
                "output_dir": str(root),
                "public_contract_id": contract.public.public_id,
                "environment_id": surface.environment_id,
                "mcp_surface_id": surface.mcp_surface.surface_id,
            }
        elif args.adapter == "openenv":
            root = _require_empty_directory(output)
            export = compile_openenv_export(contract)
            payload = {
                "export_id": export.export_id,
                "environment_name": export.environment_name,
                "public_contract_id": export.public_contract_id,
                "task_id": export.task_id,
                "world_id": export.world_id,
                "episode_id": export.episode_id,
                "domain": export.domain,
                "mcp_surface_id": export.mcp_surface.surface_id,
                "tools": export.mcp_surface.catalog.tools_list_result(),
            }
            (root / "openenv-export.json").write_bytes(_json_bytes(payload))
            result = {"adapter": "openenv", "output_dir": str(root), **payload}
            result.pop("tools", None)
        elif args.adapter == "hud":
            hud_built = build_hud_operational_export(contract, output)
            result = {
                "adapter": "hud",
                "output_dir": hud_built.output_dir,
                "public_contract_id": hud_built.public_contract_id,
                "public_package_id": hud_built.public_package_id,
                "export_id": hud_built.export_id,
            }
        elif args.adapter == "prime":
            prime_built = build_prime_operational_package(
                output,
                contracts=[contract],
                veritas_requirement=args.veritas_requirement,
            )
            result = {
                "adapter": "prime",
                "output_dir": prime_built.output_dir,
                "public_contract_id": contract.public.public_id,
                "package_id": prime_built.package_id,
                "export_id": prime_built.export_id,
            }
        elif args.adapter == "harbor":
            missing = [
                name
                for name in ("task_name", "agent_image", "runtime_image")
                if getattr(args, name) is None
            ]
            if missing:
                raise WorldPortabilityCLIError(
                    "HARBOR_CONFIGURATION_REQUIRED",
                    ",".join(missing),
                )
            config = HarborExportConfig(
                task_name=args.task_name,
                agent_image=args.agent_image,
                runtime_image=args.runtime_image,
                verifier_image=args.verifier_image,
                seed=args.seed,
            )
            harbor_built = export_harbor_package(contract, output, config)
            result = {
                "adapter": "harbor",
                "output_dir": harbor_built.output_dir,
                "public_contract_id": harbor_built.public_contract_id,
                "package_id": harbor_built.package_id,
                "mcp_surface_id": harbor_built.mcp_surface_id,
            }
        else:
            raise WorldPortabilityCLIError("ADAPTER_UNSUPPORTED", args.adapter)
    except WorldPortabilityCLIError:
        raise
    except Exception as exc:
        raise WorldPortabilityCLIError(
            "EXPORT_UNSUPPORTED_SEMANTICS",
            _safe_exception_message(exc),
        ) from exc
    _print_json(result)
    return 0


def _command_conformance(args: argparse.Namespace) -> int:
    contract = _load_contract(args.contract)
    vector = _load_vector(args.vector)
    try:
        expected = _baseline_snapshot(contract, vector)
        actual, generated = _adapter_snapshot(args.adapter, contract, vector)
        report = compare_adapter_semantics(
            expected,
            actual,
            test_vector=vector,
            mapped_fields=_conformance_mapping(args.adapter),
            generated_fields=generated,
            excluded_private_fields=EVALUATOR_PRIVATE_FIELDS,
        )
    except WorldPortabilityCLIError:
        raise
    except Exception as exc:
        raise WorldPortabilityCLIError(
            "CONFORMANCE_EXECUTION_FAILED",
            _safe_exception_message(exc),
        ) from exc
    payload = report.model_dump(mode="json")
    payload["adapter"] = args.adapter
    payload["passed"] = report.passed
    payload["public_contract_id"] = contract.public.public_id
    _print_json(payload)
    if not report.passed:
        raise WorldPortabilityCLIError(
            "CONFORMANCE_FAILED",
            ",".join(report.semantic_losses),
        )
    return 0


def _command_trajectory(args: argparse.Namespace) -> int:
    records = _read_trajectory(args.trajectory)
    header = records[0]
    payload: dict[str, Any] = {
        "trajectory": str(args.trajectory),
        "public_contract_id": header.get("public_contract_id"),
        "mcp_surface_id": header.get("surface_id"),
        "seed": header.get("seed"),
        "records": len(records),
        "tool_calls": sum(record.get("kind") == "tool_call" for record in records),
    }
    if args.include_private_identities:
        payload["contract_id"] = header.get("contract_id")
    if args.contract is not None:
        contract = _load_contract(args.contract)
        expected_surface = compile_mcp_surface(contract.public).surface_id
        identity_match = (
            header.get("public_contract_id") == contract.public.public_id
            and header.get("contract_id") == contract.contract_id
            and header.get("surface_id") == expected_surface
        )
        payload["identity_match"] = identity_match
        if not identity_match:
            _print_json(payload)
            raise WorldPortabilityCLIError(
                "TRAJECTORY_IDENTITY_MISMATCH",
                "contract/public/surface identity mismatch",
            )
        if args.reverify:
            try:
                verified = replay_harbor_trajectory(contract, records)
            except Exception as exc:
                raise WorldPortabilityCLIError(
                    "REVERIFICATION_FAILED",
                    _safe_exception_message(exc),
                ) from exc
            payload["reverified"] = True
            payload["replayed_tool_calls"] = verified.replayed_tool_calls
            if args.include_operator_metadata:
                payload["operator"] = {
                    "reward": verified.reward,
                    "reward_components": verified.reward_components,
                    **_private_identity_summary(contract),
                }
    elif args.reverify:
        raise WorldPortabilityCLIError(
            "CONTRACT_REQUIRED",
            "--reverify requires --contract",
        )
    _print_json(payload)
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Standalone Veritas operational-world portability tooling"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    compile_parser = sub.add_parser(
        "compile",
        help="compile an OperationalEpisode JSON document to PortableOperationalContract",
    )
    compile_parser.add_argument("--episode", type=Path, required=True)
    compile_parser.add_argument("--output", type=Path, required=True)
    compile_parser.add_argument("--public-output", type=Path)
    compile_parser.set_defaults(handler=_command_compile)

    inspect_parser = sub.add_parser("inspect", help="inspect a portable contract safely")
    inspect_parser.add_argument("--contract", type=Path, required=True)
    inspect_parser.add_argument("--include-private-identities", action="store_true")
    inspect_parser.set_defaults(handler=_command_inspect)

    partition_parser = sub.add_parser(
        "validate-partition",
        help="validate the public/evaluator-private partition",
    )
    partition_parser.add_argument("--contract", type=Path, required=True)
    partition_parser.set_defaults(handler=_command_validate_partition)

    run_parser = sub.add_parser("run", help="reset and run the generic portable runtime")
    run_parser.add_argument("--contract", type=Path, required=True)
    run_parser.add_argument("--vector", type=Path)
    run_parser.add_argument("--seed", type=int)
    run_parser.add_argument("--include-operator-metadata", action="store_true")
    run_parser.set_defaults(handler=_command_run)

    export_parser = sub.add_parser("export", help="export to a supported runtime adapter")
    export_parser.add_argument(
        "--adapter",
        choices=("nemo", "openenv", "hud", "prime", "harbor"),
        required=True,
    )
    export_parser.add_argument("--contract", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--seed", type=int, default=0)
    export_parser.add_argument("--veritas-requirement", default=DEFAULT_VERITAS_REQUIREMENT)
    export_parser.add_argument("--task-name")
    export_parser.add_argument("--agent-image")
    export_parser.add_argument("--runtime-image")
    export_parser.add_argument("--verifier-image")
    export_parser.set_defaults(handler=_command_export)

    conformance_parser = sub.add_parser(
        "conformance",
        help="run fail-closed adapter semantic conformance when public trace APIs permit it",
    )
    conformance_parser.add_argument(
        "--adapter",
        choices=("nemo", "hud", "harbor", "openenv", "prime"),
        required=True,
    )
    conformance_parser.add_argument("--contract", type=Path, required=True)
    conformance_parser.add_argument("--vector", type=Path, required=True)
    conformance_parser.set_defaults(handler=_command_conformance)

    trajectory_parser = sub.add_parser(
        "trajectory",
        help="inspect Harbor trajectory and reverification identities",
    )
    trajectory_parser.add_argument("--trajectory", type=Path, required=True)
    trajectory_parser.add_argument("--contract", type=Path)
    trajectory_parser.add_argument("--reverify", action="store_true")
    trajectory_parser.add_argument("--include-private-identities", action="store_true")
    trajectory_parser.add_argument("--include-operator-metadata", action="store_true")
    trajectory_parser.set_defaults(handler=_command_trajectory)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except WorldPortabilityCLIError as exc:
        sys.stderr.write(f"error[{exc.code}]: {exc.message}\n")
        return 2
    except Exception as exc:  # last-resort fail-closed boundary
        sys.stderr.write(
            f"error[UNEXPECTED_FAILURE]: {_safe_exception_message(exc)}\n"
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
