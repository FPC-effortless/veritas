"""Dependency-free CONSTRUCTED regression diagnostic, never capability evidence."""
from __future__ import annotations

import argparse
import json
import os
import random
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("linear", "mean"), required=True)
    args = parser.parse_args()
    seed = int(os.environ["TRAINLAB_SEED"])
    rng = random.Random(seed)
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    data = json.loads(Path(__file__).with_name("constructed_regression.json").read_text())
    slope, bias = 0.0, 0.0
    for _ in range(200):
        row = rng.choice(data["train"])
        error = slope * row["x"] + bias - row["y"]
        if args.model == "linear":
            slope -= 0.04 * error * row["x"]
        bias -= 0.04 * error
    validation = [{"prediction": slope * row["x"] + bias, "target": row["y"]} for row in data["validation"]]
    errors = [row["prediction"] - row["target"] for row in validation]
    metrics = {
        "validation_mse": sum(error**2 for error in errors) / len(errors),
        "validation_mae": sum(abs(error) for error in errors) / len(errors),
        "train_mse": sum((slope * row["x"] + bias - row["y"])**2 for row in data["train"]) / len(data["train"]),
    }
    for name, value in {
        "metrics.json": metrics,
        "checkpoint.json": {"kind": "CONSTRUCTED_DIAGNOSTIC", "model": args.model, "seed": seed,
                            "slope": slope, "bias": bias, "updates": 200,
                            "learned_parameters": 2 if args.model == "linear" else 1,
                            "rng_state": rng.getstate()},
        "predictions.json": {"split": "CONSTRUCTED_VALIDATION", "rows": validation},
    }.items():
        (output / name).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"source": "CONSTRUCTED_ONLY", "model": args.model, "metrics": metrics}))


if __name__ == "__main__":
    main()
