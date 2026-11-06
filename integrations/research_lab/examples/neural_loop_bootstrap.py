"""Explicit opt-in real neural operating acceptance; never part of ordinary CI."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from research_lab.autonomy import register_lane
from research_lab.core import Controller
from trainlab.runner import write_json


def bootstrap(root):
    source = Path(__file__).with_name("neural_loop_train.py")
    source_path = "integrations/research_lab/examples/neural_loop_train.py"
    repo = Path(__file__).resolve().parents[3]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    committed = subprocess.check_output(["git", "show", commit + ":" + source_path], cwd=repo)
    if source.read_bytes() != committed:
        raise ValueError("commit the exact trainer source before neural acceptance")
    lab = Controller(root)
    lab.program(
        "neural-operations",
        "Prove a bounded trained GRU evidence loop with an independent replay and review",
        20000,
        0,
    )
    lab.resource("local", "cpu", 2, 0)
    recipes = lab.root / "neural-recipes"
    recipes.mkdir(exist_ok=True)
    shutil.copyfile(Path(__file__).with_name("neural_loop_train.py"), recipes / "trainer.py")
    profiles = {}
    for profile, delay, updates in (("initial", 4, 100), ("longer", 12, 100), ("repair", 4, 200)):
        for arm in ("candidate", "control"):
            write_json(
                recipes / f"{profile}-{arm}.json",
                {
                    "schema": "trainlab.experiment.v1",
                    "name": f"GRU loop {profile} {arm}",
                    "description": (
                        "Real standard GRU fit on constructed copy data; operational evidence only"
                    ),
                    "command": [sys.executable, "trainer.py", arm, str(delay), str(updates)],
                    "seed": 11,
                    "timeout_seconds": 120,
                    "source_kind": "CONSTRUCTED",
                    "split_identity": f"generated-copy-v1-delay{delay}-dev8901-train-seed-plus101",
                    "inputs": ["trainer.py"],
                    "artifacts": ["checkpoint.pt", "predictions.json", "training.json"],
                    "metrics": {
                        "accuracy": "max",
                        "train_loss": "min",
                        "fitted_models": "max",
                        "parameters": "max",
                    },
                    "budget": {
                        "fitted_models": 1,
                        "optimizer_updates": updates,
                        "batch_size": 32,
                        "tokens_per_example": delay + 1,
                    },
                },
            )
        p = {
            "schema": "research_lab.protocol.v1",
            "id": "template-" + profile,
            "program": "neural-operations",
            "author": "root-designer",
            "question": (
                "Can the real recurrent trainer complete a replayable delayed-copy contrast?"
            ),
            "hypothesis": (
                "Keeping recurrent state improves exact recall compared with per-token reset."
            ),
            "alternatives": [
                "The optimizer has not learned the task",
                "A reset model can exploit the output marginal",
            ],
            "predictions": ["Carry should exceed reset", "Longer delays may reduce carry recall"],
            "controls": [
                "same initialized parameters, training batches, optimizer updates and DEV data",
                "state reset at every token in the control",
            ],
            "ablations": ["reset carried state"],
            "metric": "accuracy",
            "direction": "max",
            "minimum_effect": 0.10,
            "seeds": [11, 23, 37],
            "resource": "local",
            "slots": 1,
            "max_attempts": 1,
            "stopping_rule": (
                "Finish the frozen optimizer updates in every arm/seed; "
                "do not retry based on accuracy"
            ),
            "scope": "SYNTHETIC_RESEARCH",
            "priority": 1,
            "source_commit": commit,
            "limitations": [
                (
                    "Generated delayed-copy operational assay; "
                    "no TAC-OSM or frontier architecture qualification"
                ),
                "Train/DEV examples overlap in this 15-class assay; no generalization claim",
                "Same-host/runtime replay; no external replication",
                "No live LLM scientist or real-world data claim",
                "No optimizer-resume claim; queue and completed checkpoints are persistent",
            ],
            "next_test": (
                "If supported increase delay; otherwise increase preregistered training steps; "
                "at most two rounds"
            ),
            "candidate": f"{profile}-candidate.json",
            "control": f"{profile}-control.json",
            "replication_tolerance": 0,
            "replay_artifacts": ["predictions.json"],
        }
        write_json(recipes / f"{profile}.json", p)
        profiles[profile] = {
            "protocol": f"{profile}.json",
            "transitions": {
                "BOUNDED_CONTRAST_SUPPORTED": "longer" if profile == "initial" else None,
                "BOUNDED_CONTRAST_NOT_SUPPORTED": "repair" if profile == "initial" else None,
            },
        }
    spec = {
        "schema": "research_lab.autonomy.v1",
        "id": "neural-loop",
        "program": "neural-operations",
        "initial": "initial",
        "profiles": profiles,
        "director": None,
        "max_rounds": 2,
    }
    write_json(recipes / "lane.json", spec)
    register_lane(lab, spec, recipes)
    workers = [
        {
            "id": f"neural-primary-{i}",
            "role": "experiment",
            "resource": "local",
            "principal": "root-designer",
        }
        for i in (1, 2)
    ]
    write_json(lab.root / "workers.json", workers)
    return lab


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    lab = bootstrap(args.root)
    print(lab.root)
