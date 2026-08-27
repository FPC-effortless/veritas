from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any

from pydantic import ValidationError

from investigation_world.mcp_compiler.models import (
    MCPCompiledSurface,
    MCPDispatchMode,
    MCPDispatchTarget,
    MCPToolCatalog,
    MCPToolDefinition,
    MCPToolProvenance,
    MCPToolSourceKind,
    content_id,
    thaw_json,
)
from investigation_world.portable_contract import PortablePublicContract
from investigation_world.portable_runtime import PortableInvocationKind


class MCPCompilerError(ValueError):
    def __init__(self, code: str, path: str, detail: str):
        super().__init__(f"{code} at {path}: {detail}")
        self.code = code
        self.path = path
        self.detail = detail


_SAFE_NAME = re.compile(r"[^a-z0-9_]+")


def _transport_name(source_kind: MCPToolSourceKind, canonical_name: str) -> str:
    canonical_identity = f"{source_kind.value}:{canonical_name}"
    digest = hashlib.sha256(canonical_identity.encode("utf-8")).hexdigest()[:16]
    slug = _SAFE_NAME.sub("_", canonical_name.casefold()).strip("_")
    if not slug:
        slug = source_kind.value
    slug = slug[:72]
    prefix = "action" if source_kind is MCPToolSourceKind.ACTION else "operation"
    return f"{prefix}__{slug}__{digest}"


def _validate_mcp_input_schema(schema: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        raise MCPCompilerError(
            "MCP_INPUT_SCHEMA_INVALID",
            path,
            "MCP tool inputSchema must be a JSON object schema",
        )
    materialized = thaw_json(schema)
    if materialized.get("type") != "object":
        raise MCPCompilerError(
            "MCP_INPUT_ROOT_NOT_OBJECT",
            path,
            "MCP 2026-07-28 tool inputSchema requires an object root",
        )
    return materialized


def _validate_output_schema(schema: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(schema, Mapping):
        raise MCPCompilerError(
            "MCP_OUTPUT_SCHEMA_INVALID",
            path,
            "MCP tool outputSchema must be a JSON Schema object",
        )
    return thaw_json(schema)


def _schema_digest(input_schema: dict[str, Any], output_schema: dict[str, Any]) -> str:
    return content_id(
        "veritas-mcp-tool-schema-v1",
        {"inputSchema": input_schema, "outputSchema": output_schema},
    )


def _action_entries(public: PortablePublicContract) -> list[tuple[MCPToolDefinition, MCPToolProvenance, MCPDispatchTarget]]:
    entries: list[tuple[MCPToolDefinition, MCPToolProvenance, MCPDispatchTarget]] = []
    for index, action in enumerate(public.actions):
        input_schema = _validate_mcp_input_schema(
            action.input_schema,
            path=f"public.actions[{index}].input_schema",
        )
        output_schema = _validate_output_schema(
            action.output_schema,
            path=f"public.actions[{index}].output_schema",
        )
        transport_name = _transport_name(MCPToolSourceKind.ACTION, action.name)
        canonical_identity = f"portable-action:{action.name}"
        tool = MCPToolDefinition(
            name=transport_name,
            description=action.description or f"Portable action {action.name}",
            inputSchema=input_schema,
            outputSchema=output_schema,
        )
        provenance = MCPToolProvenance(
            public_contract_id=public.public_id,
            source_kind=MCPToolSourceKind.ACTION,
            canonical_name=action.name,
            canonical_identity=canonical_identity,
            transport_name=transport_name,
            interaction_mode=action.interaction_mode.value,
            schema_digest=_schema_digest(input_schema, output_schema),
        )
        target = MCPDispatchTarget(
            tool_name=transport_name,
            source_kind=MCPToolSourceKind.ACTION,
            canonical_name=action.name,
            canonical_identity=canonical_identity,
            invocation_kind=PortableInvocationKind.ACTION,
            dispatch_mode=MCPDispatchMode.STEP,
        )
        entries.append((tool, provenance, target))
    return entries


def _operation_entries(public: PortablePublicContract) -> list[tuple[MCPToolDefinition, MCPToolProvenance, MCPDispatchTarget]]:
    entries: list[tuple[MCPToolDefinition, MCPToolProvenance, MCPDispatchTarget]] = []
    for index, operation in enumerate(public.runtime.builtin_operations):
        input_schema = _validate_mcp_input_schema(
            operation.input_schema,
            path=f"public.runtime.builtin_operations[{index}].input_schema",
        )
        output_schema = _validate_output_schema(
            operation.output_schema,
            path=f"public.runtime.builtin_operations[{index}].output_schema",
        )
        transport_name = _transport_name(MCPToolSourceKind.OPERATION, operation.name)
        canonical_identity = f"portable-operation:{operation.name}"
        tool = MCPToolDefinition(
            name=transport_name,
            description=f"Portable runtime operation {operation.name}",
            inputSchema=input_schema,
            outputSchema=output_schema,
        )
        provenance = MCPToolProvenance(
            public_contract_id=public.public_id,
            source_kind=MCPToolSourceKind.OPERATION,
            canonical_name=operation.name,
            canonical_identity=canonical_identity,
            transport_name=transport_name,
            interaction_mode=operation.interaction_mode.value,
            schema_digest=_schema_digest(input_schema, output_schema),
        )
        target = MCPDispatchTarget(
            tool_name=transport_name,
            source_kind=MCPToolSourceKind.OPERATION,
            canonical_name=operation.name,
            canonical_identity=canonical_identity,
            invocation_kind=PortableInvocationKind.OPERATION,
            dispatch_mode=(
                MCPDispatchMode.SUBMIT
                if operation.name == public.runtime.termination.terminal_operation
                else MCPDispatchMode.STEP
            ),
        )
        entries.append((tool, provenance, target))
    return entries


def compile_mcp_surface(public_contract: PortablePublicContract) -> MCPCompiledSurface:
    """Compile only agent-visible portable semantics into deterministic MCP tools."""

    if not isinstance(public_contract, PortablePublicContract):
        raise MCPCompilerError(
            "PUBLIC_CONTRACT_REQUIRED",
            "public_contract",
            "the MCP compiler accepts PortablePublicContract only; evaluator-private contracts are forbidden",
        )
    try:
        public = PortablePublicContract.model_validate(
            public_contract.model_dump(mode="python")
        )
    except (ValidationError, TypeError, ValueError) as exc:
        raise MCPCompilerError(
            "PUBLIC_CONTRACT_INVALID",
            "public_contract",
            str(exc),
        ) from exc

    entries = _action_entries(public) + _operation_entries(public)
    entries.sort(key=lambda item: item[0].name)

    aliases = [tool.name for tool, _, _ in entries]
    if len(aliases) != len(set(aliases)):
        raise MCPCompilerError(
            "TRANSPORT_ALIAS_COLLISION",
            "tools",
            "collision-safe MCP alias generation produced a duplicate name",
        )

    canonical_identities = [item.canonical_identity for _, item, _ in entries]
    if len(canonical_identities) != len(set(canonical_identities)):
        raise MCPCompilerError(
            "CANONICAL_TOOL_IDENTITY_DUPLICATE",
            "tools",
            "portable public contract contains duplicate canonical tool identities",
        )

    catalog = MCPToolCatalog(
        public_contract_id=public.public_id,
        tools=tuple(tool for tool, _, _ in entries),
        provenance=tuple(provenance for _, provenance, _ in entries),
    )
    return MCPCompiledSurface(
        catalog=catalog,
        dispatch=tuple(target for _, _, target in entries),
    )
