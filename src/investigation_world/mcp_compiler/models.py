from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.portable_runtime import PortableInvocationKind

MCP_PROTOCOL_VERSION = "2026-07-28"


class FrozenDict(dict[str, Any]):
    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("MCP compiler mappings are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable


class FrozenList(list[Any]):
    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("MCP compiler sequences are immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable


def _deep_freeze(value: Any) -> Any:
    if isinstance(value, (FrozenDict, FrozenList)):
        return value
    if isinstance(value, Mapping):
        return FrozenDict({str(key): _deep_freeze(item) for key, item in value.items()})
    if isinstance(value, list):
        return FrozenList(_deep_freeze(item) for item in value)
    if isinstance(value, tuple):
        return tuple(_deep_freeze(item) for item in value)
    if isinstance(value, frozenset):
        return frozenset(_deep_freeze(item) for item in value)
    return value


def thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]
    if isinstance(value, frozenset):
        return [thaw_json(item) for item in sorted(value, key=repr)]
    return value


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        thaw_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def content_id(namespace: str, value: Any) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return f"{namespace}:sha256:{digest}"


class FrozenMCPModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    @model_validator(mode="after")
    def freeze_nested_values(self) -> "FrozenMCPModel":
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            frozen = _deep_freeze(value)
            if frozen is not value:
                object.__setattr__(self, field_name, frozen)
        return self


class MCPToolSourceKind(StrEnum):
    ACTION = "action"
    OPERATION = "operation"


class MCPDispatchMode(StrEnum):
    STEP = "step"
    SUBMIT = "submit"


class MCPToolDefinition(FrozenMCPModel):
    """Wire-compatible MCP 2026-07-28 tool definition."""

    name: str
    description: str
    input_schema: dict[str, Any] = Field(alias="inputSchema")
    output_schema: dict[str, Any] = Field(alias="outputSchema")

    def wire(self) -> dict[str, Any]:
        return thaw_json(self.model_dump(mode="python", by_alias=True))


class MCPToolProvenance(FrozenMCPModel):
    public_contract_id: str
    source_kind: MCPToolSourceKind
    canonical_name: str
    canonical_identity: str
    transport_name: str
    interaction_mode: str
    schema_digest: str


class MCPDispatchTarget(FrozenMCPModel):
    tool_name: str
    source_kind: MCPToolSourceKind
    canonical_name: str
    canonical_identity: str
    invocation_kind: PortableInvocationKind
    dispatch_mode: MCPDispatchMode = MCPDispatchMode.STEP


class MCPToolCatalog(FrozenMCPModel):
    protocol_version: str = MCP_PROTOCOL_VERSION
    public_contract_id: str
    tools: tuple[MCPToolDefinition, ...]
    provenance: tuple[MCPToolProvenance, ...]

    @model_validator(mode="after")
    def validate_catalog(self) -> "MCPToolCatalog":
        tool_names = [tool.name for tool in self.tools]
        if len(tool_names) != len(set(tool_names)):
            raise ValueError("MCP tool transport names must be unique")
        provenance_names = [item.transport_name for item in self.provenance]
        if sorted(provenance_names) != sorted(tool_names):
            raise ValueError("MCP tool provenance must cover the tool catalog exactly")
        if any(item.public_contract_id != self.public_contract_id for item in self.provenance):
            raise ValueError("MCP tool provenance references the wrong public contract")
        return self

    @property
    def catalog_id(self) -> str:
        return content_id(
            "veritas-mcp-catalog-v1",
            {
                "protocol_version": self.protocol_version,
                "public_contract_id": self.public_contract_id,
                "tools": [tool.wire() for tool in self.tools],
                "provenance": [item.model_dump(mode="python") for item in self.provenance],
            },
        )

    def tools_list_result(self) -> dict[str, Any]:
        return {
            "tools": [tool.wire() for tool in self.tools],
            "ttlMs": 0,
            "cacheScope": "private",
        }


class MCPCompiledSurface(FrozenMCPModel):
    catalog: MCPToolCatalog
    dispatch: tuple[MCPDispatchTarget, ...]

    @model_validator(mode="after")
    def validate_dispatch(self) -> "MCPCompiledSurface":
        tool_names = {tool.name for tool in self.catalog.tools}
        dispatch_names = [target.tool_name for target in self.dispatch]
        if len(dispatch_names) != len(set(dispatch_names)):
            raise ValueError("MCP dispatch aliases must be unique")
        if set(dispatch_names) != tool_names:
            raise ValueError("MCP dispatch map must cover the tool catalog exactly")
        return self

    @property
    def surface_id(self) -> str:
        return content_id(
            "veritas-mcp-surface-v1",
            {
                "catalog_id": self.catalog.catalog_id,
                "dispatch": [item.model_dump(mode="python") for item in self.dispatch],
            },
        )

    def dispatch_by_tool_name(self) -> dict[str, MCPDispatchTarget]:
        return {target.tool_name: target for target in self.dispatch}
