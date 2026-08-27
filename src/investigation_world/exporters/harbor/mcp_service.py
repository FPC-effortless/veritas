from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from investigation_world.mcp_compiler import MCP_PROTOCOL_VERSION, compile_mcp_surface
from investigation_world.portable_contract import PortablePublicContract


def _json_rpc_result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _json_rpc_error(
    request_id: Any,
    code: int,
    message: str,
    data: Any = None,
) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def _call_runtime(base_url: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    payload = json.dumps(
        {"name": name, "arguments": arguments},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        base_url.rstrip("/") + "/tool",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            body = {"detail": "runtime-control rejected the tool call"}
        detail = body.get("detail", body)
        raise RuntimeError(json.dumps(detail, sort_keys=True)) from exc


def _tool_wire_result(step: dict[str, Any]) -> dict[str, Any]:
    failure = step.get("failure")
    if failure is not None:
        message = str(failure.get("message", "portable runtime rejected the tool call"))
        return {
            "content": [{"type": "text", "text": message}],
            "isError": True,
        }
    observation = step.get("observation")
    result: dict[str, Any] = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    observation,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            }
        ]
    }
    if isinstance(observation, dict):
        result["structuredContent"] = observation
    return result


def _load_public_contract(path: Path) -> PortablePublicContract:
    return PortablePublicContract.model_validate_json(path.read_text(encoding="utf-8"))


def create_mcp_app(public: PortablePublicContract, runtime_control_url: str) -> FastAPI:
    surface = compile_mcp_surface(public)
    app = FastAPI(
        title="Veritas Harbor MCP",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    def health() -> dict[str, Any] | JSONResponse:
        try:
            url = runtime_control_url.rstrip("/") + "/health"
            with urllib.request.urlopen(url, timeout=2) as response:
                upstream = json.loads(response.read().decode("utf-8"))
            return {"ok": bool(upstream.get("ok")), "surface_id": surface.surface_id}
        except Exception:
            return JSONResponse(status_code=503, content={"ok": False})

    @app.post("/mcp")
    async def mcp(request: Request) -> Response:
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(_json_rpc_error(None, -32700, "Parse error"), status_code=400)
        if not isinstance(body, dict) or body.get("jsonrpc") != "2.0":
            request_id = body.get("id") if isinstance(body, dict) else None
            return JSONResponse(
                _json_rpc_error(request_id, -32600, "Invalid Request"),
                status_code=400,
            )
        method = body.get("method")
        request_id = body.get("id")
        params = body.get("params") or {}
        if method in {"notifications/initialized", "notifications/cancelled"}:
            return Response(status_code=202)
        if method == "initialize":
            return JSONResponse(
                _json_rpc_result(
                    request_id,
                    {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": False}},
                        "serverInfo": {"name": "veritas-harbor", "version": "1"},
                    },
                )
            )
        if method == "ping":
            return JSONResponse(_json_rpc_result(request_id, {}))
        if method == "tools/list":
            return JSONResponse(_json_rpc_result(request_id, surface.catalog.tools_list_result()))
        if method == "tools/call":
            if not isinstance(params, dict):
                return JSONResponse(
                    _json_rpc_error(request_id, -32602, "Invalid params"),
                    status_code=400,
                )
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not isinstance(name, str) or not isinstance(arguments, dict):
                return JSONResponse(
                    _json_rpc_error(request_id, -32602, "Invalid params"),
                    status_code=400,
                )
            try:
                step = _call_runtime(runtime_control_url, name, arguments)
            except RuntimeError as exc:
                return JSONResponse(
                    _json_rpc_error(request_id, -32602, "Tool call rejected", str(exc)),
                    status_code=400,
                )
            return JSONResponse(_json_rpc_result(request_id, _tool_wire_result(step)))
        return JSONResponse(
            _json_rpc_error(request_id, -32601, "Method not found"),
            status_code=404,
        )

    return app


def main() -> None:
    public_path = Path(
        os.environ.get(
            "VERITAS_PUBLIC_CONTRACT_PATH",
            "/opt/veritas-harbor/public-contract.json",
        )
    )
    runtime_url = os.environ.get(
        "VERITAS_RUNTIME_CONTROL_URL",
        "http://runtime-control:8081",
    )
    app = create_mcp_app(_load_public_contract(public_path), runtime_url)
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
