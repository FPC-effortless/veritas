from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from investigation_world.mcp_compiler.models import (
    MCPCompiledSurface,
    MCPDispatchMode,
    MCPDispatchTarget,
)
from investigation_world.portable_runtime import (
    PortableRuntimeProtocol,
    PortableStepRequest,
    PortableStepResult,
)
from investigation_world.portable_runtime.validation import (
    SchemaValidationError,
    UnsupportedSchemaError,
    validate_json_instance,
)


class MCPToolCallError(ValueError):
    """Fail-closed MCP tools/call error suitable for JSON-RPC Invalid Params mapping."""

    def __init__(
        self,
        code: str,
        detail: str,
        *,
        json_rpc_code: int = -32602,
        path: str = "$",
    ):
        super().__init__(f"{code} at {path}: {detail}")
        self.code = code
        self.detail = detail
        self.json_rpc_code = json_rpc_code
        self.path = path


def resolve_mcp_tool_call(
    surface: MCPCompiledSurface,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
) -> tuple[MCPDispatchTarget, dict[str, Any]]:
    if not isinstance(tool_name, str) or not tool_name:
        raise MCPToolCallError(
            "INVALID_TOOL_NAME",
            "tools/call name must be a non-empty string",
            path="params.name",
        )
    if arguments is not None and not isinstance(arguments, Mapping):
        raise MCPToolCallError(
            "INVALID_TOOL_ARGUMENTS",
            "tools/call arguments must be an object when present",
            path="params.arguments",
        )

    target = surface.dispatch_by_tool_name().get(tool_name)
    if target is None:
        raise MCPToolCallError(
            "UNKNOWN_TOOL",
            "tool name is not present in the compiled MCP catalog",
            path="params.name",
        )
    tool = next(item for item in surface.catalog.tools if item.name == tool_name)
    payload = dict(arguments or {})
    try:
        validate_json_instance(payload, tool.input_schema)
    except SchemaValidationError as exc:
        raise MCPToolCallError(
            "INVALID_TOOL_ARGUMENTS",
            exc.message,
            path=exc.path,
        ) from exc
    except UnsupportedSchemaError as exc:
        raise MCPToolCallError(
            "TOOL_SCHEMA_UNSUPPORTED",
            exc.detail,
            path=exc.path,
        ) from exc
    return target, payload


def dispatch_mcp_tool(
    runtime: PortableRuntimeProtocol,
    surface: MCPCompiledSurface,
    tool_name: str,
    arguments: Mapping[str, Any] | None = None,
) -> PortableStepResult:
    """Resolve an MCP transport alias and delegate execution to the portable runtime."""

    target, payload = resolve_mcp_tool_call(surface, tool_name, arguments)
    if target.dispatch_mode is MCPDispatchMode.SUBMIT:
        return runtime.submit(payload)
    return runtime.step(
        PortableStepRequest(
            kind=target.invocation_kind,
            name=target.canonical_name,
            arguments=payload,
        )
    )
