"""Real CPU PyTorch model acceptance using a pinned CONSTRUCTED Forge release."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from dataset_quickstart import prepare
from trainlab.runner import LabError, digest, run_experiment, verify_run, write_json


def run_demo(destination: Path) -> dict:
    integrations = Path(__file__).resolve().parents[2]
    worker = integrations / "trainlab/examples/torch_model.py"
    lock = integrations / "trainlab/requirements-pytorch-cpu.txt"
    prepare(destination)
    destination = destination.resolve()
    pin = digest(destination / "dataset/manifest.json")
    checkpoint = exported = None
    records = []
    for label, kind, method, world in (
        ("supervised", "train", "supervised", 1),
        ("fine-tuning", "train", "fine_tuning", 1),
        ("distributed", "train", "supervised", 2),
        ("debug", "debug", None, 1),
        ("profile", "profile", None, 1),
        ("test", "test", None, 1),
        ("export", "export", None, 1),
        ("deployment-check", "deployment_check", None, 1),
    ):
        recipe_root = destination / "recipes" / label
        recipe_root.mkdir(parents=True)
        shutil.copyfile(worker, recipe_root / "torch_model.py")
        shutil.copyfile(lock, recipe_root / "requirements-pytorch-cpu.txt")
        shutil.copytree(destination / "dataset", recipe_root / "dataset")
        inputs = [
            "torch_model.py",
            "requirements-pytorch-cpu.txt",
            *[
                f"dataset/{name}"
                for name in ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")
            ],
        ]
        command = [sys.executable]
        if world > 1:
            command += [
                "-m",
                "torch.distributed.run",
                "--rdzv-backend=c10d",
                "--rdzv-endpoint=127.0.0.1:0",
                "--rdzv-conf=is_host=true,read_timeout=30",
                "--local-addr=127.0.0.1",
                "--nproc-per-node=2",
                "--nnodes=1",
                "--max-restarts=0",
            ]
        command += ["torch_model.py", "--task", kind, "--pin", pin, "--device", "cpu"]
        if checkpoint is not None and label != "distributed":
            shutil.copyfile(checkpoint, recipe_root / "checkpoint.pt")
            inputs.append("checkpoint.pt")
            command += ["--checkpoint", "checkpoint.pt"]
        if kind == "deployment_check":
            shutil.copyfile(exported, recipe_root / "model.pt2")
            inputs.append("model.pt2")
        metrics = {"validation_mse": "min"}
        checks = {"validation_mse": {"max": 0.01}}
        artifacts = ["runtime.json"]
        if kind == "train":
            artifacts += ["checkpoint.pt", *[f"rank-{rank}.json" for rank in range(world)]]
        if kind == "profile":
            artifacts.append("operators.json")
        if kind in ("export", "deployment_check"):
            metrics["export_max_error"] = "min"
            checks["export_max_error"] = {"max": 1e-6}
        if kind == "export":
            artifacts += ["model.pt2", "reference.json"]
        config = {
            "schema": "trainlab.experiment.v2",
            "name": f"PyTorch constructed {label}",
            "description": "Real CPU framework acceptance; constructed data, never qualification.",
            "command": command,
            "seed": 42,
            "timeout_seconds": 120,
            "source_kind": "CONSTRUCTED",
            "split_identity": pin,
            "inputs": inputs,
            "artifacts": artifacts,
            "metrics": metrics,
            "checks": checks,
            "budget": {
                "updates": 80 if kind == "train" else 0,
                "learned_parameters": 13,
                "worker_processes": world,
                "exposures": 80 * 8 * world if kind == "train" else 0,
            },
            "workload": {
                "kind": kind,
                "training_method": method,
                "execution": "distributed" if world > 1 else "single_process",
            },
        }
        path = recipe_root / "recipe.json"
        write_json(path, config)
        record = run_experiment(path, destination / "runs")
        records.append(record)
        directory = destination / "runs" / record["id"]
        if record["status"] != "succeeded" or not verify_run(directory)["valid"]:
            raise LabError(
                f"{label} {record['status']}: {record['error']}; "
                f"inspect retained run {record['id']}"
            )
        if kind == "train" and world == 1:
            checkpoint = directory / "output/checkpoint.pt"
        if kind == "export":
            exported = directory / "output/model.pt2"
    result = {
        "schema": "trainlab.pytorch_acceptance.v1",
        "source": "CONSTRUCTED_ONLY",
        "qualification": "NOT_QUALIFIED",
        "device": "cpu",
        "cuda": "NOT_RUN",
        "distributed": "TWO_LOCAL_GLOO_RANKS",
        "deployment": "LOCAL_CPU_EXPORT_CHECK_ONLY",
        "manifest_sha256": pin,
        "run_ids": [record["id"] for record in records],
    }
    write_json(destination / "workflow.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run_demo(args.output), sort_keys=True))


if __name__ == "__main__":
    main()
