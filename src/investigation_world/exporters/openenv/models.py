from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, ClassVar, Literal

from pydantic import ConfigDict, model_validator
from pydantic.json_schema import GetJsonSchemaHandler, JsonSchemaValue
from pydantic_core import CoreSchema

from investigation_world.exporters.openenv.compat import (
    OpenEnvActionBase,
    OpenEnvObservationBase,
    OpenEnvStateBase,
)
from investigation_world.portable_runtime.validation import (
    SchemaValidationError,
    UnsupportedSchemaError,
    validate_json_instance,
)


class PortableOpenEnvAction(OpenEnvActionBase):
    """OpenEnv action envelope whose arguments retain exact portable/MCP schemas."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    tool: str
    arguments: dict[str, Any]

    _tool_schemas: ClassVar[Mapping[str, dict[str, Any]]] = {}

    @model_validator(mode="after")
    def validate_bound_tool(self) -> "PortableOpenEnvAction":
        schema = self._tool_schemas.get(self.tool)
        if schema is None:
            raise ValueError(f"unknown OpenEnv tool: {self.tool!r}")
        try:
            validate_json_instance(self.arguments, schema)
        except (SchemaValidationError, UnsupportedSchemaError) as exc:
            raise ValueError(f"arguments do not satisfy {self.tool!r} schema: {exc}") from exc
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls,
        core_schema: CoreSchema,
        handler: GetJsonSchemaHandler,
    ) -> JsonSchemaValue:
        del core_schema, handler
        branches: list[dict[str, Any]] = []
        for tool_name, input_schema in sorted(cls._tool_schemas.items()):
            branches.append(
                {
                    "type": "object",
                    "properties": {
                        "metadata": {
                            "type": "object",
                            "additionalProperties": True,
                        },
                        "tool": {"type": "string", "const": tool_name},
                        "arguments": copy.deepcopy(input_schema),
                    },
                    "required": ["tool", "arguments"],
                    "additionalProperties": False,
                }
            )
        return {
            "title": cls.__name__,
            "oneOf": branches,
        }


class PortableOpenEnvObservation(OpenEnvObservationBase):
    """Public OpenEnv observation preserving portable termination semantics."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    kind: Literal["reset", "step"]
    tool: str | None = None
    result: Any = None
    terminated: bool = False
    truncated: bool = False
    state_digest: str
    failure: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_done_projection(self) -> "PortableOpenEnvObservation":
        if self.done != (self.terminated or self.truncated):
            raise ValueError("done must equal terminated or truncated")
        return self


class PortableOpenEnvState(OpenEnvStateBase):
    """Agent-visible OpenEnv state. Evaluator-private contract material is forbidden."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    task_id: str
    world_id: str
    domain: str
    public_contract_id: str
    export_id: str
    state_digest: str
    public_state: dict[str, Any]
    terminated: bool = False
    truncated: bool = False
