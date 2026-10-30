"""TrainLab local CLI and dashboard."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .runner import LabError, compare_runs, list_runs, run_experiment, verify_run


def main() -> int:
    parser = argparse.ArgumentParser(description="TrainLab: local experiments and comparison records")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Execute a trusted local experiment config")
    run.add_argument("config", type=Path)
    run.add_argument("--runs", type=Path, default=Path(".trainlab/runs"))
    listing = commands.add_parser("list", help="List persistent run records")
    listing.add_argument("--runs", type=Path, default=Path(".trainlab/runs"))
    compare = commands.add_parser("compare", help="Compare selected saved run IDs")
    compare.add_argument("ids", nargs="+")
    compare.add_argument("--runs", type=Path, default=Path(".trainlab/runs"))
    check = commands.add_parser("verify", help="Recompute saved file and artifact hashes")
    check.add_argument("directory", type=Path)
    serve = commands.add_parser("serve", help="Open the local dashboard")
    serve.add_argument("--runs", type=Path, default=Path(".trainlab/runs"))
    serve.add_argument("--experiments", type=Path, help="Enable execution of trusted *.json configs from this directory")
    serve.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    try:
        if args.command == "run":
            result = run_experiment(args.config, args.runs)
        elif args.command == "list":
            result = list_runs(args.runs)
        elif args.command == "compare":
            runs = {run["id"]: run for run in list_runs(args.runs)}
            if len(set(args.ids)) != len(args.ids) or any(key not in runs for key in args.ids):
                raise LabError("select distinct existing run IDs")
            result = compare_runs([runs[key] for key in args.ids])
        elif args.command == "verify":
            result = verify_run(args.directory)
        else:
            from .server import Dashboard
            with Dashboard(args.runs, args.experiments, args.port) as server:
                print(f"TrainLab: http://127.0.0.1:{server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    print("\nClosing dashboard; waiting for any active experiment to finish.")
            return 0
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "run" and result["status"] != "succeeded":
            return 1
        if args.command == "verify" and not result["valid"]:
            return 1
        return 0
    except (LabError, OSError, ValueError) as exc:
        parser.exit(2, f"trainlab: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
