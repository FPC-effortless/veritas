from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from investigation_world.mcp_compiler import compile_mcp_surface, dispatch_mcp_tool
from investigation_world.portable_contract import PortableOperationalContract
from investigation_world.portable_runtime import PortableOperationalRuntime, PortableStepResult


class HarborVerificationError(RuntimeError):
    """Trajectory evidence is missing, inconsistent, or not replayable."""


@dataclass(frozen=True)
class HarborVerificationResult:
    reward: float
    reward_components: dict[str, float] | None
    final_result: dict[str, Any]
    replayed_tool_calls: int


def _records(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HarborVerificationError(f"trajectory artifact unavailable: {path}") from exc
    if not lines:
        raise HarborVerificationError("trajectory artifact is empty")
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarborVerificationError(f"invalid trajectory JSON at line {index}") from exc
        if not isinstance(record, dict):
            raise HarborVerificationError(f"trajectory line {index} is not an object")
        records.append(record)
    return records


def replay_harbor_trajectory(
    contract: PortableOperationalContract,
    records: list[dict[str, Any]],
) -> HarborVerificationResult:
    if not records or records[0].get("kind") != "reset":
        raise HarborVerificationError("trajectory must begin with a reset record")
    header = records[0]
    surface = compile_mcp_surface(contract.public)
    if header.get("contract_id") != contract.contract_id:
        raise HarborVerificationError("trajectory contract_id does not match verifier contract")
    if header.get("public_contract_id") != contract.public.public_id:
        raise HarborVerificationError(
            "trajectory public_contract_id does not match verifier contract"
        )
    if header.get("surface_id") != surface.surface_id:
        raise HarborVerificationError("trajectory MCP surface does not match shared compiler output")
    seed = header.get("seed")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise HarborVerificationError("trajectory reset seed is invalid")

    runtime = PortableOperationalRuntime(contract)
    reset = runtime.reset(seed=seed)
    if header.get("result") != reset.model_dump(mode="json"):
        raise HarborVerificationError("deterministic reset evidence does not replay")

    rewarded: PortableStepResult | None = None
    final_result: PortableStepResult | None = None
    replayed = 0
    for index, event in enumerate(records[1:], start=2):
        if event.get("kind") != "tool_call":
            raise HarborVerificationError(f"unsupported trajectory event at line {index}")
        name = event.get("name")
        arguments = event.get("arguments")
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise HarborVerificationError(f"invalid tool call at line {index}")
        try:
            result = dispatch_mcp_tool(runtime, surface, name, arguments)
        except Exception as exc:
            raise HarborVerificationError(
                f"tool call at line {index} cannot be replayed"
            ) from exc
        if event.get("result") != result.model_dump(mode="json"):
            raise HarborVerificationError(f"tool result mismatch at line {index}")
        replayed += 1
        final_result = result
        if result.reward is not None:
            if rewarded is not None:
                raise HarborVerificationError(
                    "trajectory contains multiple rewarded terminal results"
                )
            rewarded = result

    if rewarded is None:
        final_result = runtime.verify()
        rewarded = final_result
    if rewarded.reward is None:
        raise HarborVerificationError("native verifier produced no reward")
    components = (
        rewarded.reward_components.model_dump(mode="json")
        if rewarded.reward_components is not None
        else None
    )
    return HarborVerificationResult(
        reward=rewarded.reward,
        reward_components=components,
        final_result=(final_result or rewarded).model_dump(mode="json"),
        replayed_tool_calls=replayed,
    )


def verify_harbor_trajectory_file(
    contract_path: Path,
    trajectory_path: Path,
) -> HarborVerificationResult:
    contract = PortableOperationalContract.model_validate_json(
        contract_path.read_text(encoding="utf-8")
    )
    return replay_harbor_trajectory(contract, _records(trajectory_path))


def _write_outputs(
    result: HarborVerificationResult,
    reward_path: Path,
    details_path: Path,
) -> None:
    reward_path.parent.mkdir(parents=True, exist_ok=True)
    details_path.parent.mkdir(parents=True, exist_ok=True)
    reward_path.write_text(f"{result.reward:.6f}\n", encoding="utf-8")
    details_path.write_text(
        json.dumps(
            {
                "reward": result.reward,
                "reward_components": result.reward_components,
                "final_result": result.final_result,
                "replayed_tool_calls": result.replayed_tool_calls,
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay and natively verify a Harbor trajectory"
    )
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--trajectory", type=Path, required=True)
    parser.add_argument("--reward", type=Path, required=True)
    parser.add_argument("--details", type=Path, required=True)
    args = parser.parse_args()
    result = verify_harbor_trajectory_file(args.contract, args.trajectory)
    _write_outputs(result, args.reward, args.details)


if __name__ == "__main__":
    main()
