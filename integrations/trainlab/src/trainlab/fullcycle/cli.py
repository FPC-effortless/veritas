"""Full lifecycle and registered-model subcommands, imported only when selected."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from trainlab.runner import LabError, read_json


def main(argv):
    parser = argparse.ArgumentParser(prog="trainlab")
    commands = parser.add_subparsers(dest="command", required=True)
    pipeline = commands.add_parser("pipeline").add_subparsers(dest="action", required=True)
    run = pipeline.add_parser("run")
    run.add_argument("config", type=Path)
    run.add_argument("--output", type=Path, required=True)
    run.add_argument("--stop-stage", choices=["pretrain", "midtrain", "sft", "dpo", "rl"])
    run.add_argument("--stop-after", type=int)
    for action in ("resume", "status", "report", "verify"):
        p = pipeline.add_parser(action)
        p.add_argument("directory", type=Path)
    data = commands.add_parser("data").add_subparsers(dest="action", required=True)
    for action in ("fetch", "prepare"):
        command = data.add_parser(action)
        command.add_argument("plan", type=Path)
        command.add_argument("--cache", type=Path, required=True)
    status = data.add_parser("status")
    status.add_argument("directory", type=Path)
    models = commands.add_parser("model").add_subparsers(dest="action", required=True)
    chat = models.add_parser("chat")
    chat.add_argument("directory", type=Path)
    chat.add_argument("--prompt")
    chat.add_argument("--max-new-tokens", type=int, default=48)
    chat.add_argument("--device", default="cpu")
    serve = models.add_parser("serve")
    serve.add_argument("directory", type=Path)
    serve.add_argument("--port", type=int, default=8787)
    serve.add_argument("--device", default="cpu")
    args = parser.parse_args(argv)
    try:
        if args.command == "data":
            from forge_data.hub import acquire, prepare

            if args.action == "fetch":
                result = acquire(args.plan, args.cache)
            elif args.action == "prepare":
                result = prepare(args.plan, args.cache)
            else:
                result = {
                    name: read_json(args.directory / name, limit=32 * 1024 * 1024)
                    for name in ("acquisition.json", "prepared.json")
                    if (args.directory / name).exists()
                }
        elif args.command == "pipeline":
            if args.action in ("run", "resume"):
                from .pipeline import run_pipeline

                result = (
                    run_pipeline(
                        args.config,
                        args.output,
                        stop_stage=args.stop_stage,
                        stop_after=args.stop_after,
                    )
                    if args.action == "run"
                    else run_pipeline(output=args.directory, resume=True)
                )
            elif args.action == "verify":
                from .pipeline import verify_pipeline

                result = verify_pipeline(args.directory)
            else:
                result = read_json(
                    args.directory / ("state.json" if args.action == "status" else "report.json"),
                    limit=32 * 1024 * 1024,
                )
        elif args.action == "serve":
            from .inference import serve_chat

            serve_chat(args.directory, port=args.port, device=args.device)
            return 0
        else:
            import torch

            from .inference import load_bundle, reply

            torch.set_num_threads(2)
            model, tokens = load_bundle(args.directory, device=args.device)
            messages = []
            if args.prompt is not None:
                print(
                    reply(
                        model,
                        tokens,
                        [{"role": "user", "content": args.prompt}],
                        max_new_tokens=args.max_new_tokens,
                    )
                )
                return 0
            print("Local research model. Type /reset or /quit.")
            while True:
                try:
                    prompt = input("you> ")
                except EOFError:
                    break
                if prompt == "/quit":
                    break
                if prompt == "/reset":
                    messages.clear()
                    continue
                messages.append({"role": "user", "content": prompt})
                answer = reply(model, tokens, messages, max_new_tokens=args.max_new_tokens)
                messages.append({"role": "assistant", "content": answer})
                print("model> " + answer)
            return 0
        if args.command == "pipeline":
            import torch.distributed as dist

            if dist.is_initialized():
                dist.barrier()
                dist.destroy_process_group()
        print(json.dumps(result, sort_keys=True, indent=2))
        return 0
    except (LabError, ValueError, OSError) as exc:
        parser.exit(2, f"trainlab: {exc}\n")
