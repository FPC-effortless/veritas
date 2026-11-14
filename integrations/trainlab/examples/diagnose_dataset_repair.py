"""Replay a reviewed training-label repair and a fixed-model drift comparison."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import warnings
from pathlib import Path

from forge_data.quality_diagnostics import adjudicate
from qualify_diagnostics import LICENSE, version_info
from trainlab.dataset_repair import (
    classification_request,
    compare_drift_performance,
    compare_label_repair,
)
from trainlab.prediction_artifacts import write_predictions
from trainlab.runner import LabError, digest, write_json


def sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def evidence(root):
    from sklearn.datasets import load_wine
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import StandardScaler
    from threadpoolctl import threadpool_limits

    root.mkdir(parents=True, exist_ok=False)
    wine = load_wine()
    names = list(wine.feature_names)
    indexes = list(range(len(wine.data)))
    training, remainder = train_test_split(
        indexes, test_size=0.4, stratify=wine.target, random_state=415
    )
    original, recent = train_test_split(
        remainder, test_size=0.5, stratify=wine.target[remainder], random_state=416
    )
    split_boundary = 13.0
    code = digest(Path(__file__))
    config = {
        "seed": [415, 416],
        "scale": "training-only standard scaling",
        "fit": "logistic regression max_iter=400",
        "packages": version_info(),
        "slice": "alcohol >= 13",
        "drift": "held-out recent features scaled by 1.3 for alcohol",
    }
    config_pin = sha(config)

    def row(i, split):
        x = dict(zip(names, map(float, wine.data[i]), strict=True))
        x["slice"] = "high" if x["alcohol"] >= split_boundary else "low"
        return {"id": f"wine-{i:03}", "split": split, "features": x, "label": str(wine.target[i])}

    def make(rows):
        return {
            "schema": "forge.diagnostic-input.v1",
            "feature_fields": names + ["slice"],
            "group_fields": [],
            "rows": rows,
        }

    train_rows = [row(i, "train") for i in sorted(training)]
    reference = [row(i, "validation") for i in sorted(original)]
    current = [row(i, "validation") for i in sorted(recent)]
    clean = make(train_rows + reference)
    parent = copy.deepcopy(clean)
    reviews = []
    for r in parent["rows"]:
        if r["split"] == "train":
            original_class = r["label"]
            r["label"] = str((int(original_class) + 1) % 3)
            reviews.append(
                {
                    "id": r["id"],
                    "decision": "accept",
                    "old_label": r["label"],
                    "new_label": original_class,
                    "reviewer": "public-fixture-oracle",
                    "rationale": "Restore original label after deliberate class rotation.",
                }
            )
    parent_path = root / "faulted-view.json"
    write_json(parent_path, parent)
    parent_pin = digest(parent_path)
    write_json(root / "review-input.json", reviews)
    correction = adjudicate(parent_path, sha256=parent_pin, reviews=reviews)
    corrected = correction["observations"]["document"]
    if corrected != clean:
        raise LabError("review did not recover the original training labels")
    corrected_path = root / "corrected-view.json"
    write_json(corrected_path, corrected)
    corrected_pin = digest(corrected_path)
    for r in current:
        r["features"]["alcohol"] *= 1.3
    drift_view = make(train_rows + current)
    drift_path = root / "drift-view.json"
    write_json(drift_path, drift_view)
    drift_pin = digest(drift_path)
    write_json(
        root / "metadata.json",
        {**config, "dataset": LICENSE, "driver_sha256": code, "config_sha256": config_pin},
    )

    def matrix(rows):
        return [[r["features"][name] for name in names] for r in rows]

    def fit(view):
        rows = [r for r in view["rows"] if r["split"] == "train"]
        scaler = StandardScaler().fit(matrix(rows))
        predictor = LogisticRegression(max_iter=400)
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            predictor.fit(scaler.transform(matrix(rows)), [r["label"] for r in rows])
        model_pin = sha(
            [
                scaler.mean_.tolist(),
                scaler.scale_.tolist(),
                predictor.coef_.tolist(),
                predictor.intercept_.tolist(),
                predictor.classes_.tolist(),
            ]
        )
        return scaler, predictor, model_pin

    def predict(name, view, pin, fitted):
        scaler, predictor, model_pin = fitted
        ids = [r for r in view["rows"] if r["split"] == "validation"]
        results = predictor.predict(scaler.transform(matrix(ids))).tolist()
        req = classification_request(
            view,
            dataset_sha256=pin,
            model_sha256=model_pin,
            code_sha256=code,
            configuration_sha256=config_pin,
        )
        path = root / f"{name}-predictions.json"
        pin = write_predictions(
            path,
            req,
            [{"id": r["id"], "output": answer} for r, answer in zip(ids, results, strict=True)],
        )
        return {"path": path, "sha256": pin, "model_sha256": model_pin}, results

    with threadpool_limits(limits=1):
        baseline_fit, repaired_fit = fit(parent), fit(corrected)
        baseline, before = predict("baseline", parent, parent_pin, baseline_fit)
        repaired, after = predict("repaired", corrected, corrected_pin, repaired_fit)
        shifted, recent_results = predict("drift", drift_view, drift_pin, repaired_fit)
    repair = compare_label_repair(
        parent_path,
        corrected_path,
        parent_sha256=parent_pin,
        corrected_sha256=corrected_pin,
        reviews=reviews,
        baseline=baseline,
        repaired=repaired,
        code_sha256=code,
        configuration_sha256=config_pin,
        slice_field="slice",
    )
    drift = compare_drift_performance(
        corrected_path,
        drift_path,
        reference_sha256=corrected_pin,
        current_sha256=drift_pin,
        reference_predictions=repaired,
        current_predictions=shifted,
        fields={"alcohol": "numeric"},
        thresholds={"numeric": 0.2, "categorical": 0.2, "missingness": 0.05},
        code_sha256=code,
        configuration_sha256=config_pin,
        slice_field="slice",
    )
    recount = {
        "before_correct": sum(a == r["label"] for a, r in zip(before, reference, strict=True)),
        "after_correct": sum(a == r["label"] for a, r in zip(after, reference, strict=True)),
        "shifted_correct": sum(
            a == r["label"] for a, r in zip(recent_results, current, strict=True)
        ),
    }
    if any(repair["overall"][key] != recount[key] for key in ("before_correct", "after_correct")):
        raise LabError("independent label repair recount disagrees")
    shifted_count = sum(row["current"]["correct"] for row in drift["accuracy_by_slice"])
    if shifted_count != recount["shifted_correct"]:
        raise LabError("independent drift recount disagrees")
    write_json(root / "repair.json", repair)
    write_json(root / "drift.json", drift)
    write_json(root / "recount.json", recount)
    print(
        json.dumps(
            {
                "report": str(root),
                "training": len(train_rows),
                "reference": len(reference),
                "current": len(current),
                "repair": repair["status"],
                "drift": drift["status"],
                "recount": recount,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    evidence(args.root.resolve())
