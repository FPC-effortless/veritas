"""Constructed, zero-fit latent suite acceptance; no research qualification."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from trainlab.latent.artifacts import freeze, sha
from trainlab.latent.suite import reanalyze, run_plan
from trainlab.runner import digest, read_json, write_json


def prepare(root, *, ecosystem=False):
    root.mkdir(parents=True, exist_ok=False)
    rng = np.random.default_rng(71)
    latent = rng.normal(size=(80, 3))
    vectors = latent @ rng.normal(size=(3, 8)) + 0.02 * rng.normal(size=(80, 8))
    targets = np.arange(80) % 4
    logits = rng.normal(size=(80, 4))
    logits[np.arange(80), targets] += 2
    baseline = rng.normal(size=20)
    treatment = baseline + rng.normal(0.2, 0.15, size=20)
    forge = None
    if ecosystem:
        from forge_data.core import canonical, release
        from forge_data.dataset import Dataset

        cutoff = "2026-01-01T00:00:00Z"
        source_rows = [
            {
                "episode_id": f"episode-{i}",
                "subject_id": f"unit-{i}",
                "record_id": f"row-{i}",
                "observed_at": cutoff,
                "available_at": cutoff,
                "observation": {"vector": vectors[i].tolist(), "logits": logits[i].tolist()},
                "action": None,
                "outcome": {
                    "status": "constructed",
                    "verified": False,
                    "available_at": cutoff,
                    "value": int(targets[i]),
                },
            }
            for i in range(len(vectors))
        ]
        source_spec = {
            "dataset_id": "latent-constructed-acceptance",
            "source_id": "fixture/latent",
            "source_version": "constructed-v1",
            "adapter": "operations-jsonl",
            "license_id": "fixture-only",
            "provenance_uri": "https://example.invalid/latent",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": "latent-constructed-v1",
        }
        (root / "source.jsonl").write_bytes(b"".join(canonical(row) for row in source_rows))
        write_json(root / "source-spec.json", source_spec)
        release(root / "source.jsonl", root / "source-spec.json", root / "dataset")
        pin = digest(root / "dataset/manifest.json")
        dataset = Dataset(root / "dataset", manifest_sha256=pin)
        rows = [
            row
            for split in ("train", "validation")
            for row in dataset.examples(
                split, cutoff=cutoff, target_cutoff=cutoff, feature_fields=["vector", "logits"]
            )
        ]
        vectors = np.asarray([row["features"]["vector"] for row in rows])
        logits = np.asarray([row["features"]["logits"] for row in rows])
        targets = np.asarray([row["target"]["value"] for row in rows])
        forge = {
            "manifest_sha256": pin,
            "selected_splits": ["train", "validation"],
            "selected_rows": len(rows),
            "cutoff": cutoff,
            "view_sha256": sha(rows),
        }
    np.savez(
        root / "observations.npz",
        vectors=vectors,
        logits=logits,
        targets=targets,
        baseline=baseline,
        treatment=treatment,
    )

    def artifact(key):
        return {"artifact": "observed", "key": key}

    def result(name, *path):
        return {"result": name, "path": list(path)}

    jobs = [
        {
            "id": "atlas",
            "operation": "geometry.latent_geometry",
            "args": [artifact("vectors")],
            "role": "secondary",
            "scope": "constructed vectors; projection fidelity only",
        },
        {
            "id": "score",
            "operation": "scoring.classification_metrics",
            "args": [artifact("logits"), artifact("targets")],
        },
        {
            "id": "calibration",
            "operation": "scoring.calibration",
            "args": [result("score", "max_probability"), result("score", "native_correct")],
        },
        {
            "id": "effect",
            "operation": "analysis.paired_estimate",
            "args": [artifact("treatment"), artifact("baseline"), list(range(20))],
            "kwargs": {"draws": 200, "seed": 11},
            "role": "primary",
            "unit": "constructed score",
            "scope": "paired source-unit bootstrap conditional on this fixed constructed model",
        },
        {
            "id": "identity_effect",
            "operation": "analysis.paired_estimate",
            "args": [artifact("baseline"), artifact("baseline"), list(range(20))],
            "kwargs": {"draws": 200, "seed": 11, "indices": result("effect", "indices")},
            "role": "control",
        },
        {
            "id": "model_replay",
            "operation": "interventions.native_parity",
            "kwargs": {"input_ids": [[1, 2]]},
            "role": "control",
            "scope": "Missing native hooks must remain UNSUPPORTED",
        },
    ]
    plan = {
        "schema": "trainlab.latent-plan.v1",
        "title": "Veritas latent diagnostics - constructed acceptance",
        "identities": {
            "model": sha("constructed logits"),
            "dataset": sha("seed71 fixture"),
            "code": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "configuration": "0" * 64,
        },
        "artifacts": {"observed": {"path": "observations.npz", "sha256": "0" * 64, "kind": "npz"}},
        "jobs": jobs,
        "budget": {"max_calls": 20, "max_seconds": 30},
        "provenance": {"source_kind": "CONSTRUCTED", "training_updates": 0},
        "figures": [
            {
                "id": "projection",
                "kind": "scatter",
                "title": "Observed latent geometry",
                "xlabel": "Principal component 1",
                "ylabel": "Principal component 2",
                "data": {
                    "coordinates": result("atlas", 1, "coordinates"),
                    "groups": artifact("targets"),
                },
                "metadata": {"scope": "constructed data; independently fitted PCA axes"},
            },
            {
                "id": "spectrum",
                "kind": "spectrum",
                "title": "Explained variance spectrum",
                "xlabel": "Principal component",
                "ylabel": "Fraction of centered variance",
                "data": {"y": result("atlas", 1, "explained_variance_ratio")},
            },
        ],
    }
    if forge is not None:
        plan["provenance"]["forge"] = forge
        plan["identities"]["dataset"] = sha(forge)
        for index, path in enumerate(sorted((root / "dataset").glob("*"))):
            if path.is_file():
                plan["artifacts"][f"forge-{index}"] = {
                    "path": path.relative_to(root).as_posix(),
                    "kind": "opaque",
                    "sha256": digest(path),
                }
    freeze(plan, root, root / "plan.json")
    return root / "plan.json"


def recipe(plan_path, destination):
    """Compose with the existing runner and research-lab import-trainlab path."""
    config = {
        "schema": "trainlab.experiment.v2",
        "name": "latent-constructed-acceptance",
        "description": (
            "Zero-fit latent diagnostics with verified evidence; constructed inputs only."
        ),
        "execution_purpose": "engineering_diagnostic",
        "command": [sys.executable, "-m", "trainlab.latent", "worker", plan_path.name],
        "seed": 71,
        "timeout_seconds": 60,
        "source_kind": "CONSTRUCTED",
        "split_identity": "constructed-engineering-panel-not-sealed-TEST",
        "inputs": [plan_path.name]
        + [item["path"] for item in read_json(plan_path)["artifacts"].values()],
        "artifacts": ["latent-evidence.zip", "latent-receipt.json"],
        "metrics": {
            f"diagnostics_{status}": "min" if status != "tested" else "max"
            for status in ("tested", "failed", "inconclusive", "unsupported", "not_run")
        },
        "checks": {
            "diagnostics_tested": {"min": 5},
            "diagnostics_inconclusive": {"max": 0},
            "diagnostics_not_run": {"max": 0},
        },
        "budget": {"training_updates": 0, "cpu_slots": 1},
        "workload": {"kind": "test", "training_method": None, "execution": "single_process"},
    }
    write_json(destination, config)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--through-runner", action="store_true")
    parser.add_argument(
        "--ecosystem",
        action="store_true",
        help="Validate Forge data and index the TrainLab receipt in Research Lab",
    )
    args = parser.parse_args()
    plan = prepare(args.root / "inputs", ecosystem=args.ecosystem)
    if args.through_runner or args.ecosystem:
        from trainlab.runner import run_experiment

        config = recipe(plan, plan.parent / "recipe.json")
        result = run_experiment(config, args.root / "runs")
        if args.ecosystem and result["status"] == "succeeded":
            from research_lab.adapters import import_forge, import_trainlab
            from research_lab.core import Controller

            lab = Controller(args.root / "lab")
            manifest = read_json(plan)["provenance"]["forge"]["manifest_sha256"]
            linked = {
                "forge_evidence": import_forge(lab, plan.parent / "dataset", manifest),
                "trainlab_evidence": import_trainlab(lab, args.root / "runs" / result["id"]),
            }
            write_json(args.root / "ecosystem-evidence.json", linked)
            result["research_lab_evidence"] = linked
        print(json.dumps(result, indent=2))
        return int(result["status"] != "succeeded")
    result = run_plan(plan, args.root / "evidence")
    replay = reanalyze(args.root / "evidence", result["bundle_sha256"], args.root / "reanalysis")
    write_json(args.root / "acceptance.json", {"run": result, "reanalysis": replay})
    print(
        json.dumps(
            {
                "bundle_sha256": result["bundle_sha256"],
                "coverage": result["coverage"],
                "byte_exact": replay["byte_exact"],
                "model_forwards": replay["model_forwards"],
            },
            indent=2,
        )
    )
    return int(not replay["byte_exact"])


if __name__ == "__main__":
    raise SystemExit(main())
