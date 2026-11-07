"""CONSTRUCTED Forge -> TrainLab model lifecycle. No protected TEST or deployment.

From the repository root, with both packages installed or on PYTHONPATH:
python integrations/forge/examples/model_workflow.py --output /tmp/model-workflow
"""

from __future__ import annotations

import argparse
import json
import os
import random
import shutil
import sys
from pathlib import Path

from forge_data.dataset import Dataset
from trainlab.diagnostics import ModuleProfiler, require_finite
from trainlab.runner import LabError, digest, read_json, run_experiment, verify_run, write_json

FEATURE_CUTOFF = "2026-01-01T10:00:01Z"
TARGET_CUTOFF = "2026-01-02T10:00:00Z"


def predict(model, x, profiler=None):
    if profiler is None:
        return 61 * (model["slope"] * (x / 30) + model["bias"])
    with profiler.measure("encoder"):
        feature = x / 30
    with profiler.measure("affine"):
        hidden = model["slope"] * feature + model["bias"]
    with profiler.measure("output"):
        return 61 * hidden


def task(kind: str, pin: str, method: str | None):
    dataset = Dataset(Path("dataset"), manifest_sha256=pin)
    rows = dataset.examples(
        "validation",
        cutoff=FEATURE_CUTOFF,
        target_cutoff=TARGET_CUTOFF,
        feature_fields=["temperature"],
    )
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    model = {"slope": 0.0, "bias": 0.0}
    if Path("checkpoint.json").exists():
        model = read_json(Path("checkpoint.json"))
    metrics = {}
    report = {"kind": kind, "source": "CONSTRUCTED_ONLY", "qualification": "NOT_QUALIFIED"}
    if kind == "train":
        if method == "fine_tuning" and not Path("checkpoint.json").is_file():
            raise LabError("fine tuning requires the declared checkpoint")
        train = dataset.examples(
            "train",
            cutoff=FEATURE_CUTOFF,
            target_cutoff=TARGET_CUTOFF,
            feature_fields=["temperature"],
        )
        rng = random.Random(int(os.environ["TRAINLAB_SEED"]))
        for _ in range(600):
            rng.shuffle(train)
            gradient_slope = gradient_bias = 0.0
            for row in train:
                x = row["features"]["temperature"] / 30
                error = model["slope"] * x + model["bias"] - row["target"]["value"] / 61
                gradient_slope += 2 * error * x / len(train)
                gradient_bias += 2 * error / len(train)
            model["slope"] -= 0.2 * gradient_slope
            model["bias"] -= 0.2 * gradient_bias
        model.update(seed=int(os.environ["TRAINLAB_SEED"]), rng_state=rng.getstate())
        write_json(output / "checkpoint.json", model)
    elif kind == "debug":
        inspected = require_finite("parameters", [model["slope"], model["bias"]])
        inspected += require_finite(
            "predictions", [predict(model, row["features"]["temperature"]) for row in rows]
        )
        report["inspected_scalars"] = inspected
        metrics["inspected_scalars"] = inspected
    elif kind == "profile":
        profiler = ModuleProfiler()
        # Warmup is deliberately outside the measured regions.
        for row in rows:
            predict(model, row["features"]["temperature"])
        for _ in range(20):
            for row in rows:
                predict(model, row["features"]["temperature"], profiler)
        report = profiler.report()
        metrics["profile_calls"] = sum(row["calls"] for row in report["modules"].values())
    elif kind in ("export", "deployment_check"):
        exported = {
            "schema": "constructed.affine.v1",
            "slope": model["slope"],
            "bias": model["bias"],
        }
        if kind == "export":
            write_json(output / "model.json", exported)
        else:
            exported = read_json(Path("model.json"))
            if (
                set(exported) != {"schema", "slope", "bias"}
                or exported["schema"] != "constructed.affine.v1"
            ):
                raise LabError("unsupported constructed model export")
        require_finite("exported parameters", [exported["slope"], exported["bias"]])
        metrics["export_max_error"] = max(
            abs(
                predict(model, row["features"]["temperature"])
                - predict(exported, row["features"]["temperature"])
            )
            for row in rows
        )
        report["scope"] = "LOCAL_HOST_INFERENCE_ONLY"
    errors = [
        predict(model, row["features"]["temperature"]) - row["target"]["value"] for row in rows
    ]
    require_finite("validation errors", errors)
    metrics["validation_mse"] = sum(error * error for error in errors) / len(errors)
    write_json(output / f"{kind}.json", report)
    write_json(output / "metrics.json", metrics)


def run_demo(destination: Path) -> dict:
    # Reuse Forge's existing constructed release generator and point-in-time reader.
    from dataset_quickstart import prepare

    prepare(destination)
    destination = destination.resolve()
    pin = digest(destination / "dataset/manifest.json")
    runs = []
    checkpoint = exported = None
    for label, kind, method in (
        ("supervised", "train", "supervised"),
        ("fine-tuning", "train", "fine_tuning"),
        ("debug", "debug", None),
        ("profile", "profile", None),
        ("test", "test", None),
        ("export", "export", None),
        ("deployment-check", "deployment_check", None),
    ):
        recipe_root = destination / "recipes" / label
        recipe_root.mkdir(parents=True)
        shutil.copyfile(__file__, recipe_root / "model_task.py")
        shutil.copytree(destination / "dataset", recipe_root / "dataset")
        inputs = [
            "model_task.py",
            *[
                f"dataset/{name}"
                for name in ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")
            ],
        ]
        if checkpoint is not None:
            shutil.copyfile(checkpoint, recipe_root / "checkpoint.json")
            inputs.append("checkpoint.json")
        if kind == "deployment_check":
            shutil.copyfile(exported, recipe_root / "model.json")
            inputs.append("model.json")
        metrics = {"validation_mse": "min"}
        if kind == "debug":
            metrics["inspected_scalars"] = "max"
        if kind == "profile":
            metrics["profile_calls"] = "max"
        if kind in ("export", "deployment_check"):
            metrics["export_max_error"] = "min"
        checks = {"validation_mse": {"max": 0.1}}
        if "export_max_error" in metrics:
            checks["export_max_error"] = {"max": 1e-12}
        config = {
            "schema": "trainlab.experiment.v2",
            "name": f"Constructed {label}",
            "description": "Constructed local software acceptance; no scientific qualification.",
            "command": [sys.executable, "model_task.py", "--task", kind, "--pin", pin],
            "seed": 42,
            "timeout_seconds": 30,
            "source_kind": "CONSTRUCTED",
            "split_identity": pin,
            "inputs": inputs,
            "artifacts": [f"{kind}.json"]
            + (["checkpoint.json"] if kind == "train" else [])
            + (["model.json"] if kind == "export" else []),
            "metrics": metrics,
            "checks": checks,
            "budget": {"updates": 600 if kind == "train" else 0, "learned_parameters": 2},
            "workload": {"kind": kind, "training_method": method, "execution": "single_process"},
        }
        if method:
            config["command"] += ["--method", method]
        path = recipe_root / "recipe.json"
        write_json(path, config)
        record = run_experiment(path, destination / "runs")
        runs.append(record)
        directory = destination / "runs" / record["id"]
        if record["status"] != "succeeded" or not verify_run(directory)["valid"]:
            raise LabError(f"{label} failed; inspect retained run {record['id']}")
        if kind == "train":
            checkpoint = directory / "output/checkpoint.json"
        if kind == "export":
            exported = directory / "output/model.json"
    result = {
        "source": "CONSTRUCTED_ONLY",
        "run_ids": [run["id"] for run in runs],
        "workloads": [run["workload"] for run in runs],
        "manifest_sha256": pin,
        "qualification": "NOT_QUALIFIED",
        "deployment": "LOCAL_CHECK_ONLY",
    }
    write_json(destination / "workflow.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--task", choices=("train", "debug", "profile", "test", "export", "deployment_check")
    )
    parser.add_argument("--pin")
    parser.add_argument("--method", choices=("supervised", "fine_tuning"))
    args = parser.parse_args()
    if args.task:
        task(args.task, args.pin, args.method)
    elif args.output:
        print(json.dumps(run_demo(args.output), sort_keys=True))
    else:
        parser.error("--output is required")


if __name__ == "__main__":
    main()
