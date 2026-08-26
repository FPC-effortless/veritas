from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.commercial import EvaluationManifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a reproducible Veritas evaluation manifest")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark-version", required=True)
    parser.add_argument("--benchmark-hash")
    parser.add_argument("--model", required=True)
    parser.add_argument("--harness", required=True)
    parser.add_argument("--attempts-per-task", type=int, default=1)
    parser.add_argument("--token-budget", type=int)
    parser.add_argument("--tool-budget", type=int)
    parser.add_argument("--wall-clock-seconds", type=int)
    parser.add_argument("--endpoint-host")
    parser.add_argument("--customer-reference")
    args = parser.parse_args()

    manifest = EvaluationManifest(
        benchmark_version=args.benchmark_version,
        benchmark_hash=args.benchmark_hash,
        model=args.model,
        harness=args.harness,
        attempts_per_task=args.attempts_per_task,
        token_budget=args.token_budget,
        tool_budget=args.tool_budget,
        wall_clock_seconds=args.wall_clock_seconds,
        endpoint_host=args.endpoint_host,
        customer_reference=args.customer_reference,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest.public_payload(), indent=2, sort_keys=True))
    print(args.output)


if __name__ == "__main__":
    main()
