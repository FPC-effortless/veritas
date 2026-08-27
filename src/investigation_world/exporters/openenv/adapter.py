from __future__ import annotations

import hashlib
from typing import Any

from investigation_world.exporters.openenv.compat import (
    EnvironmentMetadata,
    OpenEnvEnvironmentBase,
    create_openenv_app,
)
from investigation_world.exporters.openenv.models import (
    PortableOpenEnvAction,
    PortableOpenEnvObservation,
    PortableOpenEnvState,
)
from investigation_world.mcp_compiler import compile_mcp_surface, dispatch_mcp_tool
from investigation_world.mcp_compiler.models import (
    MCPCompiledSurface,
    content_id,
    thaw_json,
)
from investigation_world.portable_contract import (
    PortableOperationalContract,
    PortablePublicContract,
)
from investigation_world.portable_runtime import (
    PortableOperationalRuntime,
    PortableRuntimeProtocol,
    PortableStepResult,
)
from investigation_world.portable_runtime.validation import validate_json_instance

OPENENV_EXPORT_SCHEMA_VERSION = "openenv-operational-v1"


def _safe_suffix(identifier: str, length: int = 16) -> str:
    return hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:length]


def _bind_action_type(surface: MCPCompiledSurface, export_id: str) -> type[PortableOpenEnvAction]:
    schemas = {
        tool.name: thaw_json(tool.input_schema)
        for tool in surface.catalog.tools
    }
    name = f"PortableOpenEnvAction_{_safe_suffix(export_id)}"
    return type(name, (PortableOpenEnvAction,), {"_tool_schemas": schemas})


def _public_failure(result: PortableStepResult) -> dict[str, Any] | None:
    failure = result.failure
    if failure is None:
        return None
    return {
        "code": failure.code.value,
        "message": failure.message,
        "retryable": failure.retryable,
    }


def _public_metadata(
    public: PortablePublicContract,
    *,
    export_id: str,
    state_digest: str,
    tool: str | None = None,
    terminated: bool = False,
    truncated: bool = False,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "environment": "veritas-portable-operational",
        "export_schema_version": OPENENV_EXPORT_SCHEMA_VERSION,
        "export_id": export_id,
        "public_contract_id": public.public_id,
        "task_id": public.identity.task_id,
        "world_id": public.identity.world_id,
        "episode_id": public.identity.episode_id,
        "domain": public.identity.domain,
        "state_digest": state_digest,
        "terminated": terminated,
        "truncated": truncated,
    }
    if tool is not None:
        metadata["tool"] = tool
    return metadata


class PortableOpenEnvEnvironment(OpenEnvEnvironmentBase):
    """Generic OpenEnv transport over PortableRuntimeProtocol semantics."""

    SUPPORTS_CONCURRENT_SESSIONS = True

    def __init__(
        self,
        *,
        public_contract: PortablePublicContract,
        surface: MCPCompiledSurface,
        export_id: str,
        environment_name: str,
        action_type: type[PortableOpenEnvAction],
        runtime: PortableRuntimeProtocol,
    ) -> None:
        super().__init__()
        self._public = public_contract
        self._surface = surface
        self._dispatch = surface.dispatch_by_tool_name()
        self._export_id = export_id
        self._environment_name = environment_name
        self._action_type = action_type
        self._runtime = runtime
        self._state = self._state_from_runtime(step_count=0, terminated=False, truncated=False)

    @property
    def state(self) -> PortableOpenEnvState:
        return self._state.model_copy(deep=True)

    def reset(
        self,
        seed: int | None = None,
        episode_id: str | None = None,
        **kwargs: Any,
    ) -> PortableOpenEnvObservation:
        del episode_id  # Transport session IDs never override portable task identity.
        if kwargs:
            raise ValueError(
                f"unsupported reset parameters for portable runtime: {sorted(kwargs)}"
            )
        reset = self._runtime.reset(seed=seed)
        validate_json_instance(reset.observation, self._public.state.observation_schema)
        self._state = self._state_from_runtime(
            step_count=0,
            terminated=False,
            truncated=False,
        )
        return PortableOpenEnvObservation(
            kind="reset",
            tool=None,
            result=reset.observation,
            reward=None,
            done=False,
            terminated=False,
            truncated=False,
            state_digest=reset.state_digest,
            failure=None,
            metadata=_public_metadata(
                self._public,
                export_id=self._export_id,
                state_digest=reset.state_digest,
            ),
        )

    def step(
        self,
        action: PortableOpenEnvAction,
        timeout_s: float | None = None,
        **kwargs: Any,
    ) -> PortableOpenEnvObservation:
        del timeout_s
        if kwargs:
            raise ValueError(f"unsupported step parameters: {sorted(kwargs)}")
        if not isinstance(action, self._action_type):
            action = self._action_type.model_validate(action.model_dump(mode="python"))

        if action.tool not in self._dispatch:
            raise ValueError(f"unknown OpenEnv tool: {action.tool!r}")
        result = dispatch_mcp_tool(
            self._runtime,
            self._surface,
            action.tool,
            action.arguments,
        )

        self._state = self._state_from_runtime(
            step_count=self._state.step_count + 1,
            terminated=result.terminated,
            truncated=result.truncated,
        )
        return PortableOpenEnvObservation(
            kind="step",
            tool=action.tool,
            result=result.observation,
            reward=result.reward,
            done=(result.terminated or result.truncated),
            terminated=result.terminated,
            truncated=result.truncated,
            state_digest=result.state_digest,
            failure=_public_failure(result),
            metadata=_public_metadata(
                self._public,
                export_id=self._export_id,
                state_digest=result.state_digest,
                tool=action.tool,
                terminated=result.terminated,
                truncated=result.truncated,
            ),
        )

    def get_metadata(self) -> EnvironmentMetadata:
        return EnvironmentMetadata(
            name=self._environment_name,
            description="Generic OpenEnv adapter over a Veritas portable operational runtime.",
            version=OPENENV_EXPORT_SCHEMA_VERSION,
        )

    def _state_from_runtime(
        self,
        *,
        step_count: int,
        terminated: bool,
        truncated: bool,
    ) -> PortableOpenEnvState:
        public_state = self._runtime.public_state()
        validate_json_instance(public_state, self._public.state.observation_schema)
        return PortableOpenEnvState(
            episode_id=self._public.identity.episode_id,
            step_count=step_count,
            task_id=self._public.identity.task_id,
            world_id=self._public.identity.world_id,
            domain=self._public.identity.domain,
            public_contract_id=self._public.public_id,
            export_id=self._export_id,
            state_digest=self._runtime.state_digest(),
            public_state=public_state,
            terminated=terminated,
            truncated=truncated,
        )


class OpenEnvOperationalExport:
    """Compiled public OpenEnv surface plus an evaluator-side environment factory."""

    __slots__ = (
        "export_id",
        "environment_name",
        "public_contract_id",
        "task_id",
        "world_id",
        "episode_id",
        "domain",
        "action_type",
        "observation_type",
        "state_type",
        "mcp_surface",
        "_contract",
    )

    def __init__(
        self,
        *,
        export_id: str,
        environment_name: str,
        public_contract_id: str,
        task_id: str,
        world_id: str,
        episode_id: str,
        domain: str,
        action_type: type[PortableOpenEnvAction],
        mcp_surface: MCPCompiledSurface,
        contract: PortableOperationalContract,
    ) -> None:
        self.export_id = export_id
        self.environment_name = environment_name
        self.public_contract_id = public_contract_id
        self.task_id = task_id
        self.world_id = world_id
        self.episode_id = episode_id
        self.domain = domain
        self.action_type = action_type
        self.observation_type = PortableOpenEnvObservation
        self.state_type = PortableOpenEnvState
        self.mcp_surface = mcp_surface
        self._contract = contract

    def create_environment(self) -> PortableOpenEnvEnvironment:
        runtime = PortableOperationalRuntime(self._contract)
        return PortableOpenEnvEnvironment(
            public_contract=self._contract.public,
            surface=self.mcp_surface,
            export_id=self.export_id,
            environment_name=self.environment_name,
            action_type=self.action_type,
            runtime=runtime,
        )

    def create_app(self, **kwargs: Any) -> Any:
        return create_openenv_app(
            self.create_environment,
            self.action_type,
            self.observation_type,
            env_name=self.environment_name,
            **kwargs,
        )


def compile_openenv_export(
    contract: PortableOperationalContract,
) -> OpenEnvOperationalExport:
    """Compile one generic OpenEnv adapter from a portable operational contract."""

    if not isinstance(contract, PortableOperationalContract):
        raise TypeError("contract must be a PortableOperationalContract")
    copied = PortableOperationalContract.model_validate(contract.model_dump(mode="python"))
    surface = compile_mcp_surface(copied.public)
    export_id = content_id(
        "veritas-openenv-export-v1",
        {
            "adapter_schema_version": OPENENV_EXPORT_SCHEMA_VERSION,
            "public_contract_id": copied.public.public_id,
            "mcp_surface_id": surface.surface_id,
        },
    )
    action_type = _bind_action_type(surface, export_id)
    return OpenEnvOperationalExport(
        export_id=export_id,
        environment_name=f"veritas_operational_{_safe_suffix(export_id)}",
        public_contract_id=copied.public.public_id,
        task_id=copied.public.identity.task_id,
        world_id=copied.public.identity.world_id,
        episode_id=copied.public.identity.episode_id,
        domain=copied.public.identity.domain,
        action_type=action_type,
        mcp_surface=surface,
        contract=copied,
    )
