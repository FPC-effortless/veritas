from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from investigation_world.mcp_compiler import (
    MCPToolCallError,
    compile_mcp_surface,
    dispatch_mcp_tool,
)
from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.portable_runtime import PortableOperationalRuntime, PortableStepResult


class RuntimeToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class RuntimeControl:
    """Private operational service: shared compiler dispatch over shared portable runtime."""

    def __init__(
        self,
        contract: PortableOperationalContract,
        *,
        seed: int = 0,
        trajectory_path: Path | None = None,
    ):
        self.contract = contract
        self.surface = compile_mcp_surface(contract.public)
        self.runtime = PortableOperationalRuntime(contract)
        self.seed = seed
        self.trajectory_path = trajectory_path
        self._lock = threading.Lock()
        reset = self.runtime.reset(seed=seed)
        self._write_reset(reset.model_dump(mode="json"))

    def _append(self, record: dict[str, Any], *, reset: bool = False) -> None:
        if self.trajectory_path is None:
            return
        self.trajectory_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "w" if reset else "a"
        with self.trajectory_path.open(mode, encoding="utf-8", newline="\n") as handle:
            handle.write(
                json.dumps(
                    record,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
            )
            handle.write("\n")

    def _write_reset(self, result: dict[str, Any]) -> None:
        self._append(
            {
                "kind": "reset",
                "contract_id": self.contract.contract_id,
                "public_contract_id": self.contract.public.public_id,
                "surface_id": self.surface.surface_id,
                "seed": self.seed,
                "result": result,
            },
            reset=True,
        )

    def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> PortableStepResult:
        with self._lock:
            result = dispatch_mcp_tool(self.runtime, self.surface, name, arguments or {})
            self._append(
                {
                    "kind": "tool_call",
                    "name": name,
                    "arguments": arguments or {},
                    "result": result.model_dump(mode="json"),
                }
            )
            return result


def _load_contract(path: Path) -> PortableOperationalContract:
    return PortableOperationalContract.model_validate_json(path.read_text(encoding="utf-8"))


def create_runtime_app(control: RuntimeControl) -> FastAPI:
    app = FastAPI(
        title="Veritas Harbor runtime control",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "public_contract_id": control.contract.public.public_id,
            "surface_id": control.surface.surface_id,
        }

    @app.post("/tool")
    def tool(call: RuntimeToolCall) -> dict[str, Any]:
        try:
            return control.call_tool(call.name, call.arguments).model_dump(mode="json")
        except MCPToolCallError as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": exc.code,
                    "detail": exc.detail,
                    "json_rpc_code": exc.json_rpc_code,
                    "path": exc.path,
                },
            ) from exc

    return app


def main() -> None:
    contract_path = Path(
        os.environ.get("VERITAS_CONTRACT_PATH", "/opt/veritas-harbor/contract.json")
    )
    trajectory_path = Path(
        os.environ.get("VERITAS_TRAJECTORY_PATH", "/tmp/veritas-runtime/trajectory.jsonl")
    )
    seed = int(os.environ.get("VERITAS_RUNTIME_SEED", "0"))
    control = RuntimeControl(
        _load_contract(contract_path),
        seed=seed,
        trajectory_path=trajectory_path,
    )
    uvicorn.run(create_runtime_app(control), host="0.0.0.0", port=8081, log_level="warning")


if __name__ == "__main__":
    main()
