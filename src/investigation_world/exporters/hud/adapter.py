from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from investigation_world.mcp_compiler import (
    MCPCompiledSurface,
    MCPToolSourceKind,
    compile_mcp_surface,
    dispatch_mcp_tool,
)
from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.portable_runtime import (
    PortableOperationalRuntime,
    PortableResetResult,
    PortableRuntimeProtocol,
    PortableStepResult,
    PortableSubmission,
)

HUD_EXPORT_VERSION = "1"
HUD_WIRE_PROTOCOL = "hud/1.0"
HUD_MCP_CAPABILITY_PROTOCOL = "mcp/2025-11-25"
HUD_PINNED_SDK = "hud==0.6.15"


class HudOperationalExportError(RuntimeError):
    """Fail-closed error at the HUD/portable-runtime boundary."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class HudCompatibilityGap(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    layer: Literal["hud", "mcp", "integration"]
    detail: str
    affected_tools: tuple[str, ...] = ()


class HudTaskStart(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    environment_name: str
    task_template_id: str
    prompt: str
    reset: PortableResetResult


class HudMeteringEvent(BaseModel):
    """Public-only metering event. Hooks cannot alter semantic results."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    phase: Literal["start", "tool", "grade"]
    public_contract_id: str
    task_id: str
    state_digest: str
    tool_name: str | None = None
    reward: float | None = None
    terminated: bool = False
    truncated: bool = False


HudMeter = Callable[[HudMeteringEvent], None]


def _slug(value: str, *, limit: int = 52) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return (normalized or "task")[:limit].rstrip("-")


def _identity_suffix(public_id: str) -> str:
    return public_id.rsplit(":", 1)[-1][:12].casefold()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _schema_root_type(schema: Mapping[str, Any]) -> str | None:
    raw = schema.get("type")
    return raw if isinstance(raw, str) else None


class HudOperationalAdapter:
    """Thin HUD semantic adapter over the shared portable runtime and MCP compiler.

    The class deliberately owns no world transition or reward logic. HUD task reset,
    MCP tool dispatch and task grading all delegate to the shared portable runtime.
    HUD capability tunnelling does not carry the HUD control-session identifier to
    the backend MCP daemon, so this adapter fails closed if two HUD task sessions try
    to share one operator container concurrently.
    """

    def __init__(
        self,
        contract: PortableOperationalContract,
        *,
        runtime: PortableRuntimeProtocol | None = None,
        meter: HudMeter | None = None,
    ) -> None:
        self.contract = contract
        self.surface: MCPCompiledSurface = compile_mcp_surface(contract.public)
        self.runtime: PortableRuntimeProtocol = runtime or PortableOperationalRuntime(contract)
        self._meter = meter
        self._active_session_id: str | None = None
        self._terminal_result: PortableStepResult | None = None

        suffix = _identity_suffix(contract.public.public_id)
        self.environment_name = f"veritas-{_slug(contract.public.identity.world_id)}-{suffix}"
        self.task_template_id = f"task-{_slug(contract.public.identity.task_id)}-{suffix}"

    @property
    def active_session_id(self) -> str | None:
        return self._active_session_id

    @property
    def compatibility_gaps(self) -> tuple[HudCompatibilityGap, ...]:
        gaps: list[HudCompatibilityGap] = []
        if self.surface.catalog.protocol_version != HUD_MCP_CAPABILITY_PROTOCOL.split("/", 1)[1]:
            gaps.append(
                HudCompatibilityGap(
                    code="HUD_MCP_PROTOCOL_VERSION_LAG",
                    layer="hud",
                    detail=(
                        f"HUD 0.6.15 registers only {HUD_MCP_CAPABILITY_PROTOCOL}; the shared "
                        f"Veritas MCP compiler declares {self.surface.catalog.protocol_version}. "
                        "The exporter does not rewrite compiler protocol metadata or tool schemas."
                    ),
                )
            )

        non_object = tuple(
            item.name
            for item in self.surface.catalog.tools
            if _schema_root_type(item.output_schema) not in {None, "object"}
        )
        if non_object:
            gaps.append(
                HudCompatibilityGap(
                    code="HUD_MCP_LEGACY_STRUCTURED_OUTPUT_OBJECT_ONLY",
                    layer="mcp",
                    detail=(
                        "HUD's MCP 2025 client stack represents structuredContent as an object; "
                        "the shared compiler contains non-object output schemas. The generated "
                        "server keeps those schemas unchanged and emits those observations as "
                        "canonical JSON text rather than inventing an object wrapper."
                    ),
                    affected_tools=non_object,
                )
            )

        submit_tools = tuple(
            item.transport_name
            for item in self.surface.catalog.provenance
            if item.source_kind is MCPToolSourceKind.OPERATION and item.canonical_name == "submit"
        )
        if submit_tools:
            gaps.append(
                HudCompatibilityGap(
                    code="PORTABLE_MCP_SUBMIT_RESULT_ENVELOPE_GAP",
                    layer="integration",
                    detail=(
                        "The shared MCP submit dispatch returns PortableStepResult while the "
                        "compiled submit outputSchema describes the verifier breakdown. HUD "
                        "tasks.grade remains the lossless grading path; the exporter does not "
                        "fabricate missing verifier fields or mutate the shared submit schema."
                    ),
                    affected_tools=submit_tools,
                )
            )
        return tuple(gaps)

    def metadata(self, *, include_private_identity: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "adapter": "veritas.generic-hud-operational",
            "adapter_version": HUD_EXPORT_VERSION,
            "hud_wire_protocol": HUD_WIRE_PROTOCOL,
            "hud_sdk": HUD_PINNED_SDK,
            "hud_mcp_capability_protocol": HUD_MCP_CAPABILITY_PROTOCOL,
            "compiler_mcp_protocol": self.surface.catalog.protocol_version,
            "environment": {
                "name": self.environment_name,
                "version": HUD_EXPORT_VERSION,
            },
            "task": {
                "template_id": self.task_template_id,
                "identity": self.contract.public.identity.model_dump(mode="json"),
            },
            "public_contract_id": self.contract.public.public_id,
            "mcp_catalog_id": self.surface.catalog.catalog_id,
            "mcp_surface_id": self.surface.surface_id,
            "single_active_task_per_container": True,
            "metering": "out_of_band_observer_only",
            "compatibility_gaps": [
                item.model_dump(mode="json") for item in self.compatibility_gaps
            ],
        }
        if include_private_identity:
            payload["contract_id"] = self.contract.contract_id
        return payload

    def start(self, *, seed: int = 0, session_id: str = "default") -> HudTaskStart:
        if self._active_session_id not in {None, session_id}:
            raise HudOperationalExportError(
                "HUD_CONCURRENT_SESSION_UNSUPPORTED",
                "HUD capability tunnels do not identify the owning task session; use one task "
                "session per operator container",
            )
        self._active_session_id = session_id
        self._terminal_result = None
        reset = self.runtime.reset(seed=seed)
        prompt = self._render_prompt(reset)
        self._emit(
            HudMeteringEvent(
                phase="start",
                public_contract_id=self.contract.public.public_id,
                task_id=self.contract.public.identity.task_id,
                state_digest=reset.state_digest,
            )
        )
        return HudTaskStart(
            environment_name=self.environment_name,
            task_template_id=self.task_template_id,
            prompt=prompt,
            reset=reset,
        )

    def end(self, *, session_id: str = "default") -> None:
        if self._active_session_id is None:
            return
        if self._active_session_id != session_id:
            raise HudOperationalExportError(
                "HUD_SESSION_MISMATCH",
                f"active session is {self._active_session_id!r}, not {session_id!r}",
            )
        self._active_session_id = None
        self._terminal_result = None

    def call_tool(
        self,
        tool_name: str,
        arguments: Mapping[str, Any] | None = None,
    ) -> PortableStepResult:
        self._require_active()
        result = dispatch_mcp_tool(self.runtime, self.surface, tool_name, arguments or {})
        if result.reward is not None:
            self._terminal_result = result
        self._emit(
            HudMeteringEvent(
                phase="tool",
                public_contract_id=self.contract.public.public_id,
                task_id=self.contract.public.identity.task_id,
                tool_name=tool_name,
                state_digest=result.state_digest,
                reward=result.reward,
                terminated=result.terminated,
                truncated=result.truncated,
            )
        )
        return result

    def grade(
        self,
        answer: PortableSubmission | Mapping[str, Any] | str | None = None,
        *,
        session_id: str = "default",
    ) -> PortableStepResult:
        self._require_session(session_id)
        if self._terminal_result is not None:
            result = self._terminal_result
        else:
            submission = self._coerce_submission(answer)
            result = self.runtime.verify(submission)
        if result.reward is None:
            failure = result.failure.code.value if result.failure is not None else "unknown"
            raise HudOperationalExportError(
                "HUD_GRADE_REWARD_UNAVAILABLE",
                f"portable verifier did not return a numeric reward (failure={failure})",
            )
        self._terminal_result = result
        self._emit(
            HudMeteringEvent(
                phase="grade",
                public_contract_id=self.contract.public.public_id,
                task_id=self.contract.public.identity.task_id,
                state_digest=result.state_digest,
                reward=result.reward,
                terminated=result.terminated,
                truncated=result.truncated,
            )
        )
        return result

    def _render_prompt(self, reset: PortableResetResult) -> str:
        public = self.contract.public
        payload = {
            "veritas_operational_task": {
                "identity": public.identity.model_dump(mode="json"),
                "objective": public.objective,
                "role": public.role,
                "permitted_systems": list(public.permitted_systems),
                "constraints": list(public.constraints),
                "success_description": public.success_description,
                "task_metadata": public.task_metadata,
                "episode_metadata": public.episode_metadata,
            },
            "initial_observation": reset.observation,
            "initial_state_digest": reset.state_digest,
            "capability": {
                "name": "operational-tools",
                "catalog_id": self.surface.catalog.catalog_id,
                "surface_id": self.surface.surface_id,
            },
            "submission": (
                "Return a final answer for HUD tasks.grade. A JSON object matching the portable "
                "submission schema is accepted; plain text is treated as the conclusion."
            ),
        }
        return _canonical_json(payload)

    def _coerce_submission(
        self,
        value: PortableSubmission | Mapping[str, Any] | str | None,
    ) -> PortableSubmission:
        if isinstance(value, PortableSubmission):
            return value
        if value is None:
            return PortableSubmission()
        if isinstance(value, Mapping):
            return PortableSubmission.model_validate(dict(value))
        if not isinstance(value, str):
            raise HudOperationalExportError(
                "HUD_GRADE_ANSWER_TYPE_UNSUPPORTED",
                f"expected string, mapping or PortableSubmission, got {type(value).__name__}",
            )
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return PortableSubmission(conclusion=value)
        if isinstance(parsed, dict):
            return PortableSubmission.model_validate(parsed)
        return PortableSubmission(conclusion=value)

    def _require_active(self) -> None:
        if self._active_session_id is None:
            raise HudOperationalExportError(
                "HUD_TASK_NOT_STARTED",
                "tasks.start must reset the portable runtime before any capability call",
            )

    def _require_session(self, session_id: str) -> None:
        self._require_active()
        if self._active_session_id != session_id:
            raise HudOperationalExportError(
                "HUD_SESSION_MISMATCH",
                f"active session is {self._active_session_id!r}, not {session_id!r}",
            )

    def _emit(self, event: HudMeteringEvent) -> None:
        if self._meter is None:
            return
        try:
            self._meter(event)
        except Exception:
            # Metering is explicitly observational and cannot alter world semantics.
            return
