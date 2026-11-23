"""Installed latent research CLI; offline analysis is the default."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..runner import LabError, read_json


def main(argv=None):
    parser = argparse.ArgumentParser(description="Veritas latent research diagnostics and evidence")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "catalog", help="List executable diagnostic operations and required capabilities"
    )
    freeze_cmd = commands.add_parser("freeze", help="Pin input hashes and the analysis plan")
    freeze_cmd.add_argument("draft", type=Path)
    freeze_cmd.add_argument("--output", type=Path, required=True)
    run = commands.add_parser("run", help="Run a frozen plan in a new output directory")
    run.add_argument("plan", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument(
        "--allow-native",
        action="store_true",
        help="Execute the explicitly pinned trusted local adapter factory",
    )
    run.add_argument("--select", nargs="+")
    run.add_argument("--no-figures", action="store_true")
    check = commands.add_parser("verify", help="Verify an externally pinned evidence bundle")
    check.add_argument("bundle", type=Path)
    check.add_argument("--sha256", required=True)
    replay = commands.add_parser(
        "reanalyze", help="Replay saved-output analysis with zero model calls"
    )
    replay.add_argument("bundle", type=Path)
    replay.add_argument("--sha256", required=True)
    replay.add_argument("--output", type=Path, required=True)
    replay.add_argument("--no-figures", action="store_true")
    export = commands.add_parser("export", help="Write and verify a portable evidence ZIP")
    export.add_argument("bundle", type=Path)
    export.add_argument("--sha256", required=True)
    export.add_argument("--output", type=Path, required=True)
    worker_cmd = commands.add_parser("worker", help="Execute inside an existing TrainLab recipe")
    worker_cmd.add_argument("plan", type=Path)
    worker_cmd.add_argument("--allow-native", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "catalog":
            from .registry import catalog

            result = [
                {"operation": op.name, "mode": op.mode, "requires": list(op.requires)}
                for op in catalog().values()
            ]
        elif args.command == "freeze":
            from .artifacts import freeze

            result = freeze(
                read_json(args.draft, limit=16 * 1024 * 1024), args.draft.parent, args.output
            )
        elif args.command == "verify":
            from .artifacts import verify_bundle

            doc = verify_bundle(args.bundle, args.sha256)
            result = {
                "verified": True,
                "state": doc["state"],
                "files": len(doc["files"]),
                "scientific_qualification": doc["scientific_qualification"],
            }
        elif args.command == "run":
            from .suite import run_plan

            result = run_plan(
                args.plan,
                args.output,
                allow_native=args.allow_native,
                selected=args.select,
                render_figures=not args.no_figures,
            )
        elif args.command == "reanalyze":
            from .suite import reanalyze

            result = reanalyze(
                args.bundle, args.sha256, args.output, render_figures=not args.no_figures
            )
        elif args.command == "export":
            from .suite import export_bundle

            result = export_bundle(args.bundle, args.sha256, args.output)
        else:
            from .suite import worker

            result = worker(args.plan, allow_native=args.allow_native)
        print(json.dumps(result, indent=2, sort_keys=True, allow_nan=False))
        if args.command == "reanalyze" and not result["byte_exact"]:
            return 1
        if args.command in ("run", "worker") and (
            result["state"] != "COMPLETE"
            or any(
                row["status"] in ("INCONCLUSIVE", "NOT_RUN") and row["reason"] != "NOT_SELECTED"
                for row in result["coverage"]
            )
        ):
            return 1
        return 0
    except (LabError, OSError, ValueError, ImportError) as exc:
        parser.exit(2, f"veritas-latent: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
