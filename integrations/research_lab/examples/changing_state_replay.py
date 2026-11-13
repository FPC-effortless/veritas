"""Replay admitted public CSM/slot checkpoints through the four-component ecosystem.

No fitting, protected TEST selection, or scientific promotion. Commands are trusted
local code. Exact model bytes are read from the operator's recovered source package.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import sys
import time
import zipfile
from pathlib import Path

from forge_data.core import canonical, release
from forge_data.dataset import Dataset
from trainlab.runner import contained_file, digest, read_json, write_json

ARCHIVE_SHA = "e4a3d3e39e6e8aa3e6f4f3c6c76b705dacf310be4adb8fc82f068712e678b9f2"
MANIFEST_SHA = "5efb16d2e1aea360dc453d5fc00b152c1cb270eec47b15639d32d43b3da7d74a"
CUTOFF = "2026-11-13T00:00:00Z"
SEEDS = (101, 202, 303)
TOKENS = ("<pad>", "<bos>", "set", ";", "ask", "?", "<nop>") + tuple(
    f"r{i}" for i in range(4)
) + tuple(f"v{i}" for i in range(8))
VOCAB = {token: i for i, token in enumerate(TOKENS)}


def encode(memory, query):
    """Inference-only encoder: no labels, physical destinations or gain targets."""
    if set(memory) != {"keys", "events"} or memory["keys"] != [f"r{i}" for i in range(4)]:
        raise ValueError("the frozen models support exactly four declared identities")
    if query not in memory["keys"]:
        raise ValueError("unsupported query")
    tokens = [VOCAB["<bos>"]]
    for event in memory["events"]:
        if (
            set(event) != {"op", "key", "value"} or event["op"] != "set"
            or event["key"] not in memory["keys"]
            or event["value"] not in [f"v{i}" for i in range(8)]
        ):
            raise ValueError("untrained operation, identity or value")
        tokens.extend(VOCAB[t] for t in ("set", event["key"], event["value"], ";"))
    return tokens + [VOCAB["<nop>"]] * 4 + [VOCAB["ask"], VOCAB[query], VOCAB["?"]]


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def prepare_source(package, destination):
    """Verify the recovered package, then create ordinary local TrainLab recipes."""
    package = package.resolve()
    manifest = read_json(contained_file(package, "MANIFEST.json"))
    for item in manifest["files"]:
        if digest(contained_file(package, item["path"])) != item["sha256"]:
            raise ValueError("recovered package hash mismatch")
    archive_path = contained_file(package, "CSM-Research-Update-20261109.zip")
    if digest(archive_path) != ARCHIVE_SHA:
        raise ValueError("wrong original CSM archive")
    if digest(package / "MANIFEST.json") != MANIFEST_SHA:
        raise ValueError("wrong recovered package manifest")
    stress = package / "research/changing_state_001"
    slot = package / "research/slot_control_001"
    frozen = read_json(stress / "freeze.json")
    slot_freeze = read_json(slot / "freeze.json")
    for filename, expected in slot_freeze["files"].items():
        if digest(contained_file(slot, filename)) != expected:
            raise ValueError("historical control source changed")
    closure = read_json(slot / "training_closed.json")
    if (
        closure["all_three_closed_before_stress_scoring"] is not True
        or [r["seed"] for r in closure["runs"]] != list(SEEDS)
    ):
        raise ValueError("historical training closure incomplete")
    if destination.exists():
        raise ValueError("source destination must be new")
    destination.mkdir(parents=True)
    provenance = {"original_archive_sha256": ARCHIVE_SHA, "checkpoints": {}}
    with zipfile.ZipFile(archive_path) as archive:
        reference = archive.read("experiments/csm_foundation_001/model.py")
        expected = frozen["dependencies"]["experiments/csm_foundation_001/model.py"]
        if hashlib.sha256(reference).hexdigest() != expected:
            raise ValueError("reference model source changed")
        (destination / "native_csm.py").write_bytes(reference)
        for receipt in closure["runs"]:
            seed = receipt["seed"]
            directory = slot / "runs" / str(seed)
            prefix = f"experiments/csm_address_002/runs/supervised_{seed}/"
            historical = json.loads(archive.read(prefix + "complete.json"))
            if (
                receipt != read_json(directory / "complete.json")
                or receipt["updates"] != 256 or receipt["answer_exposures"] != 8192
                or receipt["freeze_sha256"] != digest(slot / "freeze.json")
                or receipt["schedule_sha256"] != historical["schedule_sha256"]
                or receipt["training_log_sha256"] != digest(directory / "updates.jsonl")
            ):
                raise ValueError("historical control closure differs")
            steps = [json.loads(line)["step"] for line in
                     (directory / "updates.jsonl").read_text().splitlines()]
            if steps != list(range(1, 257)):
                raise ValueError("historical training steps incomplete")
            for arm, blob, expected in (
                ("csm", archive.read(prefix + "checkpoint.pt"),
                 frozen["checkpoints"][f"supervised_{seed}"]),
                ("slot", (directory / "checkpoint.pt").read_bytes(),
                 receipt["checkpoint_sha256"]),
            ):
                if hashlib.sha256(blob).hexdigest() != expected:
                    raise ValueError("checkpoint changed")
                filename = f"{arm}_{seed}.pt"
                (destination / filename).write_bytes(blob)
                provenance["checkpoints"][filename] = expected
    shutil.copyfile(slot / "model.py", destination / "native_slot.py")
    shutil.copyfile(__file__, destination / "driver.py")
    worlds = read_json(stress / "worlds.json", limit=4 * 1024 * 1024)
    if len(worlds) != 640 or {w["block"] for w in worlds} != set(range(8)):
        raise ValueError("unexpected frozen world panel")
    # Preserve the existing encoder as a byte-pinned, pre-execution parity control.
    original = load_module(stress / "stress_data.py", "historical_stress_encoder")
    rows = []
    for world in worlds:
        memory = {
            "keys": [f"r{i}" for i in range(4)],
            "events": [{"op": "set", "key": f"r{k}", "value": f"v{v}"}
                       for k, v in world["writes"]],
        }
        for q in range(4):
            if encode(memory, f"r{q}") != original.encode(world, q)["input_ids"]:
                raise ValueError("native encoder parity failed")
        identity = f"{world['family']}-{world['regime']}-{world['updates']}"
        rows.append({
            "episode_id": identity, "subject_id": f"base-{world['block']}",
            "record_id": identity, "observed_at": CUTOFF, "available_at": CUTOFF,
            "observation": {"memory": memory}, "action": None,
            "outcome": {"status": "unknown", "verified": False},
        })
    spec = {
        "dataset_id": "changing-state-001-dev-replay", "source_id": "public/cs001",
        "source_version": digest(stress / "worlds.json"), "adapter": "operations-jsonl",
        "license_id": "OPERATOR_AUTHORIZED_RESEARCH_REPLAY",
        "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/512",
        "ai_use_allowed": True, "redistribution_allowed": True, "privacy_reviewed": True,
        "split_salt": "ecosystem-native-replay-001",
    }
    write_json(destination / "source.json", spec)
    (destination / "source.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    release(destination / "source.jsonl", destination / "source.json", destination / "dataset")
    provenance.update(
        worlds_sha256=digest(stress / "worlds.json"),
        recovered_manifest_sha256=digest(package / "MANIFEST.json"),
        training_closure_sha256=digest(slot / "training_closed.json"),
        encoder_parity_queries=2560,
        model_sources={name: digest(destination / name)
                       for name in ("native_csm.py", "native_slot.py")},
        disclosure="Previously exposed public DEV; Forge split is archival bookkeeping.",
    )
    write_json(destination / "lineage.json", provenance)
    (destination / "design.md").write_text(
        "# ECOSYSTEM-MEM-002 frozen native replay\n\n"
        "Two learned arms, seeds101/202/303, no fits. Eight correlated base-pattern groups; "
        "all 640 old public DEV worlds released through Forge; only its validation group "
        "scored. Four fresh queries per full map. One CPU thread, FP32; one untimed warmup "
        "per length and one measured complete-map call per world. Encoding, tensor creation, "
        "state initialization, token steps, argmax, map assembly and JSON serialization timed. "
        "Imports/loading excluded. No concurrency, retries, tuning or new generalization claim. "
        "Unchanged native checkpoint hashes in lineage.json. Matching historical training "
        "schedule hashes does not independently establish all training chronology. "
        "No deletion/COPY/LINK capability or inference-cost qualification.\n"
    )
    slots = []
    for index, seed in enumerate(SEEDS):
        for arm in (("csm", "slot") if index % 2 == 0 else ("slot", "csm")):
            identity = f"{arm}-{seed}"
            recipe = {
                "schema": "trainlab.experiment.v2", "name": identity,
                "description": "Frozen learned model replay; no new model fit",
                "command": [sys.executable, "driver.py", "evaluate", arm, str(seed)],
                "seed": seed, "timeout_seconds": 180, "source_kind": "CONSTRUCTED",
                "split_identity": digest(destination / "dataset/manifest.json"),
                "inputs": ["driver.py", f"native_{arm}.py", f"{arm}_{seed}.pt",
                           "design.md", "lineage.json"] + [
                    "dataset/" + f for f in
                    ("manifest.json", "train.jsonl", "validation.jsonl", "test.jsonl")
                ],
                "artifacts": ["memory_predictions.json", "timing.json"],
                "metrics": {"requests": "max", "measured_seconds": "min"},
                "budget": {"model_fits": 0, "cpu_threads": 1},
                "workload": {"kind": "test", "training_method": None,
                             "execution": "single_process"}, "checks": {},
            }
            write_json(destination / (identity + ".json"), recipe)
            slots.append({"id": identity, "arm": arm, "seed": seed,
                          "recipe": identity + ".json"})
    write_json(destination / "campaign.json", {
        "schema": "veritas.memory-campaign.v1", "dataset": "dataset",
        "split": "validation", "cutoff": CUTOFF, "design": "design.md", "slots": slots,
    })
    return provenance


def evaluate(arm, seed):
    import numpy as np
    import torch

    if torch.__version__ != "2.5.1+cpu" or np.__version__ != "2.3.5":
        raise ValueError("use the historically pinned Torch/NumPy runtime")
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    torch.manual_seed(seed)
    root = Path.cwd()
    lineage = read_json(root / "lineage.json")
    checkpoint = root / f"{arm}_{seed}.pt"
    if digest(checkpoint) != lineage["checkpoints"][checkpoint.name]:
        raise ValueError("checkpoint differs before loading")
    tick = time.perf_counter_ns()
    module = load_module(root / f"native_{arm}.py", "native_replay_model")
    model = (
        module.RecordRewrite(module.Config(vocab_size=19)) if arm == "csm" else module.SlotStore()
    )
    # The exact CSM archive hash is checked before deserializing its trusted checkpoint.
    weights = torch.load(checkpoint, map_location="cpu", weights_only=(arm == "slot"))
    model.load_state_dict(weights["model"])
    model.eval()
    load_ns = time.perf_counter_ns() - tick
    before = {key: value.clone() for key, value in model.state_dict().items()}
    data = Dataset(root / "dataset", manifest_sha256=digest(root / "dataset/manifest.json"))
    rows = data.examples("validation", cutoff=CUTOFF, feature_fields=["memory"])

    def request(memory):
        result = {}
        for key in memory["keys"]:
            ids = torch.tensor([encode(memory, key)], dtype=torch.long)
            state = model.init_state(1, "cpu")
            for token in ids.unbind(1):
                logits, state = model.step(token, state)
            if not torch.isfinite(logits).all():
                raise ValueError("nonfinite inference")
            prediction = int(logits.argmax(-1).item())
            result[key] = TOKENS[prediction]
        json.dumps(result, sort_keys=True, allow_nan=False)
        return result

    predictions, measurements, warmed = {}, [], set()
    with torch.inference_mode():
        for row in rows:
            memory = row["features"]["memory"]
            length = len(memory["events"])
            if length not in warmed:
                request(memory)
                warmed.add(length)
            tick = time.perf_counter_ns()
            predictions[row["record_id"]] = request(memory)
            elapsed = time.perf_counter_ns() - tick
            measurements.append({"record_id": row["record_id"], "events": length,
                                 "elapsed_ns": elapsed})
    if any(not torch.equal(value, before[key]) for key, value in model.state_dict().items()):
        raise ValueError("inference mutated model weights")
    if digest(checkpoint) != lineage["checkpoints"][checkpoint.name]:
        raise ValueError("checkpoint bytes changed")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    write_json(output / "memory_predictions.json", {"predictions": predictions})
    write_json(output / "timing.json", {
        "measurements": measurements, "arm": arm, "seed": seed, "model_load_ns": load_ns,
        "python": platform.python_version(), "torch": torch.__version__, "numpy": np.__version__,
        "platform": platform.platform(), "threads": 1, "batch": 1, "weights_unchanged": True,
        "parameters": sum(p.numel() for p in model.parameters()),
        "warmup": "one full-map request per event length", "repetitions": 1,
        "scope": "fresh four-query full-map calls; imports/loading and disk writes excluded",
        "qualification": "EXPLORATORY_LOCAL_CPU_ONLY",
    })
    write_json(output / "metrics.json", {
        "requests": len(rows),
        "measured_seconds": sum(r["elapsed_ns"] for r in measurements) / 1e9,
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="mode", required=True)
    build = commands.add_parser("prepare")
    build.add_argument("package", type=Path)
    build.add_argument("destination", type=Path)
    execute = commands.add_parser("evaluate")
    execute.add_argument("arm", choices=("csm", "slot"))
    execute.add_argument("seed", type=int, choices=SEEDS)
    args = parser.parse_args()
    if args.mode == "prepare":
        print(json.dumps(prepare_source(args.package, args.destination), indent=2))
    else:
        evaluate(args.arm, args.seed)
