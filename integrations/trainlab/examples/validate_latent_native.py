"""Bounded original-checkpoint conformance through the actual manifest runner.

Inputs are constructed byte sequences. No corpus evaluation or training occurs.
Run only with an explicitly authorized local archive and trusted source code.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np
from trainlab.latent.artifacts import freeze, sha
from trainlab.latent.suite import reanalyze, run_plan
from trainlab.runner import digest, read_json, write_json


def run(archive, output):
    archive, output = Path(archive), Path(output)
    output.mkdir(parents=True, exist_ok=False)
    example = Path(__file__).with_name("latent_native_factory.py")
    records = []
    for architecture in ("csm", "transformer", "gated_delta_reference", "cog"):
        root = output / architecture
        root.mkdir()
        if architecture == "cog":
            source = archive / "latent_atlas/extracted/cog_model"
            files = {
                "model_source": source / "model.py",
                "native_source": source / "vendor/mamba2.py",
                "checkpoint": source / "model.pt",
            }
        else:
            source = archive / "latent_transfer_006/inputs"
            files = {
                "model_source": source / "model_source/models.py",
                "native_source": source / "model_source/native_csm.py",
                "checkpoint": source / "parent_checkpoints" / f"{architecture}_seed11.pt",
            }
        artifacts = {}
        for key, path in files.items():
            filename = f"{key}{path.suffix}"
            shutil.copyfile(path, root / filename)
            artifacts[key] = {"path": filename, "kind": "opaque", "sha256": digest(path)}
        shutil.copyfile(example, root / "adapter.py")
        tokens = np.array([list(b"aiA biB . , ai. "), list(b"aiB biA . , ai. ")], dtype=np.int64)
        if architecture == "cog":
            tokens = np.tile(tokens, (1, 2))
        targets = np.concatenate((tokens[:, 1:], np.full((len(tokens), 1), ord("."))), axis=1)
        np.savez(root / "synthetic.npz", input_ids=tokens, target_ids=targets)
        artifacts["synthetic"] = {"path": "synthetic.npz", "kind": "npz", "sha256": "0" * 64}
        x = {"artifact": "synthetic", "key": "input_ids"}
        jobs = [
            {
                "id": "parity",
                "operation": "interventions.native_parity",
                "kwargs": {"input_ids": x},
                "role": "control",
            },
            {
                "id": "latency",
                "operation": "interventions.latency_sweep",
                "kwargs": {"input_ids": x, "warmups": 2, "repeats": 5},
            },
        ]

        def observed(key):
            return {"result": "rows", "path": [key]}

        readout = {"capability": "readout", "context": {"context": observed("context")}}
        jobs.extend(
            [
                {"id": "capture", "operation": "native.forward", "args": [x]},
                {
                    "id": "rows",
                    "operation": "data.prepare_token_rows",
                    "args": [{"result": "capture"}, x],
                    "kwargs": {
                        "record_ids": ["constructed-a", "constructed-b"],
                        "domains": ["constructed", "constructed"],
                        "target_ids": {"artifact": "synthetic", "key": "target_ids"},
                    },
                },
                {
                    "id": "geometry",
                    "operation": "geometry.latent_geometry",
                    "args": [observed("hidden")],
                    "kwargs": {"dimensions": 3},
                },
                {
                    "id": "readout",
                    "operation": "calibration.native_readout_contrast",
                    "args": [observed("hidden"), {}, observed("target_ids"), readout],
                    "kwargs": {
                        "readout_kind": observed("readout_kind"),
                        "observed_native_scores": observed("logits"),
                    },
                },
                {
                    "id": "folds",
                    "operation": "data.source_record_folds",
                    "args": [observed("record_ids"), observed("domains")],
                },
                {
                    "id": "compression",
                    "operation": "geometry.compression_diagnostic",
                    "args": [observed("hidden"), observed("target_ids"), readout],
                    "kwargs": {
                        "folds": {"result": "folds", "path": ["folds"]},
                        "clusters": observed("record_ids"),
                        "domains": observed("domains"),
                        "ranks": [0, 2],
                        "random_seeds": [11],
                        "readout_kind": observed("readout_kind"),
                        "observed_native_scores": observed("logits"),
                    },
                },
            ]
        )
        if architecture == "csm":
            jobs.append(
                {
                    "id": "retrieval",
                    "operation": "interventions.retrieval_sweep",
                    "kwargs": {"input_ids": x, "anchor": 12, "horizon": 4, "donor_indices": [1, 0]},
                    "role": "control",
                }
            )
        plan = {
            "schema": "trainlab.latent-plan.v1",
            "title": f"{architecture} native implementation conformance",
            "identities": {
                "model": artifacts["checkpoint"]["sha256"],
                "dataset": sha(tokens.tolist()),
                "code": sha({k: v["sha256"] for k, v in artifacts.items() if k.endswith("source")}),
                "configuration": "0" * 64,
            },
            "artifacts": artifacts,
            "jobs": jobs,
            "figures": [
                {
                    "id": "head_geometry",
                    "kind": "scatter",
                    "title": f"{architecture}: constructed-input head geometry",
                    "data": {
                        "coordinates": {"result": "geometry", "path": [1, "coordinates"]},
                        "rows": observed("rows"),
                    },
                }
            ],
            "budget": {"max_calls": 500, "max_seconds": 90},
            "adapter": {
                "path": "adapter.py",
                "sha256": digest(example),
                "factory": "build_adapter",
            },
            "provenance": {
                "source_kind": "CONSTRUCTED_INPUTS_EXISTING_MODEL",
                "training_updates": 0,
                "native": {
                    "architecture": architecture,
                    "model_source": "model_source",
                    "native_source": "native_source",
                    "checkpoint": "checkpoint",
                    "cpu_threads": 1,
                },
            },
        }
        freeze(plan, root, root / "plan.json")
        result = run_plan(root / "plan.json", root / "evidence", allow_native=True)
        replay = reanalyze(
            root / "evidence", result["bundle_sha256"], root / "reanalysis", render_figures=False
        )
        record = {
            "architecture": architecture,
            "bundle_sha256": result["bundle_sha256"],
            "coverage": result["coverage"],
            "checkpoint_sha256": artifacts["checkpoint"]["sha256"],
            "reanalysis": replay,
        }
        for job in jobs:
            path = root / "evidence/results" / f"{job['id']}.json"
            record[job["id"]] = (
                read_json(path)["value"] if path.is_file() else {"status": "MISSING"}
            )
        records.append(record)
    result = {
        "schema": "trainlab.latent-native-acceptance.v1",
        "records": records,
        "training_updates": 0,
        "corpus_scoring": False,
        "passed": all(row["status"] == "TESTED" for rec in records for row in rec["coverage"])
        and all(rec["reanalysis"]["byte_exact"] for rec in records),
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(output / "validation.json", result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = run(args.archive_root, args.output)
    print(
        json.dumps(
            {
                "passed": result["passed"],
                "models": [
                    {"architecture": row["architecture"], "coverage": row["coverage"]}
                    for row in result["records"]
                ],
            },
            indent=2,
        )
    )
    return int(not result["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
