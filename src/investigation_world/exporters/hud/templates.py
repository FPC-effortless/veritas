from __future__ import annotations

from investigation_world.exporters.hud.adapter import (
    HUD_EXPORT_VERSION,
    HUD_PINNED_SDK,
    HudOperationalAdapter,
)

PINNED_PYTHON_BASE_IMAGE = (
    "python:3.12.11-slim-bookworm@"
    "sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7"
)
PINNED_MCP = "mcp==1.24.0"
PINNED_FASTMCP = "fastmcp==3.2.0"


def render_mcp_service() -> str:
    return '''from __future__ import annotations

import contextlib
import json
from collections.abc import AsyncIterator

import mcp.types as types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.routing import Route

from investigation_world.exporters.hud.adapter import HudOperationalAdapter


def build_mcp_app(adapter: HudOperationalAdapter) -> Starlette:
    server = Server(adapter.environment_name, version="1")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [
            types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=dict(tool.input_schema),
                outputSchema=dict(tool.output_schema),
            )
            for tool in adapter.surface.catalog.tools
        ]

    @server.call_tool(validate_input=False)
    async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
        try:
            result = adapter.call_tool(name, arguments)
        except Exception as exc:
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=str(exc))],
                isError=True,
            )

        payload = result.observation
        if result.failure is not None:
            error_payload = {
                "failure": result.failure.model_dump(mode="json"),
                "state_digest": result.state_digest,
                "budget_status": result.budget_status.model_dump(mode="json"),
            }
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=json.dumps(error_payload, sort_keys=True),
                    )
                ],
                isError=True,
            )

        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        # MCP 2025 structuredContent is object-only. Preserve exact compiler
        # schemas: object observations are structured; non-object observations
        # remain canonical JSON text and the declared compatibility gap records it.
        structured = payload if isinstance(payload, dict) else None
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=text)],
            structuredContent=structured,
            isError=False,
        )

    security = TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*"],
        allowed_origins=[],
    )
    manager = StreamableHTTPSessionManager(
        app=server,
        json_response=True,
        stateless=False,
        security_settings=security,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        async with manager.run():
            yield

    class MCPHandler:
        async def __call__(self, scope, receive, send) -> None:
            await manager.handle_request(scope, receive, send)

    return Starlette(
        routes=[
            Route(
                "/mcp",
                endpoint=MCPHandler(),
                methods=["GET", "POST", "DELETE"],
            )
        ],
        lifespan=lifespan,
    )
'''


def render_env() -> str:
    return '''from __future__ import annotations

import asyncio
from pathlib import Path

import uvicorn
from hud import Environment
from hud.capabilities import Capability
from hud.environment.env import current_session_id

from investigation_world.exporters.hud.adapter import HudOperationalAdapter
from investigation_world.portable_contract import PortableOperationalContract
from mcp_service import build_mcp_app

ROOT = Path(__file__).resolve().parent
CONTRACT = PortableOperationalContract.model_validate_json(
    (ROOT / "contract.json").read_text(encoding="utf-8")
)
ADAPTER = HudOperationalAdapter(CONTRACT)
env = Environment(name=ADAPTER.environment_name, version="1")
_server: uvicorn.Server | None = None
_server_task: asyncio.Task[None] | None = None


@env.initialize
async def start_mcp() -> None:
    global _server, _server_task
    config = uvicorn.Config(
        build_mcp_app(ADAPTER),
        host="127.0.0.1",
        port=8766,
        log_level="warning",
        lifespan="on",
    )
    _server = uvicorn.Server(config)
    _server_task = asyncio.create_task(_server.serve())
    for _ in range(500):
        if _server.started:
            break
        if _server_task.done():
            await _server_task
            raise RuntimeError("MCP capability service exited during startup")
        await asyncio.sleep(0.01)
    if not _server.started:
        raise RuntimeError("MCP capability service did not become ready")
    env.add_capability(
        Capability.mcp(
            name="operational-tools",
            url="http://127.0.0.1:8766/mcp",
            transport="streamable-http",
        )
    )


@env.shutdown
async def stop_mcp() -> None:
    global _server, _server_task
    if _server is not None:
        _server.should_exit = True
    if _server_task is not None:
        await _server_task
    _server = None
    _server_task = None


@env.template(
    id=ADAPTER.task_template_id,
    description="Generic Veritas portable operational task",
)
async def operational_task(seed: int = 0):
    session_id = current_session_id.get()
    if session_id is None:
        raise RuntimeError("HUD task has no control-session identity")
    start = ADAPTER.start(seed=seed, session_id=session_id)
    try:
        answer = yield {"prompt": start.prompt}
        result = ADAPTER.grade(answer, session_id=session_id)
        yield {
            "score": result.reward,
            "info": {
                "public_contract_id": CONTRACT.public.public_id,
                "mcp_catalog_id": ADAPTER.surface.catalog.catalog_id,
                "mcp_surface_id": ADAPTER.surface.surface_id,
                "state_digest": result.state_digest,
                "terminated": result.terminated,
                "truncated": result.truncated,
                "reward_components": (
                    result.reward_components.model_dump(mode="json")
                    if result.reward_components is not None
                    else None
                ),
                "portable_result": result.model_dump(mode="json"),
                "compatibility_gaps": [
                    gap.model_dump(mode="json") for gap in ADAPTER.compatibility_gaps
                ],
            },
        }
    finally:
        ADAPTER.end(session_id=session_id)
'''


def render_pyproject() -> str:
    return f'''[project]
name = "veritas-hud-operational-export"
version = "{HUD_EXPORT_VERSION}.0.0"
requires-python = ">=3.12,<3.13"
dependencies = [
  "{HUD_PINNED_SDK}",
  "{PINNED_MCP}",
  "{PINNED_FASTMCP}",
  "pydantic>=2.10,<3",
  "uvicorn>=0.30,<1",
]

[build-system]
requires = ["hatchling==1.27.0"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["vendor/investigation_world"]
'''


def render_dockerfile() -> str:
    return f'''FROM {PINNED_PYTHON_BASE_IMAGE}
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1
COPY . /app
RUN python -m pip install --no-cache-dir --disable-pip-version-check .
EXPOSE 8765
CMD ["hud", "serve", "env.py", "--host", "0.0.0.0", "--port", "8765"]
'''


def render_operator_readme(adapter: HudOperationalAdapter) -> str:
    gaps = "\n".join(f"- `{gap.code}`: {gap.detail}" for gap in adapter.compatibility_gaps)
    return f'''# Generic Veritas HUD operational export

This directory is an **operator-side** HUD build context. It contains the full
PortableOperationalContract, including evaluator-private state, and must not be
published to the evaluated agent.

The HUD control server exposes one MCP capability named `operational-tools` and
one task template `{adapter.task_template_id}`. `tasks.start` resets the shared
portable runtime, MCP calls dispatch through the shared MCP compiler/runtime, and
`tasks.grade` delegates reward to the portable verifier.

The container accepts one active HUD task session at a time because HUD capability
tunnels do not identify the owning control session to the backend daemon.

## Declared compatibility gaps

{gaps or '- None.'}
'''
