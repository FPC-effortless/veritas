from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import PrivateAttr

from investigation_world.mcp_compiler import (
    MCPCompiledSurface,
    MCPDispatchMode,
    compile_mcp_surface,
)
from investigation_world.mcp_compiler.models import thaw_json
from investigation_world.portable_contract import PortablePublicContract
from investigation_world.portable_runtime import (
    PortableRuntimeProtocol,
    PortableStepRequest,
    PortableStepResult,
)


class NeMoOperationalExportError(ValueError):
    """Fail-closed error raised before portable runtime semantics are invoked."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True, slots=True)
class NeMoToolBinding:
    transport_name: str
    canonical_name: str
    canonical_identity: str
    source_kind: str
    interaction_mode: str
    dispatch_mode: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    schema_digest: str

    def function_tool(self, *, terminal: bool = False) -> dict[str, Any]:
        description = self.description
        if terminal:
            description = f"{description} This is the terminal operation for the episode."
        return {
            "type": "function",
            "name": self.transport_name,
            "description": description,
            "parameters": thaw_json(self.input_schema),
        }

    def metadata(self) -> dict[str, Any]:
        return {
            "transport_name": self.transport_name,
            "canonical_name": self.canonical_name,
            "canonical_identity": self.canonical_identity,
            "source_kind": self.source_kind,
            "interaction_mode": self.interaction_mode,
            "dispatch_mode": self.dispatch_mode,
            "input_schema": thaw_json(self.input_schema),
            "output_schema": thaw_json(self.output_schema),
            "schema_digest": self.schema_digest,
        }


@dataclass(frozen=True, slots=True)
class NeMoOperationalSurface:
    public_contract: PortablePublicContract
    mcp_surface: MCPCompiledSurface
    environment_id: str
    tool_bindings: tuple[NeMoToolBinding, ...]
    terminal_tool_name: str

    @property
    def public_contract_id(self) -> str:
        return self.public_contract.public_id

    def function_tools(self) -> list[dict[str, Any]]:
        return [
            binding.function_tool(terminal=binding.transport_name == self.terminal_tool_name)
            for binding in self.tool_bindings
        ]

    def metadata(self, *, seed: int) -> dict[str, Any]:
        public = self.public_contract
        return {
            "adapter": "veritas-native-nemo-gymnasium-v1",
            "environment_id": self.environment_id,
            "public_contract_id": public.public_id,
            "schema_version": public.schema_version,
            "seed": seed,
            "task_identity": thaw_json(public.identity.model_dump(mode="python")),
            "task_metadata": thaw_json(public.task_metadata),
            "episode_metadata": thaw_json(public.episode_metadata),
            "runtime": {
                "stateful": public.runtime.stateful,
                "deterministic_reset": public.runtime.deterministic_reset,
                "terminal_operation": public.runtime.termination.terminal_operation,
            },
            "mcp_surface_id": self.mcp_surface.surface_id,
            "terminal_tool_name": self.terminal_tool_name,
            "tool_bindings": [binding.metadata() for binding in self.tool_bindings],
        }


def compile_nemo_surface(public_contract: PortablePublicContract) -> NeMoOperationalSurface:
    """Compile public portable semantics into NeMo Responses API function tools.

    The shared MCP compiler is used only for schema-safe transport naming and exact schema
    preservation. Runtime execution remains direct through PortableRuntimeProtocol.
    """

    if not isinstance(public_contract, PortablePublicContract):
        raise NeMoOperationalExportError(
            "PUBLIC_CONTRACT_REQUIRED",
            (
                "native NeMo export accepts PortablePublicContract only; "
                "evaluator-private fields are forbidden"
            ),
        )

    mcp_surface = compile_mcp_surface(public_contract)
    tools_by_name = {tool.name: tool for tool in mcp_surface.catalog.tools}
    provenance_by_name = {
        item.transport_name: item for item in mcp_surface.catalog.provenance
    }
    bindings: list[NeMoToolBinding] = []
    terminal_tool_name: str | None = None

    for target in mcp_surface.dispatch:
        tool = tools_by_name[target.tool_name]
        provenance = provenance_by_name[target.tool_name]
        binding = NeMoToolBinding(
            transport_name=target.tool_name,
            canonical_name=target.canonical_name,
            canonical_identity=target.canonical_identity,
            source_kind=target.source_kind.value,
            interaction_mode=provenance.interaction_mode,
            dispatch_mode=target.dispatch_mode.value,
            description=tool.description,
            input_schema=thaw_json(tool.input_schema),
            output_schema=thaw_json(tool.output_schema),
            schema_digest=provenance.schema_digest,
        )
        bindings.append(binding)
        if target.dispatch_mode is MCPDispatchMode.SUBMIT:
            if terminal_tool_name is not None:
                raise NeMoOperationalExportError(
                    "MULTIPLE_TERMINAL_TOOLS",
                    "portable public surface compiled more than one terminal operation",
                )
            terminal_tool_name = target.tool_name

    if terminal_tool_name is None:
        raise NeMoOperationalExportError(
            "TERMINAL_TOOL_MISSING",
            "portable public surface does not expose the configured terminal operation",
        )

    bindings.sort(key=lambda item: item.transport_name)
    return NeMoOperationalSurface(
        public_contract=public_contract,
        mcp_surface=mcp_surface,
        environment_id=f"veritas:nemo-gymnasium:{public_contract.public_id}",
        tool_bindings=tuple(bindings),
        terminal_tool_name=terminal_tool_name,
    )


def _default_input_messages(surface: NeMoOperationalSurface) -> list[dict[str, str]]:
    public = surface.public_contract
    systems = ", ".join(public.permitted_systems) if public.permitted_systems else "none"
    constraints = "\n".join(f"- {item}" for item in public.constraints) or "- none"
    system = (
        f"Role: {public.role}\n"
        f"Permitted systems: {systems}\n"
        f"Constraints:\n{constraints}\n"
        "Use only the provided environment tools for operational actions. "
        f"Complete the episode by calling terminal tool {surface.terminal_tool_name}."
    )
    user = (
        f"Objective: {public.objective}\n"
        f"Success condition: {public.success_description}"
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def compile_nemo_task_row(
    public_contract: PortablePublicContract,
    *,
    seed: int = 0,
    input_messages: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a NeMo Gym input row for ``gymnasium_agent``.

    ``veritas`` is top-level metadata, so GymnasiumServer reset/step receives it via
    ``body.model_extra`` while ``responses_create_params`` remains model-facing.
    """

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise NeMoOperationalExportError("INVALID_SEED", "seed must be an integer")
    surface = compile_nemo_surface(public_contract)
    messages = (
        _default_input_messages(surface)
        if input_messages is None
        else [thaw_json(dict(message)) for message in input_messages]
    )
    return {
        "responses_create_params": {
            "input": messages,
            "tools": surface.function_tools(),
            "tool_choice": "auto",
            "parallel_tool_calls": False,
        },
        "veritas": surface.metadata(seed=seed),
    }


@dataclass(slots=True)
class _RuntimeSession:
    runtime: PortableRuntimeProtocol
    seed: int


def _canonical_json_text(value: Any) -> str:
    return json.dumps(
        thaw_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _read_field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _response_function_calls(action: Any) -> list[Any]:
    output = _read_field(action, "output")
    if output is None:
        raise NeMoOperationalExportError(
            "INVALID_NEMO_RESPONSE",
            "step action must expose a response.output sequence",
        )
    if not isinstance(output, Sequence) or isinstance(output, (str, bytes, bytearray)):
        raise NeMoOperationalExportError(
            "INVALID_NEMO_RESPONSE",
            "response.output must be a sequence",
        )
    return [item for item in output if _read_field(item, "type") == "function_call"]


def _parse_arguments(call: Any) -> dict[str, Any]:
    raw = _read_field(call, "arguments", {})
    if isinstance(raw, Mapping):
        return dict(raw)
    if not isinstance(raw, str):
        raise NeMoOperationalExportError(
            "INVALID_TOOL_ARGUMENTS",
            "NeMo function-call arguments must be a JSON object string",
        )
    try:
        decoded = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise NeMoOperationalExportError(
            "INVALID_TOOL_ARGUMENTS",
            f"function-call arguments are not valid JSON: {exc.msg}",
        ) from exc
    if not isinstance(decoded, dict):
        raise NeMoOperationalExportError(
            "INVALID_TOOL_ARGUMENTS",
            "function-call arguments must decode to a JSON object",
        )
    return decoded


def _failure_output(result: PortableStepResult) -> Any:
    if result.failure is None:
        return result.observation
    return {
        "observation": result.observation,
        "failure": result.failure.model_dump(mode="json"),
    }


class NeMoOperationalAdapter:
    """Session-safe adapter implementing NeMo Gymnasium ``reset``/``step`` semantics."""

    def __init__(
        self,
        public_contract: PortablePublicContract,
        runtime_factory: Callable[[], PortableRuntimeProtocol],
    ) -> None:
        self.surface = compile_nemo_surface(public_contract)
        self._runtime_factory = runtime_factory
        self._sessions: dict[str, _RuntimeSession] = {}

    @staticmethod
    def _session_key(session_id: str | None) -> str:
        return session_id if session_id is not None else "__default__"

    def _new_runtime(self) -> PortableRuntimeProtocol:
        runtime = self._runtime_factory()
        if not isinstance(runtime, PortableRuntimeProtocol):
            raise NeMoOperationalExportError(
                "PORTABLE_RUNTIME_REQUIRED",
                "runtime_factory must return PortableRuntimeProtocol",
            )
        return runtime

    def _validate_reset_metadata(self, metadata: Mapping[str, Any]) -> int:
        veritas = metadata.get("veritas", {})
        if veritas is None:
            veritas = {}
        if not isinstance(veritas, Mapping):
            raise NeMoOperationalExportError(
                "INVALID_TASK_METADATA",
                "top-level veritas metadata must be an object",
            )
        contract_id = veritas.get("public_contract_id")
        if contract_id is not None and contract_id != self.surface.public_contract_id:
            raise NeMoOperationalExportError(
                "TASK_CONTRACT_MISMATCH",
                "NeMo row public_contract_id does not match this resources server",
            )
        environment_id = veritas.get("environment_id")
        if environment_id is not None and environment_id != self.surface.environment_id:
            raise NeMoOperationalExportError(
                "ENVIRONMENT_ID_MISMATCH",
                "NeMo row environment_id does not match this resources server",
            )
        seed = veritas.get("seed", 0)
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise NeMoOperationalExportError("INVALID_SEED", "veritas.seed must be an integer")
        return seed

    def _runtime_info(
        self,
        runtime: PortableRuntimeProtocol,
        *,
        result: PortableStepResult | None = None,
    ) -> dict[str, Any]:
        info: dict[str, Any] = {
            "adapter": "veritas-native-nemo-gymnasium-v1",
            "environment_id": self.surface.environment_id,
            "public_contract_id": self.surface.public_contract_id,
            "task_identity": thaw_json(
                self.surface.public_contract.identity.model_dump(mode="python")
            ),
            "state": thaw_json(runtime.public_state()),
            "state_digest": runtime.state_digest(),
            "budget_status": runtime.budget_state().model_dump(mode="json"),
        }
        if result is not None:
            if result.reward_components is not None:
                info["reward_components"] = result.reward_components.model_dump(mode="json")
            if result.failure is not None:
                info["failure"] = result.failure.model_dump(mode="json")
        return info

    async def reset(
        self,
        metadata: Mapping[str, Any] | None,
        session_id: str | None = None,
    ) -> tuple[str | None, dict[str, Any]]:
        metadata = metadata or {}
        seed = self._validate_reset_metadata(metadata)
        runtime = self._new_runtime()
        reset_result = runtime.reset(seed=seed)
        self._sessions[self._session_key(session_id)] = _RuntimeSession(
            runtime=runtime,
            seed=seed,
        )
        return _canonical_json_text(reset_result.observation), {
            "veritas": {
                "adapter": "veritas-native-nemo-gymnasium-v1",
                "environment_id": self.surface.environment_id,
                "public_contract_id": self.surface.public_contract_id,
                "task_identity": thaw_json(
                    self.surface.public_contract.identity.model_dump(mode="python")
                ),
                "task_metadata": thaw_json(self.surface.public_contract.task_metadata),
                "episode_metadata": thaw_json(self.surface.public_contract.episode_metadata),
                "seed": seed,
                "state": thaw_json(runtime.public_state()),
                "state_digest": reset_result.state_digest,
                "budget_status": reset_result.budget_status.model_dump(mode="json"),
            }
        }

    def _adapter_failure(
        self,
        runtime: PortableRuntimeProtocol,
        *,
        code: str,
        detail: str,
        call_id: str | None = None,
        truncated: bool = False,
    ) -> tuple[str | None, float, bool, bool, dict[str, Any]]:
        info = {
            "veritas": {
                **self._runtime_info(runtime),
                "adapter_failure": {"code": code, "message": detail},
            }
        }
        if call_id:
            info["tool_outputs"] = [
                {
                    "call_id": call_id,
                    "output": _canonical_json_text(
                        {"failure": {"code": code, "message": detail}}
                    ),
                }
            ]
        return None, 0.0, False, truncated, info

    async def step(
        self,
        action: Any,
        metadata: Mapping[str, Any] | None,
        session_id: str | None = None,
    ) -> tuple[str | None, float, bool, bool, dict[str, Any]]:
        del metadata  # task identity is bound at reset; step metadata must not change semantics.
        session = self._sessions.get(self._session_key(session_id))
        if session is None:
            raise NeMoOperationalExportError(
                "SESSION_NOT_RESET",
                "reset must succeed before step for this NeMo session",
            )
        runtime = session.runtime

        try:
            calls = _response_function_calls(action)
        except NeMoOperationalExportError as exc:
            return self._adapter_failure(
                runtime,
                code=exc.code,
                detail=exc.detail,
                truncated=True,
            )
        if not calls:
            return self._adapter_failure(
                runtime,
                code="TOOL_CALL_REQUIRED",
                detail="portable operational episodes require an exported tool call",
                truncated=True,
            )
        if len(calls) != 1:
            return self._adapter_failure(
                runtime,
                code="PARALLEL_TOOL_CALLS_UNSUPPORTED",
                detail="exactly one function call may map to each portable runtime step",
                truncated=True,
            )

        call = calls[0]
        call_id = _read_field(call, "call_id")
        tool_name = _read_field(call, "name")
        if not isinstance(call_id, str) or not call_id:
            return self._adapter_failure(
                runtime,
                code="INVALID_CALL_ID",
                detail="NeMo function call must carry a non-empty call_id",
                truncated=True,
            )
        if not isinstance(tool_name, str) or not tool_name:
            return self._adapter_failure(
                runtime,
                code="INVALID_TOOL_NAME",
                detail="NeMo function call must carry a non-empty tool name",
                call_id=call_id,
            )

        target = self.surface.mcp_surface.dispatch_by_tool_name().get(tool_name)
        if target is None:
            return self._adapter_failure(
                runtime,
                code="UNKNOWN_TOOL",
                detail="tool name is not part of this portable public contract",
                call_id=call_id,
            )
        try:
            arguments = _parse_arguments(call)
        except NeMoOperationalExportError as exc:
            return self._adapter_failure(
                runtime,
                code=exc.code,
                detail=exc.detail,
                call_id=call_id,
            )

        if target.dispatch_mode is MCPDispatchMode.SUBMIT:
            result = runtime.submit(arguments)
        else:
            result = runtime.step(
                PortableStepRequest(
                    kind=target.invocation_kind,
                    name=target.canonical_name,
                    arguments=arguments,
                )
            )

        reward = 0.0 if result.reward is None else float(result.reward)
        info = {
            "tool_outputs": [
                {
                    "call_id": call_id,
                    "output": _canonical_json_text(_failure_output(result)),
                }
            ],
            "veritas": self._runtime_info(runtime, result=result),
        }
        return None, reward, result.terminated, result.truncated, info

    async def close_session(self, session_id: str | None = None) -> None:
        self._sessions.pop(self._session_key(session_id), None)


def bind_gymnasium_server(
    gymnasium_server_cls: type,
    adapter_factory: Callable[[], NeMoOperationalAdapter],
    *,
    class_name: str = "VeritasNeMoGymnasiumServer",
) -> type:
    """Bind the adapter to NeMo's bundled ``GymnasiumServer`` without importing NeMo here.

    Pass ``resources_servers.gymnasium.GymnasiumServer`` from a NeMo Gym installation.
    This keeps Veritas importable when NeMo Gym is not installed while producing a native
    Resources Server subclass when it is.
    """

    if not isinstance(gymnasium_server_cls, type):
        raise NeMoOperationalExportError(
            "INVALID_GYMNASIUM_SERVER",
            "gymnasium_server_cls must be a class",
        )

    class BoundVeritasNeMoGymnasiumServer(gymnasium_server_cls):
        _veritas_adapter: NeMoOperationalAdapter = PrivateAttr(default_factory=adapter_factory)

        async def reset(
            self,
            metadata: dict,
            session_id: str | None = None,
        ) -> tuple[str | None, dict[str, Any]]:
            return await self._veritas_adapter.reset(metadata, session_id)

        async def step(
            self,
            action: Any,
            metadata: dict,
            session_id: str | None = None,
        ) -> tuple[str | None, float, bool, bool, dict[str, Any]]:
            return await self._veritas_adapter.step(action, metadata, session_id)

        async def close_session(self, session_id: str | None) -> None:
            await self._veritas_adapter.close_session(session_id)
            await super().close_session(session_id)

    BoundVeritasNeMoGymnasiumServer.__name__ = class_name
    BoundVeritasNeMoGymnasiumServer.__qualname__ = class_name
    return BoundVeritasNeMoGymnasiumServer
