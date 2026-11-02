from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trainlab.runner import read_json

from .core import ROLES, Controller, LabError


def parser():
    p = argparse.ArgumentParser(description="Persistent research operations around TrainLab")
    p.add_argument("--root", type=Path, default=Path(".trainlab/research-lab"))
    sub = p.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init")
    init.add_argument("--program", required=True)
    init.add_argument("--objective", required=True)
    init.add_argument("--seconds", type=float, required=True)
    init.add_argument("--microusd", type=int, default=0)
    init.add_argument("--allow-paid", action="store_true")
    init.add_argument("--cpu-slots", type=int, default=1)
    resource = sub.add_parser("resource")
    resource.add_argument("id")
    resource.add_argument("--kind", choices=["cpu", "gpu"], required=True)
    resource.add_argument("--slots", type=int, required=True)
    resource.add_argument("--rate-microusd", type=int, default=0)
    for command in ("register", "order"):
        command_parser = sub.add_parser(command)
        command_parser.add_argument("path", type=Path)
        command_parser.add_argument("--recipes", type=Path)
    worker = sub.add_parser("worker")
    worker.add_argument("id")
    worker.add_argument("--role", choices=sorted(ROLES - {"review"}), required=True)
    worker.add_argument("--principal")
    worker.add_argument("--resource", default="local")
    worker.add_argument("--watch", action="store_true")
    sub.add_parser("status")
    sub.add_parser("direct")
    sub.add_parser("expire")
    lane = sub.add_parser("activate")
    lane.add_argument("path", type=Path)
    lane.add_argument("--recipes", type=Path)
    sub.add_parser("dispatch")
    supervisor = sub.add_parser("supervise")
    supervisor.add_argument("workers", type=Path)
    recover = sub.add_parser("recover")
    recover.add_argument("task")
    recover.add_argument("--confirmed-stopped", action="store_true")
    for command in ("proposal", "catalog"):
        action = sub.add_parser(command)
        action.add_argument("path", type=Path)
    memory = sub.add_parser("memory")
    memory.add_argument("query", nargs="?", default="")
    synth = sub.add_parser("synthesize")
    synth.add_argument("protocol")
    review = sub.add_parser("review")
    review.add_argument("protocol")
    review.add_argument("--worker", required=True)
    review.add_argument("--principal")
    review.add_argument("--receipt", type=Path, required=True)
    packet = sub.add_parser("package")
    packet.add_argument("protocol")
    packet.add_argument("destination", type=Path)
    for command in ("import-trainlab", "import-forge", "woyengi-handoff"):
        action = sub.add_parser(command)
        action.add_argument("path", type=Path)
        if command == "import-forge":
            action.add_argument("--manifest-sha256", required=True)
    server = sub.add_parser("serve")
    server.add_argument("--port", type=int, default=8770)
    server.add_argument("--forge-workspace", type=Path)
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    lab = Controller(args.root)
    try:
        from . import adapters, evidence
        from .agents import register_order
        from .execution import run_worker

        if args.command == "init":
            lab.program(
                args.program,
                args.objective,
                args.seconds,
                args.microusd,
                allow_paid=args.allow_paid,
            )
            lab.resource("local", "cpu", args.cpu_slots, 0)
            result = lab.status()
        elif args.command == "resource":
            lab.resource(args.id, args.kind, args.slots, args.rate_microusd)
            result = {"registered": args.id}
        elif args.command in ("register", "order"):
            action = (
                lab.register
                if args.command == "register"
                else lambda p, r: register_order(lab, p, r)
            )
            result = {"pin": action(read_json(args.path), args.recipes or args.path.parent)}
        elif args.command == "worker":
            lab.worker(args.id, args.role, args.resource, principal=args.principal)
            from .supervisor import signal_stop

            result = {"completed": run_worker(lab, args.id, watch=args.watch, stop=signal_stop())}
        elif args.command == "activate":
            from .autonomy import register_lane

            result = {
                "pin": register_lane(lab, read_json(args.path), args.recipes or args.path.parent)
            }
        elif args.command == "dispatch":
            from .autonomy import tick

            result = tick(lab)
        elif args.command == "supervise":
            from .supervisor import signal_stop, supervise

            supervise(lab, read_json(args.workers), stop=signal_stop())
            result = {"supervisor": "stopped"}
        elif args.command == "status":
            result = lab.status()
        elif args.command == "expire":
            result = {"quarantined": lab.expire()}
        elif args.command == "recover":
            lab.recover(args.task, confirmed_stopped=args.confirmed_stopped)
            result = {"recovered": args.task}
        elif args.command == "proposal":
            result = {"pin": evidence.ingest_proposal(lab, read_json(args.path))}
        elif args.command == "catalog":
            result = adapters.import_catalog(lab, args.path)
        elif args.command == "memory":
            result = evidence.retrieve(lab, args.query)
        elif args.command == "direct":
            result = evidence.direct(lab)
        elif args.command == "synthesize":
            result = lab.synthesize(args.protocol)
        elif args.command == "review":
            from .execution import submit_review

            receipt = read_json(args.receipt)

            lab.worker(
                args.worker,
                "review",
                lab.protocol(args.protocol)["resource"],
                principal=args.principal,
            )
            result = submit_review(lab, args.protocol, args.worker, receipt)
        elif args.command == "package":
            result = evidence.prepare_publication(lab, args.protocol, args.destination)
        elif args.command == "import-trainlab":
            result = {"pin": adapters.import_trainlab(lab, args.path)}
        elif args.command == "import-forge":
            result = {"pin": adapters.import_forge(lab, args.path, args.manifest_sha256)}
        elif args.command == "woyengi-handoff":
            result = adapters.woyengi_handoff(lab, args.path)
        else:
            from trainlab.server import Dashboard

            from .server import LabWorkspace

            server = Dashboard(
                args.root,
                None,
                args.port,
                workspace_factory=LabWorkspace,
                forge_workspace=args.forge_workspace,
            )
            print(f"Research Observatory: http://127.0.0.1:{server.server_port}", flush=True)
            try:
                server.serve_forever(poll_interval=0.5)
            finally:
                server.server_close()
            return 0
        print(json.dumps(result, indent=2, allow_nan=False))
        return 0
    except (LabError, OSError, ValueError) as exc:
        print("Research Lab OS: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
