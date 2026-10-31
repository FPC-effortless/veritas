"""TrainLab local CLI and dashboard."""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from pathlib import Path

from .runner import LabError, compare_runs, list_runs, run_experiment, verify_run


def main() -> int:
    parser = argparse.ArgumentParser(
        description="TrainLab: local experiments and comparison records"
    )
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
    serve.add_argument(
        "--forge-workspace", type=Path, help="Enable the Forge dataset GUI at /forge/"
    )
    serve.add_argument(
        "--experiments",
        type=Path,
        help="Enable execution of trusted *.json configs from this directory",
    )
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument(
        "--production", action="store_true", help="Use authenticated production WSGI hosting"
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--auth-file", type=Path)
    serve.add_argument("--public-origin", help="HTTPS origin served by your TLS reverse proxy")
    auth = commands.add_parser("init-auth", help="Create private hashed operator credentials")
    auth.add_argument("destination", type=Path)
    auth.add_argument("--username", required=True)
    health = commands.add_parser("health", help="Inspect aggregate run-store health")
    health.add_argument("--runs", type=Path, default=Path(".trainlab/runs"))
    backup = commands.add_parser(
        "backup", help="Back up finalized verified runs while the server is stopped"
    )
    backup.add_argument("destination", type=Path)
    backup.add_argument("--runs", type=Path, default=Path(".trainlab/runs"))
    restore = commands.add_parser(
        "restore", help="Verify and restore a pinned backup into a NEW store"
    )
    restore.add_argument("archive", type=Path)
    restore.add_argument("--runs", type=Path, required=True)
    restore.add_argument("--sha256", required=True)
    recover = commands.add_parser("recover", help="Finalize a crashed run offline as interrupted")
    recover.add_argument("directory", type=Path)
    recover.add_argument("--confirm-no-running-jobs", action="store_true")
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
        elif args.command == "init-auth":
            from .production import create_credentials

            if not sys.stdin.isatty():
                raise LabError(
                    "init-auth requires an interactive terminal to read a password privately"
                )
            password = getpass.getpass("Operator password (12+ characters): ")
            if password != getpass.getpass("Confirm password: "):
                raise LabError("passwords do not match")
            create_credentials(args.destination, args.username, password)
            result = {"credentials_created": True}
        elif args.command == "health":
            from .operations import store_health

            result = store_health(args.runs)
        elif args.command == "backup":
            from .operations import backup_runs

            result = backup_runs(args.runs, args.destination)
        elif args.command == "restore":
            from .operations import restore_runs

            result = restore_runs(args.archive, args.runs, expected_sha256=args.sha256)
        elif args.command == "recover":
            from .operations import recover_run

            result = recover_run(
                args.directory, confirm_no_running_jobs=args.confirm_no_running_jobs
            )
        else:
            if args.production:
                from .production import serve_production

                serve_production(
                    args.runs,
                    args.experiments,
                    auth_file=args.auth_file,
                    public_origin=args.public_origin,
                    host=args.host,
                    port=args.port,
                    forge_workspace=args.forge_workspace,
                )
                return 0
            if args.host != "127.0.0.1" or args.auth_file or args.public_origin:
                raise LabError("remote/authentication options require --production")
            from .server import Dashboard

            with Dashboard(
                args.runs, args.experiments, args.port, forge_workspace=args.forge_workspace
            ) as server:
                print(f"TrainLab: http://127.0.0.1:{server.server_port}", flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    print("\nClosing dashboard and interrupting any active experiment.")
            return 0
        print(json.dumps(result, indent=2, sort_keys=True))
        if args.command == "run" and result["status"] != "succeeded":
            return 1
        if args.command == "verify" and not result["valid"]:
            return 1
        if args.command == "health" and result["status"] != "ok":
            return 1
        return 0
    except (LabError, OSError, ValueError) as exc:
        parser.exit(2, f"trainlab: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
