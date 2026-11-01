"""Compare a paused CPU pretraining checkpoint with an uninterrupted control.

Run after --stop-stage pretrain --stop-after 32. The primary run advances by
one update and pauses again. Control updates are separate from its work metrics.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

import torch
from forge_data.language import LanguageRelease
from trainlab.fullcycle.pipeline import run_pipeline
from trainlab.fullcycle.tokenization import Tokens
from trainlab.fullcycle.training import checkpoint_load, train_stage
from trainlab.runner import contained_file, digest, read_json, write_json


def identical(first, second):
    if isinstance(first, torch.Tensor):
        return isinstance(second, torch.Tensor) and torch.equal(first, second)
    if isinstance(first, dict):
        return first.keys() == second.keys() and all(identical(first[k], second[k]) for k in first)
    if isinstance(first, (tuple, list)):
        return len(first) == len(second) and all(identical(a, b) for a, b in zip(first, second))
    return first == second


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run, output = args.run.resolve(), args.output.resolve()
    config, protocol = read_json(run / "pipeline.json"), read_json(run / "protocol.json")
    if protocol["runtime"]["device"] != "cpu" or protocol["world_size"] != 1:
        parser.error("this correspondence driver is a single-process CPU check")
    stage = config["stages"][0]
    index = read_json(run / "pretrain/checkpoint-index.json")
    paused = checkpoint_load(contained_file(run / "pretrain", index["file"]))
    if stage["name"] != "pretrain" or not 0 < paused["step"] < stage["steps"] - 1:
        parser.error(
            "requires an incomplete pretraining checkpoint with a remaining control update"
        )
    output.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(run / "initial.pt", output / "initial.pt")
    shutil.copyfile(contained_file(run / "pretrain", index["file"]), output / "paused.pt")
    next_step = paused["step"] + 1
    torch.set_num_threads(config.get("cpu_threads", 2))
    torch.use_deterministic_algorithms(config.get("deterministic", True))
    release = LanguageRelease(config["dataset"]["directory"], config["dataset"]["manifest_sha256"])
    train_stage(
        paused["model_config"],
        stage,
        release,
        Tokens(run / "tokenizer.json"),
        run / "tokens",
        output / "control",
        previous=run / "initial.pt",
        seed=config["seed"],
        device="cpu",
        precision="fp32",
        stop_after=next_step,
        checkpoint_every=config.get("checkpoint_every", 25),
        input_identity=index["input_identity"],
    )
    run_pipeline(output=run, resume=True, stop_stage="pretrain", stop_after=next_step)
    selected = read_json(run / "pretrain/checkpoint-index.json")
    shutil.copyfile(contained_file(run / "pretrain", selected["file"]), output / "resumed.pt")
    control_index = read_json(output / "control/checkpoint-index.json")
    control_path = contained_file(output / "control", control_index["file"])
    control, resumed = checkpoint_load(control_path), checkpoint_load(output / "resumed.pt")
    checked = ("model", "optimizer", "scaler", "losses", "trained_tokens", "target_tokens", "step")
    findings = {field: identical(control[field], resumed[field]) for field in checked}
    for field in ("data_rng", "torch_rng", "cuda_rng"):
        findings[field] = identical(control["runtimes"][0][field], resumed["runtimes"][0][field])
    report = {
        "schema": "trainlab.fullcycle003-recovery.v1",
        "passed": all(findings.values()),
        "checks": findings,
        "paused_at": paused["step"],
        "compared_at": resumed["step"],
        "control_optimizer_updates": control["step"],
        "control_checkpoint_sha256": digest(control_path),
        "resumed_checkpoint_sha256": digest(output / "resumed.pt"),
        "source_files": protocol["source_files"],
        "runtime": protocol["runtime"],
        "scope": "bit-exact CPU correspondence; control work is outside the primary run",
        "qualification": "NOT_QUALIFIED",
    }
    write_json(output / "report.json", report)
    print(report)
    if not report["passed"]:
        raise SystemExit("recovery diverged from uninterrupted control")


if __name__ == "__main__":
    main()
