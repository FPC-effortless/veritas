"""Three-agent proposals -> TrainLab execution -> separately operated replay/review.

This executes exact-store engineering diagnostics, with zero model fits. Original
agent proposals remain immutable. Their learned-model work remains in the backlog.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from research_lab.adapters import import_catalog
from research_lab.core import Controller
from research_lab.evidence import ingest_proposal, link, put_node
from research_lab.execution import execute_claim, run_worker
from trainlab.runner import read_json, write_json


def bootstrap(root, *, examples=None):
    examples = examples or Path(__file__).resolve().parent
    lab = Controller(root)
    lab.program(
        "labos-acceptance",
        "Validate three independently designed bounded research workflows",
        1800,
        0,
    )
    lab.program(
        "seven-architecture-next", "Resolve outstanding ARCHPAR001/002 capability gates", 3600, 0
    )
    lab.resource("local", "cpu", 2, 0)
    import_catalog(lab, examples / "literature.json")
    backlog = read_json(examples / "seven_architecture_backlog.json")
    put_node(
        lab,
        "archpar.sources",
        "evidence",
        {"sources": backlog["sources"], "trust": "REPORT_LEVEL_ONLY"},
    )
    for lane in backlog["lanes"]:
        put_node(lab, "architecture." + lane["id"], "hypothesis", lane)
        link(lab, "architecture." + lane["id"], "derived_from", "archpar.sources")
    recipe_root = lab.root / "acceptance_recipes"
    recipe_root.mkdir(exist_ok=True)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=examples,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError("acceptance needs a source checkout with a pinned Git revision") from exc
    for lane in ("causal", "robustness", "efficiency"):
        proposal_path = examples / "proposals" / f"{lane}.json"
        proposal = read_json(proposal_path)
        ingest_proposal(lab, proposal)
        script = f"{lane}_fixture.py"
        shutil.copyfile(examples / script, recipe_root / script)
        (recipe_root / "proposals").mkdir(exist_ok=True)
        shutil.copyfile(proposal_path, recipe_root / "proposals" / proposal_path.name)
        for arm in ("candidate", "control"):
            write_json(
                recipe_root / f"{lane}-{arm}.json",
                {
                    "schema": "trainlab.experiment.v1",
                    "name": f"LABOS001 {lane} {arm}",
                    "description": (
                        "Constructed exact-store operational diagnostic; fitted_models=0"
                    ),
                    "command": [sys.executable, script, arm],
                    "seed": proposal["seeds"][0],
                    "timeout_seconds": 60,
                    "source_kind": "CONSTRUCTED",
                    "split_identity": "LABOS001-" + lane + "-frozen-generator-v1",
                    "inputs": [script, "proposals/" + proposal_path.name],
                    "artifacts": ["predictions.json", "diagnostics.json"],
                    "metrics": {"score": "max"},
                    "budget": {"fitted_models": 0, "data_seeds": 3},
                },
            )
        protocol = {
            "schema": "research_lab.protocol.v1",
            "id": "LABOS001-" + lane,
            "program": "labos-acceptance",
            "author": proposal["author"],
            "question": proposal["question"],
            "hypothesis": proposal["hypothesis"],
            "alternatives": proposal["competing_explanations"],
            "predictions": proposal["predictions"],
            "controls": proposal["controls"],
            "ablations": proposal["ablations"],
            "metric": "score",
            "direction": "max",
            "minimum_effect": proposal["minimum_effect"],
            "seeds": proposal["seeds"],
            "resource": "local",
            "slots": 1,
            "max_attempts": 1,
            "stopping_rule": proposal["stopping_rule"],
            "scope": "ENGINEERING_ONLY",
            "priority": 1,
            "source_commit": commit,
            "next_test": proposal["next_discriminating_test"],
            "limitations": [
                *proposal["limitations"],
                (
                    "LABOS001 executes the exact-store harness only. Learned fits and "
                    "external scientific replication are NOT_PERFORMED."
                ),
                "Score is a lane-specific engineering endpoint, never a pooled architecture score.",
                (
                    "Efficiency control score is a diagnostic zero contrast; each "
                    "invocation measures the full paired grid."
                ),
                (
                    "Clean-directory replication shares the CPU host, interpreter and "
                    "installed runner."
                ),
            ],
            "candidate": f"{lane}-candidate.json",
            "control": f"{lane}-control.json",
            "replication_tolerance": 0.20 if lane == "efficiency" else 0,
            "replay_artifacts": ["predictions.json"],
        }
        write_json(recipe_root / f"{lane}-protocol.json", protocol)
        lab.register(protocol, recipe_root)
        put_node(lab, "protocol." + lane, "experiment", protocol)
        link(lab, "protocol." + lane, "derived_from", "proposal." + lane)
    return lab


def run_primaries(lab):
    lab.worker("primary-a", "experiment", "local")
    lab.worker("primary-b", "experiment", "local")
    first = lab.claim("primary-a")
    if first:
        execute_claim(lab, first)
    reopened = Controller(lab.root)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_worker, reopened, worker) for worker in ("primary-a", "primary-b")
        ]
        for future in futures:
            future.result()
    primary = [x for x in reopened.status()["tasks"] if x["role"] == "experiment"]
    summary = {
        "schema": "research_lab.acceptance_execution.v1",
        "primary_tasks": len(primary),
        "succeeded": sum(x["status"] == "succeeded" for x in primary),
        "failed": [x["id"] for x in primary if x["status"] != "succeeded"],
        "controller_reopen": "PERFORMED_AFTER_FIRST_TASK",
        "model_fits": 0,
        "paid_compute": "NOT_USED",
        "replication": "SEPARATE_WORKER_REQUIRED",
        "review": "SEPARATE_SESSION_REQUIRED",
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(lab.root / "acceptance_execution.json", summary)
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    controller = bootstrap(args.root)
    print(json.dumps(run_primaries(controller) if args.run else controller.status(), indent=2))
