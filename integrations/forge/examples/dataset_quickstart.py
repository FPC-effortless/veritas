"""Constructed Forge -> TrainLab -> dashboard workflow, never scientific evidence.

Run with PYTHONPATH containing both sibling packages, or install them first.
The --fit path is tiny trusted example code, not a general trainer.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from forge_data.core import ForgeError, canonical, hash_bytes, release
from forge_data.dataset import Dataset

FEATURE_CUTOFF = "2026-01-01T10:00:01Z"
TARGET_CUTOFF = "2026-01-02T10:00:00Z"


def fit(method: str, pin: str) -> None:
    dataset = Dataset(Path("dataset"), manifest_sha256=pin)
    train = dataset.examples(
        "train", cutoff=FEATURE_CUTOFF, target_cutoff=TARGET_CUTOFF, feature_fields=["temperature"]
    )
    validation = dataset.examples(
        "validation",
        cutoff=FEATURE_CUTOFF,
        target_cutoff=TARGET_CUTOFF,
        feature_fields=["temperature"],
    )
    transform = (lambda x: x) if method == "linear" else (lambda x: x * x)
    xs = [transform(row["features"]["temperature"]) for row in train]
    ys = [row["target"]["value"] for row in train]
    mean_x, mean_y = sum(xs) / len(xs), sum(ys) / len(ys)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / sum(
        (x - mean_x) ** 2 for x in xs
    )
    intercept = mean_y - slope * mean_x
    mse = sum(
        (slope * transform(row["features"]["temperature"]) + intercept - row["target"]["value"])
        ** 2
        for row in validation
    ) / len(validation)
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    (output / "metrics.json").write_bytes(canonical({"validation_mse": mse}))
    (output / "model.json").write_bytes(
        canonical(
            {
                "method": method,
                "slope": slope,
                "intercept": intercept,
                "source": "CONSTRUCTED_ONLY",
                "manifest_sha256": pin,
                "feature_cutoff": FEATURE_CUTOFF,
                "target_cutoff": TARGET_CUTOFF,
                "qualification": "NOT_QUALIFIED",
            }
        )
    )
    print("CONSTRUCTED_ONLY: no authentic source or capability qualification")


def prepare(output: Path, *, run: bool = False) -> dict:
    """Publish an entirely constructed local demo directory, refusing overwrite."""
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ForgeError("demo output already exists")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".forge-demo-", dir=output.parent))
    try:
        spec = {
            "dataset_id": "constructed-forge-trainlab",
            "source_id": "fixture/operations",
            "source_version": "constructed-v1",
            "adapter": "operations-jsonl",
            "license_id": "fixture-only",
            "provenance_uri": "https://example.invalid/fixture",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": "constructed-frozen-v1",
        }
        rows = [
            {
                "episode_id": f"episode-{i}",
                "subject_id": f"machine-{i}",
                "record_id": f"record-{i}",
                "observed_at": "2026-01-01T10:00:00Z",
                "available_at": FEATURE_CUTOFF,
                "observation": {"temperature": i},
                "action": None,
                "outcome": {
                    "status": "constructed",
                    "verified": False,
                    "available_at": TARGET_CUTOFF,
                    "value": 2 * i + 1,
                },
            }
            for i in range(1, 31)
        ]
        (stage / "source.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
        (stage / "source-spec.json").write_bytes(canonical(spec))
        release(stage / "source.jsonl", stage / "source-spec.json", stage / "dataset")
        pin = hash_bytes((stage / "dataset/manifest.json").read_bytes())
        summary = Dataset(stage / "dataset", manifest_sha256=pin).summary()
        shutil.copyfile(__file__, stage / "experiment.py")
        for method in ("linear", "quadratic"):
            config = {
                "schema": "trainlab.experiment.v1",
                "name": f"Forge {method} constructed demo",
                "description": "Constructed data only; no scientific or protected TEST evidence.",
                "command": [sys.executable, "experiment.py", "--fit", method, "--pin", pin],
                "seed": 42,
                "timeout_seconds": 30,
                "source_kind": "CONSTRUCTED",
                "split_identity": pin,
                "inputs": [
                    "experiment.py",
                    "dataset/manifest.json",
                    "dataset/train.jsonl",
                    "dataset/validation.jsonl",
                    "dataset/test.jsonl",
                ],
                "artifacts": ["model.json"],
                "metrics": {"validation_mse": "min"},
                "budget": {"learned_parameters": 2, "fit_passes": 1, "train_examples": 24},
            }
            (stage / f"{method}.json").write_bytes(canonical(config))
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    result = {"demo": "CONSTRUCTED_ONLY", "dataset": summary, "qualification": "NOT_QUALIFIED"}
    if run:
        from trainlab.runner import compare_runs, run_experiment, verify_run

        runs = [
            run_experiment(output / f"{method}.json", output / "runs")
            for method in ("linear", "quadratic")
        ]
        if any(record["status"] != "succeeded" for record in runs):
            raise ForgeError("demo experiment failed; inspect retained TrainLab logs")
        if not all(verify_run(output / "runs" / record["id"])["valid"] for record in runs):
            raise ForgeError("demo run file verification failed")
        comparison = compare_runs(runs)
        (output / "comparison.json").write_bytes(canonical(comparison))
        result.update(
            run_ids=[record["id"] for record in runs],
            matched_declared_conditions=comparison["matched_declared_conditions"],
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--fit", choices=("linear", "quadratic"))
    parser.add_argument("--pin")
    args = parser.parse_args()
    try:
        if args.fit:
            fit(args.fit, args.pin)
        elif args.output is not None:
            print(json.dumps(prepare(args.output, run=args.run), sort_keys=True))
        else:
            parser.error("--output is required")
    except (ForgeError, OSError, ValueError) as exc:
        parser.exit(2, f"forge demo: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
