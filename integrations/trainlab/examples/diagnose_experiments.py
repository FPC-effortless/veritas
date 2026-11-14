"""Bounded live linear training and declared fixture packs through the ecosystem."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

CUTOFF = "2026-11-14T00:00:00Z"
STEPS = list(range(1, 21))
THRESHOLDS = {
    "min_loss_drop": 0.5,
    "min_gradient_norm": 0,
    "min_update_norm": 0,
    "min_classes": 2,
    "acquired_score": 0.9,
    "max_regression": 0.05,
}


def view(source, manifest):
    from forge_data.dataset import Dataset

    dataset = Dataset(source / "dataset", manifest_sha256=manifest)
    return {
        split: [
            {"id": row["record_id"], "x": row["features"]["x"], "y": row["target"]["value"]}
            for row in dataset.examples(split, cutoff=CUTOFF, feature_fields=["x"])
        ]
        for split in ("train", "validation")
    }


def fit(data, frozen):
    """Actual full-batch scalar gradient descent; no research architecture fit."""
    weight = 0.1
    events = []
    for step in STEPS:
        train = data["train"]
        gradient = sum(2 * (weight * r["x"] - r["y"]) * r["x"] for r in train) / len(train)
        update = 0 if frozen else -0.5 * gradient
        weight += update
        loss = sum((weight * r["x"] - r["y"]) ** 2 for r in train) / len(train)
        validation = data["validation"]
        mse = sum((weight * r["x"] - r["y"]) ** 2 for r in validation) / len(validation)
        events.append(
            {
                "step": step,
                "loss": loss,
                "finite": True,
                "gradient_norm": abs(gradient),
                "update_norm": abs(update),
                "missing_gradients": 0,
                "learning_rate": 0.5,
                "predicted_classes": len({int(weight * r["x"] >= 0) for r in validation}),
                "validation_score": 1 / (1 + mse),
            }
        )
    return {
        "weight": weight,
        "events": events,
        "attempted_updates": len(STEPS),
        "nonzero_updates": 0 if frozen else len(STEPS),
    }


def fixtures():
    """These are synthetic API inputs, not measured scientific comparisons."""
    return {
        "benchmark": [
            {
                "id": str(i),
                "group": str(i),
                "original": 0,
                "intervened": 1,
                "reference_original": 0,
                "reference_intervened": 1,
                "expect_change": True,
                "deficient_original": 0,
                "deficient_intervened": 0,
            }
            for i in range(3)
        ],
        "ledger": [
            {
                "id": name,
                "attributes": {"data": "constructed", "route_labels": False},
                "seeds": [{"seed": s, "status": "succeeded"} for s in [1, 2]],
                "competence": {"status": "unknown", "evidence_sha256": None},
                "selection": {"split": "validation", "trials": 1, "rule": "fixed"},
            }
            for name in ("candidate", "baseline")
        ],
        "paired": [
            {"unit": str(i), "seed": s, "candidate": 0.6 + i / 10, "baseline": 0.5}
            for i in range(3)
            for s in [1, 2]
        ],
        "classification": [
            {"id": "a", "label": "yes", "prediction": "yes", "probabilities": [0.2, 0.8]},
            {"id": "b", "label": "no", "prediction": "yes", "probabilities": [0.3, 0.7]},
        ],
        "quality_cost": [
            {
                "id": name,
                "quality": quality,
                "session_seconds": None,
                "cost_status": "NOT_MEASURED",
                "workload_sha256": "a" * 64,
                "hardware_sha256": "b" * 64,
                "boundary_sha256": "c" * 64,
            }
            for name, quality in [("a", 0.8), ("b", 0.9)]
        ],
    }


def worker():
    from forge_data.core import canonical
    from research_lab.ecosystem import _runtime, _sha
    from trainlab.experiment_diagnostics import (
        benchmark_diagnostics,
        classification_diagnostics,
        comparison_ledger,
        paired_statistics,
        quality_cost,
        training_diagnostics,
    )
    from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
    from trainlab.runner import LabError, digest, read_json, write_json

    source = Path.cwd()
    protocol = read_json(source / "protocol.json")
    if protocol["runtime"] != _runtime():
        raise LabError("frozen runtime changed")
    data = view(source, protocol["manifest_sha256"])
    if canonical(data) != canonical(read_json(source / "view.json")):
        raise LabError("selected training view changed")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    synthetic = read_json(source / "fixtures.json")
    training, reports = {}, {}

    def train():
        training.update(fit(data, protocol["case"] == "frozen"))
        write_json(output / "training.json", training)

    def inspect():
        reports.update(
            {
                "training": training_diagnostics(
                    training["events"], expected_steps=STEPS, thresholds=THRESHOLDS
                ),
                "benchmark": benchmark_diagnostics(synthetic["benchmark"]),
                "ledger": comparison_ledger(
                    synthetic["ledger"],
                    required_seeds=[1, 2],
                    matched_fields=["data", "route_labels"],
                ),
                "paired": paired_statistics(
                    synthetic["paired"],
                    required_units=["0", "1", "2"],
                    required_seeds=[1, 2],
                    draws=200,
                ),
                "classification": classification_diagnostics(
                    synthetic["classification"], classes=["no", "yes"], bins=2
                ),
                "quality_cost": quality_cost(synthetic["quality_cost"]),
            }
        )

    def persist():
        write_json(
            output / "pack-reports.json",
            {
                "reports": reports,
                "live_observations": ["training"],
                "constructed_fixture_packs": sorted(set(reports) - {"training"}),
                "scientific_qualification": "NOT_QUALIFIED",
            },
        )

    def execution(ctx):
        ctx.invoke("train", phase="update")
        ctx.invoke("inspect", phase="verify")
        ctx.invoke("persist", phase="persist")
        return {
            "status": "TESTED",
            "summary": "Packs executed; inspect per-check findings.",
            "metrics": {"packs": len(reports), "nonzero_updates": training["nonzero_updates"]},
        }

    adapter = Adapter(
        "linear-training",
        {"train": train, "inspect": inspect, "persist": persist},
        {
            "persists": "local scalar weight",
            "query_mutates": False,
            "reset": "fresh worker starts weight at 0.1",
        },
    )
    identities = {
        "model": _sha({"model": "scalar-linear", "initial_weight": 0.1}),
        "dataset": digest(source / "view.json"),
        "code": digest(source / "driver.py"),
        "configuration": _sha(
            {"protocol": digest(source / "protocol.json"), "recipe": digest(source / "recipe.json")}
        ),
    }
    Workbench(
        adapter,
        identities,
        output / "diagnostics",
        max_calls=3,
        max_seconds=30,
        required_phases=("update", "verify", "persist"),
    ).run(
        [
            Diagnostic(
                "pack_execution",
                "1",
                ("train", "inspect", "persist"),
                execution,
                "CPU engineering control plus declared fixtures; not research training",
            )
        ]
    )
    if protocol["runtime"] != _runtime() or len(reports) != 6:
        raise LabError("runtime changed or diagnostic execution incomplete")
    write_json(
        output / "metrics.json", {"packs": len(reports), "loss": training["events"][-1]["loss"]}
    )


def prepare(source, case):
    from forge_data.core import canonical, release
    from research_lab.ecosystem import _runtime
    from trainlab.runner import digest, write_json

    source.mkdir(parents=True)
    shutil.copyfile(__file__, source / "driver.py")
    rows = [
        {
            "episode_id": f"episode-{i}",
            "subject_id": f"subject-{i}",
            "record_id": f"record-{i}",
            "observed_at": CUTOFF,
            "available_at": CUTOFF,
            "observation": {"x": (i - 63.5) / 64},
            "action": None,
            "outcome": {
                "status": "observed",
                "verified": True,
                "available_at": CUTOFF,
                "value": (i - 63.5) / 32,
            },
        }
        for i in range(128)
    ]
    (source / "rows.jsonl").write_bytes(b"".join(canonical(r) for r in rows))
    write_json(
        source / "source.json",
        {
            "dataset_id": "linear-diagnostic-controls",
            "source_id": "constructed/linear-training",
            "source_version": "1",
            "adapter": "operations-jsonl",
            "license_id": "Apache-2.0",
            "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/526",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": "linear-diagnostic-controls",
        },
    )
    release(source / "rows.jsonl", source / "source.json", source / "dataset")
    manifest = digest(source / "dataset/manifest.json")
    write_json(source / "view.json", view(source, manifest))
    write_json(source / "fixtures.json", fixtures())
    write_json(
        source / "protocol.json",
        {
            "schema": "veritas.experiment-diagnostic-example.v1",
            "case": case,
            "manifest_sha256": manifest,
            "runtime": _runtime(),
            "training_scope": "20 scalar full-batch update attempts; fixed public validation panel",
            "comparison_scope": "constructed fixtures only; costs not measured",
        },
    )
    write_json(
        source / "recipe.json",
        {
            "schema": "trainlab.experiment.v2",
            "name": "experiment-" + case,
            "description": "CPU scalar training control and constructed diagnostic fixtures",
            "command": [sys.executable, "driver.py", "--worker"],
            "seed": 1,
            "timeout_seconds": 60,
            "source_kind": "CONSTRUCTED",
            "split_identity": manifest,
            "inputs": [
                "driver.py",
                "protocol.json",
                "view.json",
                "fixtures.json",
                "dataset/manifest.json",
                "dataset/train.jsonl",
                "dataset/validation.jsonl",
                "dataset/test.jsonl",
            ],
            "artifacts": ["training.json", "pack-reports.json", "diagnostics/report.json"],
            "metrics": {"packs": "max", "loss": "min"},
            "budget": {"model_fits": 1},
            "workload": {
                "kind": "train",
                "training_method": "supervised",
                "execution": "single_process",
            },
            "checks": {},
        },
    )
    return manifest


def run(root):
    from research_lab.adapters import import_forge, import_trainlab
    from research_lab.core import Controller
    from research_lab.ecosystem import _sha
    from research_lab.evidence import link, put_node
    from trainlab.runner import LabError, digest, read_json, run_experiment, verify_run, write_json

    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    lab = Controller(root / "research_lab")
    results = []
    for case in ("clean", "frozen"):
        source = root / "sources" / case
        manifest = prepare(source, case)
        import_forge(lab, source / "dataset", manifest)
        receipt = run_experiment(source / "recipe.json", root / "runs")
        directory = root / "runs" / receipt["id"]
        if receipt["status"] != "succeeded" or not verify_run(directory)["valid"]:
            raise LabError("diagnostic execution failed; retain run for inspection")
        import_trainlab(lab, directory)
        path = directory / "output/pack-reports.json"
        report = read_json(path)
        node = "experiment-diagnosis." + _sha(report)[:24]
        put_node(lab, node, "finding", {"report": report, "artifact_sha256": digest(path)})
        link(lab, node, "derived_from", "trainlab." + receipt["id"])
        link(lab, node, "derived_from", "forge." + manifest[:24])
        results.append(
            {
                "case": case,
                "run_id": receipt["id"],
                "training": report["reports"]["training"]["coverage"],
                "loss": read_json(directory / "output/training.json")["events"][-1]["loss"],
            }
        )
    write_json(
        root / "summary.json",
        {
            "runs": results,
            "model_fit_attempts": 2,
            "research_model_fits": 0,
            "scientific_qualification": "NOT_QUALIFIED",
        },
    )
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if args.worker:
        worker()
    elif args.root:
        run(args.root.resolve())
    else:
        parser.error("new --root required")
