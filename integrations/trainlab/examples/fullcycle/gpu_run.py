"""Launch a prepared fullcycle config on real CUDA hardware; never emulate GPUs."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import torch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("config", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gpus", type=int, default=1)
    parser.add_argument("--port", type=int, default=29500)
    args = parser.parse_args()
    if not torch.cuda.is_available() or not 1 <= args.gpus <= torch.cuda.device_count():
        parser.error("requested number of real CUDA devices is unavailable")
    if args.output.exists():
        parser.error("use a new output directory; resume with the same torchrun world size")
    config = json.loads(args.config.read_bytes())
    config["dataset"]["directory"] = str(
        (args.config.parent / config["dataset"]["directory"]).resolve()
    )
    config["device"] = "cuda"
    config["precision"] = (
        "fp32"
        if config["model"]["backend"] == "tac098"
        else "bf16"
        if torch.cuda.is_bf16_supported()
        else "fp16"
    )
    prepared = args.output.with_name(args.output.name + "-cuda-config.json")
    prepared.parent.mkdir(parents=True, exist_ok=True)
    prepared.write_text(json.dumps(config, sort_keys=True, indent=2) + "\n")
    command = [sys.executable]
    if args.gpus > 1:
        command += [
            "-m",
            "torch.distributed.run",
            "--nproc_per_node",
            str(args.gpus),
            "--master_addr",
            "127.0.0.1",
            "--master_port",
            str(args.port),
        ]
    command += ["-m", "trainlab", "pipeline", "run", str(prepared), "--output", str(args.output)]
    environment = dict(os.environ, CUBLAS_WORKSPACE_CONFIG=":4096:8")
    return subprocess.call(command, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
