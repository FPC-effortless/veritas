from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableOperationalRuntime,
    PortableStepRequest,
    PortableStepResult,
)

from .models import PrimePackageBuildResult, PrimePackageFile, PrimeReplayRequest

ADAPTER_ID = "prime-verifiers-v1-operational"
EXPORT_SCHEMA_VERSION = "1"
PACKAGE_MODULE = "veritas_prime_operational"
PACKAGE_VERSION = "0.11.0"
VERITAS_RUNTIME_COMMIT = "7f7f2ec5d9618c6408f5d7aaca9329dc8f5ac5a5"
DEFAULT_VERITAS_REQUIREMENT = (
    "investigation-world @ git+https://github.com/FPC-effortless/veritas.git@"
    f"{VERITAS_RUNTIME_COMMIT}"
)


class PrimeOperationalExportError(ValueError):
    """The portable contract cannot be exported to Prime without semantic loss."""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _json_document(value: Any) -> str:
    return json.dumps(
        value,
        indent=2,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
    ) + "\n"


def _tool_name(kind: str, name: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_-]+", "_", name).strip("_") or "unnamed"
    slug = slug[:48]
    digest = hashlib.sha256(f"{kind}\0{name}".encode("utf-8")).hexdigest()[:10]
    prefix = "action" if kind == "action" else "runtime"
    return f"{prefix}__{slug}__{digest}"


def _tool_bindings(contract: PortableOperationalContract) -> dict[str, dict[str, Any]]:
    bindings: dict[str, dict[str, Any]] = {}
    for action in contract.public.actions:
        prime_name = _tool_name("action", action.name)
        bindings[prime_name] = {
            "kind": "action",
            "name": action.name,
            "description": action.description,
            "input_schema": action.input_schema,
            "output_schema": action.output_schema,
            "interaction_mode": action.interaction_mode.value,
        }
    for operation in contract.public.runtime.builtin_operations:
        prime_name = _tool_name("operation", operation.name)
        if prime_name in bindings:
            raise PrimeOperationalExportError(
                f"Prime tool-name collision for portable operation {operation.name!r}"
            )
        bindings[prime_name] = {
            "kind": "operation",
            "name": operation.name,
            "description": f"Portable runtime operation {operation.name}.",
            "input_schema": operation.input_schema,
            "output_schema": operation.output_schema,
            "interaction_mode": operation.interaction_mode.value,
        }
    return dict(sorted(bindings.items()))


def _task_prompt(
    contract: PortableOperationalContract,
    bindings: dict[str, dict[str, Any]],
) -> str:
    public = contract.public
    lines = [
        f"Role: {public.role}",
        "",
        f"Objective: {public.objective}",
        "",
        f"Success: {public.success_description}",
    ]
    if public.constraints:
        lines.extend(["", "Constraints:"])
        lines.extend(f"- {item}" for item in public.constraints)
    lines.extend(["", "Operational tools:"])
    for prime_name, binding in bindings.items():
        lines.append(
            f"- `{prime_name}` -> {binding['kind']} `{binding['name']}`: "
            f"{binding['description']}"
        )
    submit_names = [
        prime_name
        for prime_name, binding in bindings.items()
        if binding["kind"] == "operation" and binding["name"] == "submit"
    ]
    if submit_names:
        lines.extend(
            [
                "",
                "When the task is complete, call the submit runtime tool with the portable ",
                "submission fields (conclusion, claimed_state, evidence_ids, confidence).",
                f"Submit tool: `{submit_names[0]}`",
            ]
        )
    return "\n".join(lines).strip()


def _validate_contracts(
    contracts: Iterable[PortableOperationalContract],
) -> list[PortableOperationalContract]:
    values = list(contracts)
    if not values:
        raise PrimeOperationalExportError("Prime operational export requires at least one contract")

    validated: list[PortableOperationalContract] = []
    public_ids: set[str] = set()
    for contract in values:
        try:
            canonical = PortableOperationalContract.model_validate(
                contract.model_dump(mode="python")
            )
            # Construction is the losslessness gate for the merged portable runtime.
            PortableOperationalRuntime(canonical)
        except Exception as exc:
            raise PrimeOperationalExportError(
                "portable contract is not executable by the merged Portable Runtime Protocol: "
                f"{exc}"
            ) from exc
        public_id = canonical.public.public_id
        if public_id in public_ids:
            raise PrimeOperationalExportError(
                f"duplicate portable public identity in Prime export: {public_id}"
            )
        public_ids.add(public_id)
        validated.append(canonical)
    return sorted(validated, key=lambda item: item.public.public_id)


def _validate_requirement(requirement: str) -> str:
    normalized = requirement.strip()
    if not normalized:
        raise PrimeOperationalExportError("Veritas runtime requirement cannot be empty")
    lowered = normalized.casefold()
    forbidden = ("file://", "../", "..\\", " @ ./", " @ ../", "-e ")
    if any(token in lowered for token in forbidden):
        raise PrimeOperationalExportError(
            "Veritas runtime requirement must be a declared remote or registry dependency"
        )
    return normalized


def _render_pyproject(*, export_id: str, task_count: int, veritas_requirement: str) -> str:
    local_version = f"{PACKAGE_VERSION}+{export_id[:12]}"
    requirement = json.dumps(veritas_requirement)
    return f'''[project]
name = "veritas-prime-operational"
version = "{local_version}"
description = "Generated generic Veritas operational taskset for Prime Verifiers v1"
requires-python = ">=3.12,<3.14"
dependencies = [
  "verifiers>=0.2,<0.3",
  "mcp>=1.24,<2",
  "pydantic>=2.12,<3",
  {requirement},
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["{PACKAGE_MODULE}"]

[tool.verifiers.eval]
num_examples = {task_count}
rollouts_per_example = 1
'''


def _render_readme(*, export_id: str, task_count: int) -> str:
    return f'''# Veritas generic operational export for Prime Verifiers v1

Export identity: `{export_id}`  
Tasks: `{task_count}`

This generated distribution targets `verifiers.v1`. It separates Prime task data, the
operational tool/runtime bridge, and the reward hook while delegating transition and reward
semantics to `PortableOperationalRuntime`.

## Privacy boundary

`{PACKAGE_MODULE}/public_tasks.json` is the only task dataset loaded into Prime `TaskData`.
It contains the complete **public** `PortablePublicContract`, including the canonical action and
runtime-operation schemas. It contains no evaluator-private contract.

`{PACKAGE_MODULE}/private_contracts.json` is evaluator-private material required to execute and
score the environment. Treat the generated wheel as an evaluator/operator artifact when sealed
truth matters. Do not publish that file or the wheel to an agent-accessible package registry.
The task-scoped MCP server returns only portable observations or public failure messages; it does
not return reward components, hidden state, state digests, or evaluator budget state to the agent.

Prime traces record only the public task row plus normal tool traffic. The scalar Prime reward is
computed by replaying the executed public requests through `PortableOperationalRuntime`, so Prime
and the portable runtime have one reward authority.

## Runtime installation

The generated package declares all runtime dependencies in `pyproject.toml`. The default Veritas
requirement is an immutable Git dependency, so a Veritas development checkout is not required.
When a first-party `investigation-world` wheel is published, callers may replace that requirement
with an equivalent pinned registry requirement at export time.

## Legacy compatibility

The existing SRE-specific exporter at `investigation_world.portability.prime` remains the legacy
compatibility path. It is intentionally not imported or reimplemented here and is not the generic
abstraction.
'''


_TASKSET_MODULE = r'''from __future__ import annotations

import copy
from functools import lru_cache
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
import verifiers.v1 as vf

from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.portable_runtime import (
    PortableInvocationKind,
    PortableOperationalRuntime,
    PortableStepRequest,
    PortableStepResult,
)


class OperationalTaskData(vf.TaskData):
    portable_public_id: str
    public_contract: dict[str, Any]
    tool_bindings: dict[str, dict[str, Any]]
    seed: int = 0


class OperationalState(vf.State):
    requests: list[dict[str, Any]] = Field(default_factory=list)


class _RawArguments(BaseModel):
    """FastMCP call carrier; PortableOperationalRuntime performs canonical validation."""

    model_config = ConfigDict(extra="allow")

    def model_dump_one_level(self) -> dict[str, Any]:
        return dict(self.model_extra or {})


@lru_cache(maxsize=1)
def _private_payloads() -> dict[str, dict[str, Any]]:
    path = Path(__file__).with_name("private_contracts.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("private_contracts.json must contain an object")
    return payload


def _load_contract(public_id: str) -> PortableOperationalContract:
    payload = _private_payloads().get(public_id)
    if payload is None:
        raise RuntimeError(f"no evaluator-private contract for public identity {public_id}")
    return PortableOperationalContract.model_validate(payload)


def _invoke(
    runtime: PortableOperationalRuntime,
    request: dict[str, Any],
) -> PortableStepResult:
    kind = request["kind"]
    name = request["name"]
    arguments = dict(request.get("arguments") or {})
    if kind == "operation" and name == "submit":
        return runtime.submit(arguments)
    return runtime.step(
        PortableStepRequest(
            kind=PortableInvocationKind(kind),
            name=name,
            arguments=arguments,
        )
    )


def _runtime_after(
    contract: PortableOperationalContract,
    requests: list[dict[str, Any]],
    *,
    seed: int,
) -> PortableOperationalRuntime:
    runtime = PortableOperationalRuntime(contract)
    runtime.reset(seed=seed)
    for request in requests:
        _invoke(runtime, request)
    return runtime


def _reward_result(
    contract: PortableOperationalContract,
    requests: list[dict[str, Any]],
    *,
    seed: int,
) -> PortableStepResult | None:
    runtime = PortableOperationalRuntime(contract)
    runtime.reset(seed=seed)
    reward_result: PortableStepResult | None = None
    last_result: PortableStepResult | None = None
    for request in requests:
        last_result = _invoke(runtime, request)
        if last_result.reward is not None:
            reward_result = last_result
    return reward_result or last_result


def _public_failure(result: PortableStepResult) -> str:
    failure = result.failure
    if failure is None:
        return "portable runtime rejected the request"
    code = failure.code.value if hasattr(failure.code, "value") else str(failure.code)
    return f"{code}: {failure.message}"


class OperationalToolset(vf.Toolset[vf.ToolsetConfig, OperationalState]):
    # Tool names are already adapter-namespaced and are kept bare in Prime.
    TOOL_PREFIX = None

    def __init__(self, config: vf.ToolsetConfig) -> None:
        super().__init__(config)
        self._task_data: OperationalTaskData | None = None

    async def setup_task(self, task: OperationalTaskData) -> None:
        self._task_data = task
        # Fail before serving tools if evaluator-private material is absent or invalid.
        _load_contract(task.portable_public_id)

    def register(self, mcp) -> None:
        if self._task_data is None:
            raise RuntimeError("Prime operational toolset has no task data")
        data = self._task_data
        contract = _load_contract(data.portable_public_id)

        manager = getattr(mcp, "_tool_manager", None)
        if manager is None or not hasattr(manager, "get_tool"):
            raise RuntimeError(
                "Prime operational export requires FastMCP 1.x raw-schema registration support"
            )

        def make_invoke(binding: dict[str, Any]):
            async def invoke(**kwargs: Any) -> Any:
                runtime = _runtime_after(
                    contract,
                    self.state.requests,
                    seed=data.seed,
                )
                request = {
                    "kind": binding["kind"],
                    "name": binding["name"],
                    "arguments": dict(kwargs),
                }
                result = _invoke(runtime, request)
                # Record every canonical invocation, including rejected calls whose budget/event
                # effects must survive deterministic replay.
                self.state.requests.append(request)
                if result.failure is not None:
                    raise RuntimeError(_public_failure(result))
                # Never expose reward, reward components, hidden state digest, or private budgets.
                return result.observation

            return invoke

        for tool_name, binding in sorted(data.tool_bindings.items()):
            fn = make_invoke(binding)
            fn.__name__ = tool_name
            fn.__doc__ = binding["description"]
            mcp.add_tool(
                fn,
                name=tool_name,
                description=binding["description"],
                structured_output=False,
            )
            tool = manager.get_tool(tool_name)
            if tool is None:
                raise RuntimeError(f"FastMCP failed to register tool {tool_name}")
            # Verifiers v1 pins MCP 1.x, whose public FastMCP API derives schemas only from
            # Python signatures. Patch the registered internal descriptor fail-closed so the
            # model receives the exact portable JSON Schema while canonical validation remains
            # in PortableOperationalRuntime. No portable constraint is weakened or narrowed.
            tool.parameters = copy.deepcopy(binding["input_schema"])
            tool.fn_metadata.arg_model = _RawArguments


class OperationalTaskConfig(vf.TaskConfig):
    tools: vf.ToolsetConfig = vf.ToolsetConfig()


class OperationalTask(
    vf.Task[OperationalTaskData, OperationalState, OperationalTaskConfig]
):
    @property
    def key(self) -> str:
        return f"poc:{self.data.portable_public_id}"

    @classmethod
    def toolsets(cls, config: OperationalTaskConfig) -> list[vf.Toolset]:
        return [OperationalToolset(config.tools)]

    @vf.reward(weight=1.0)
    async def portable_runtime_reward(self, trace: vf.Trace) -> float:
        contract = _load_contract(self.data.portable_public_id)
        requests = list(getattr(trace.state, "requests", ()))
        result = _reward_result(contract, requests, seed=self.data.seed)
        if result is None or result.reward is None:
            return 0.0
        return float(result.reward)


class OperationalConfig(vf.TasksetConfig):
    task: OperationalTaskConfig = OperationalTaskConfig()


class OperationalTaskset(vf.Taskset[OperationalTask, OperationalConfig]):
    def load(self) -> list[OperationalTask]:
        rows = json.loads(
            Path(__file__).with_name("public_tasks.json").read_text(encoding="utf-8")
        )
        rows.sort(key=lambda row: row["portable_public_id"])
        return [
            OperationalTask(
                OperationalTaskData(idx=index, **row),
                self.config.task,
            )
            for index, row in enumerate(rows)
        ]


__all__ = [
    "OperationalConfig",
    "OperationalState",
    "OperationalTask",
    "OperationalTaskData",
    "OperationalTaskset",
    "OperationalToolset",
]


if __name__ == "__main__":
    OperationalToolset.run()
'''


def _render_init() -> str:
    return '''from veritas_prime_operational.taskset import (\n    OperationalConfig,\n    OperationalTask,\n    OperationalTaskData,\n    OperationalTaskset,\n)\n\n__all__ = [\n    "OperationalConfig",\n    "OperationalTask",\n    "OperationalTaskData",\n    "OperationalTaskset",\n]\n'''


def replay_portable_requests(
    contract: PortableOperationalContract,
    requests: Iterable[PrimeReplayRequest],
    *,
    seed: int = 0,
) -> PortableStepResult | None:
    """Replay Prime adapter requests through the portable runtime without reimplementing it."""

    runtime = PortableOperationalRuntime(contract)
    runtime.reset(seed=seed)
    reward_result: PortableStepResult | None = None
    last_result: PortableStepResult | None = None
    for request in requests:
        if request.kind == "operation" and request.name == "submit":
            last_result = runtime.submit(request.arguments)
        else:
            last_result = runtime.step(
                PortableStepRequest(
                    kind=PortableInvocationKind(request.kind),
                    name=request.name,
                    arguments=request.arguments,
                )
            )
        if last_result.reward is not None:
            reward_result = last_result
    return reward_result or last_result


def _write_files(output_dir: Path, files: dict[str, str]) -> tuple[PrimePackageFile, ...]:
    root = output_dir.resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError("Prime export output directory must be empty")
    root.mkdir(parents=True, exist_ok=True)

    written: list[PrimePackageFile] = []
    for relative_path, text in sorted(files.items()):
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise PrimeOperationalExportError(
                f"generated package path must stay relative: {relative_path}"
            )
        target = (root / relative).resolve()
        if target != root and root not in target.parents:
            raise PrimeOperationalExportError(
                f"generated package path escapes output directory: {relative_path}"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = text.encode("utf-8")
        target.write_bytes(payload)
        written.append(
            PrimePackageFile(
                path=relative.as_posix(),
                sha256=hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            )
        )
    return tuple(written)


def build_prime_operational_package(
    output_dir: Path,
    *,
    contracts: Iterable[PortableOperationalContract],
    veritas_requirement: str = DEFAULT_VERITAS_REQUIREMENT,
) -> PrimePackageBuildResult:
    """Build a generic evaluator-side Prime Verifiers v1 operational taskset package."""

    validated = _validate_contracts(contracts)
    requirement = _validate_requirement(veritas_requirement)
    identity_payload = {
        "adapter": ADAPTER_ID,
        "schema": EXPORT_SCHEMA_VERSION,
        "contract_ids": [contract.contract_id for contract in validated],
    }
    export_id = "prime-op-" + hashlib.sha256(
        _canonical_json(identity_payload).encode("utf-8")
    ).hexdigest()

    public_rows: list[dict[str, Any]] = []
    private_contracts: dict[str, dict[str, Any]] = {}
    for contract in validated:
        bindings = _tool_bindings(contract)
        public_rows.append(
            {
                "portable_public_id": contract.public.public_id,
                "prompt": _task_prompt(contract, bindings),
                "public_contract": contract.public.model_dump(mode="json"),
                "tool_bindings": bindings,
                "seed": 0,
            }
        )
        private_contracts[contract.public.public_id] = contract.model_dump(mode="json")

    files = {
        "pyproject.toml": _render_pyproject(
            export_id=export_id,
            task_count=len(validated),
            veritas_requirement=requirement,
        ),
        "README.md": _render_readme(export_id=export_id, task_count=len(validated)),
        f"{PACKAGE_MODULE}/__init__.py": _render_init(),
        f"{PACKAGE_MODULE}/taskset.py": _TASKSET_MODULE,
        f"{PACKAGE_MODULE}/public_tasks.json": _json_document(public_rows),
        f"{PACKAGE_MODULE}/private_contracts.json": _json_document(private_contracts),
    }
    written = _write_files(output_dir, files)
    package_payload = {
        "adapter": ADAPTER_ID,
        "export_id": export_id,
        "files": [item.model_dump(mode="json") for item in written],
    }
    package_id = "PRIMEOP-" + hashlib.sha256(
        _canonical_json(package_payload).encode("utf-8")
    ).hexdigest()[:24].upper()
    return PrimePackageBuildResult(
        package_id=package_id,
        export_id=export_id,
        output_dir=str(output_dir.resolve()),
        files=written,
    )
