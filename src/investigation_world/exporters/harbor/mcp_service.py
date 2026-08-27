from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlsplit

import uvicorn
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from investigation_world.mcp_compiler import MCP_PROTOCOL_VERSION, compile_mcp_surface
from investigation_world.portable_contract import PortablePublicContract

_PROTOCOL_META = "io.modelcontextprotocol/protocolVersion"
_CLIENT_CAPABILITIES_META = "io.modelcontextprotocol/clientCapabilities"
_SERVER_INFO_META = "io.modelcontextprotocol/serverInfo"
_SERVER_INFO = {"name": "veritas-harbor", "version": "1"}
_HEADER_MISMATCH = -32020
_UNSUPPORTED_PROTOCOL_VERSION = -32022


@dataclass(frozen=True)
class _MCPRequestError(Exception):
    code: int
    message: str
    status_code: int = 200
    data: Any = None


@dataclass(frozen=True)
class _RuntimeCallRejected(Exception):
    json_rpc_code: int
    code: str
    path: tuple[str | int, ...] | None = None


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


def _stamp_result(result: Mapping[str, Any]) -> dict[str, Any]:
    stamped = dict(result)
    stamped["resultType"] = "complete"
    meta = dict(stamped.get("_meta") or {})
    meta[_SERVER_INFO_META] = dict(_SERVER_INFO)
    stamped["_meta"] = meta
    return stamped


def _discover_result() -> dict[str, Any]:
    return _stamp_result(
        {
            "supportedVersions": [MCP_PROTOCOL_VERSION],
            "capabilities": {"tools": {"listChanged": False}},
            "instructions": "Use the advertised Veritas operational tools for this task.",
            "ttlMs": 0,
            "cacheScope": "private",
        }
    )


def _decode_header_value(value: str) -> str:
    prefix = "=?base64?"
    suffix = "?="
    if value.startswith(prefix) and value.endswith(suffix):
        encoded = value[len(prefix) : -len(suffix)]
        try:
            return base64.b64decode(encoded, validate=True).decode("utf-8")
        except (ValueError, UnicodeDecodeError) as exc:
            raise _MCPRequestError(
                _HEADER_MISMATCH,
                "Malformed encoded MCP routing header",
                status_code=400,
            ) from exc
    if value != value.strip(" \t") or any(
        ord(character) < 0x20 or ord(character) > 0x7E for character in value
    ):
        raise _MCPRequestError(
            _HEADER_MISMATCH,
            "Malformed MCP routing header",
            status_code=400,
        )
    return value


def _validate_origin(headers: Mapping[str, str]) -> None:
    origin = headers.get("origin")
    if not origin:
        return
    host = headers.get("host")
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or not host
        or parsed.netloc.lower() != host.lower()
    ):
        raise _MCPRequestError(-32600, "Origin not allowed", status_code=403)


def _validate_mcp_request(body: Any, headers: Mapping[str, str]) -> tuple[Any, str, dict[str, Any]]:
    _validate_origin(headers)
    if not isinstance(body, dict) or body.get("jsonrpc") != "2.0" or "id" not in body:
        raise _MCPRequestError(-32600, "Invalid Request", status_code=400)
    request_id = body.get("id")
    method = body.get("method")
    params = body.get("params")
    if not isinstance(method, str) or not isinstance(params, dict):
        raise _MCPRequestError(-32602, "Invalid params")
    meta = params.get("_meta")
    if not isinstance(meta, dict):
        raise _MCPRequestError(-32602, "Missing request metadata")
    requested_version = meta.get(_PROTOCOL_META)
    client_capabilities = meta.get(_CLIENT_CAPABILITIES_META)
    if not isinstance(requested_version, str) or not isinstance(client_capabilities, dict):
        raise _MCPRequestError(-32602, "Invalid request metadata")

    header_version = headers.get("mcp-protocol-version")
    header_method = headers.get("mcp-method")
    if not header_version or not header_method:
        raise _MCPRequestError(
            _HEADER_MISMATCH,
            "Required MCP routing headers are missing",
            status_code=400,
        )
    if header_version != requested_version or header_method != method:
        raise _MCPRequestError(
            _HEADER_MISMATCH,
            "MCP routing headers do not match the request body",
            status_code=400,
        )
    if requested_version != MCP_PROTOCOL_VERSION:
        raise _MCPRequestError(
            _UNSUPPORTED_PROTOCOL_VERSION,
            "Unsupported protocol version",
            status_code=400,
            data={"supported": [MCP_PROTOCOL_VERSION], "requested": requested_version},
        )

    if method == "tools/call":
        name = params.get("name")
        if not isinstance(name, str):
            raise _MCPRequestError(-32602, "Invalid params")
        header_name = headers.get("mcp-name")
        if not header_name:
            raise _MCPRequestError(
                _HEADER_MISMATCH,
                "Required Mcp-Name header is missing",
                status_code=400,
            )
        if _decode_header_value(header_name) != name:
            raise _MCPRequestError(
                _HEADER_MISMATCH,
                "Mcp-Name header does not match the request body",
                status_code=400,
            )
    return request_id, method, params


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
            body = {}
        detail = body.get("detail") if isinstance(body, dict) else None
        if isinstance(detail, dict):
            rpc_code = detail.get("json_rpc_code", -32603)
            error_code = detail.get("code", "runtime_call_rejected")
            path = detail.get("path")
            safe_path = tuple(path) if isinstance(path, list) else None
            if not isinstance(rpc_code, int) or isinstance(rpc_code, bool):
                rpc_code = -32603
            if not isinstance(error_code, str):
                error_code = "runtime_call_rejected"
            raise _RuntimeCallRejected(rpc_code, error_code, safe_path) from exc
        raise _RuntimeCallRejected(-32603, "runtime_call_rejected") from exc


def _tool_wire_result(step: dict[str, Any]) -> dict[str, Any]:
    failure = step.get("failure")
    if failure is not None:
        code = failure.get("code") if isinstance(failure, dict) else None
        suffix = f" ({code})" if isinstance(code, str) else ""
        return _stamp_result(
            {
                "content": [
                    {
                        "type": "text",
                        "text": f"Portable runtime rejected the tool call{suffix}",
                    }
                ],
                "isError": True,
            }
        )
    observation = step.get("observation")
    return _stamp_result(
        {
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
            ],
            "structuredContent": observation,
            "isError": False,
        }
    )


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
        try:
            request_id, method, params = _validate_mcp_request(body, request.headers)
        except _MCPRequestError as exc:
            request_id = body.get("id") if isinstance(body, dict) else None
            return JSONResponse(
                _json_rpc_error(request_id, exc.code, exc.message, exc.data),
                status_code=exc.status_code,
            )

        if method == "server/discover":
            return JSONResponse(_json_rpc_result(request_id, _discover_result()))
        if method == "tools/list":
            return JSONResponse(
                _json_rpc_result(request_id, _stamp_result(surface.catalog.tools_list_result()))
            )
        if method == "tools/call":
            name = params["name"]
            arguments = params.get("arguments") or {}
            if not isinstance(arguments, dict):
                return JSONResponse(
                    _json_rpc_error(request_id, -32602, "Invalid params")
                )
            try:
                step = _call_runtime(runtime_control_url, name, arguments)
            except _RuntimeCallRejected as exc:
                data: dict[str, Any] = {"code": exc.code}
                if exc.path is not None:
                    data["path"] = list(exc.path)
                return JSONResponse(
                    _json_rpc_error(
                        request_id,
                        exc.json_rpc_code,
                        "Tool call rejected",
                        data,
                    )
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
