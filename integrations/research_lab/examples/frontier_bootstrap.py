"""Inspect or ingest the frontier program into an existing Research Lab OS store.

Bootstrapping creates a program and versioned research knowledge graph nodes only.
It DOES NOT register or run neural experiments, agent providers or GPU sessions.
Work orders require reviewed recipes, budgets, source pins and real workers.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_lab.core import Controller
from research_lab.evidence import link, put_node
from trainlab.runner import read_json

EXAMPLES = Path(__file__).resolve().parent
MANIFEST = EXAMPLES / "frontier_unified_program.json"
SEVEN = EXAMPLES / "seven_architecture_backlog.json"
ARCHPAR_IDS = {
    "PSN": "PSN",
    "PSN2": "PSN2",
    "DPSL": "DPSL",
    "Bounded-field": "BOUNDED_FIELD",
    "ATLAS-CASSA": "ATLAS_CASSA",
    "USEF-X": "USEF_X",
    "NSF-v8-NFD": "NSF_V8_NFD",
}


def validate(manifest, historic):
    if manifest.get("schema") != "research_lab.frontier_program.v1":
        raise ValueError("wrong frontier manifest schema")
    if manifest.get("status") != "COORDINATION_SPEC_ONLY_NO_AUTONOMOUS_WORKERS_STARTED":
        raise ValueError("a bootstrap must not imply active workers")
    lanes = manifest.get("lanes")
    if not isinstance(lanes, list) or not lanes:
        raise ValueError("missing lanes")
    ids = [lane["id"] for lane in lanes]
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate lane ID")
    if len(set(x["id"] for x in manifest["benchmarks"])) != len(manifest["benchmarks"]):
        raise ValueError("duplicate benchmark ID")
    if set(ARCHPAR_IDS) != {x["id"] for x in historic["lanes"]}:
        raise ValueError("historic seven backlog changed; manual reconciliation needed")
    missing = set(ARCHPAR_IDS.values()) - set(ids)
    if missing:
        raise ValueError("missing ARCHPAR lanes: " + ", ".join(sorted(missing)))
    graph = {}
    for lane in lanes:
        if not lane.get("next_falsifier") or not lane.get("comparators"):
            raise ValueError("lane missing primary falsifier or competitor: " + lane["id"])
        deps = lane.get("dependencies", [])
        if len(deps) != len(set(deps)) or any(dep not in ids for dep in deps):
            raise ValueError("bad dependencies: " + lane["id"])
        graph[lane["id"]] = deps
    visited, active = set(), set()

    def walk(node):
        if node in active:
            raise ValueError("cyclic frontier dependencies")
        if node in visited:
            return
        active.add(node)
        for dependency in graph[node]:
            walk(dependency)
        active.remove(node)
        visited.add(node)

    for node in ids:
        walk(node)
    return {"lanes": len(lanes), "benchmarks": len(manifest["benchmarks"]),
            "source_backlog": len(historic["lanes"]), "dependencies": sum(map(len, graph.values()))}


def bootstrap(root, manifest, *, seconds=3600, cpu_slots=2):
    """Import explicit planning nodes; do not create runnable claims or training jobs."""
    lab = Controller(root)
    lab.program(manifest["program_id"], manifest["objective"], seconds, 0, allow_paid=False)
    lab.resource("local", "cpu", cpu_slots, 0)
    prefix = "frontier." + manifest["version"].replace("-", "") + "."
    put_node(lab, prefix + "mission", "hypothesis", {
        "objective": manifest["objective"],
        "status": manifest["status"],
        "governance": manifest["governance"],
        "selection": manifest["integration_policy"],
        "science_rules": manifest["science_rules"],
    })
    for bench in manifest["benchmarks"]:
        put_node(lab, prefix + "benchmark." + bench["id"], "evidence", {
            "kind": "FROZEN_DESIGN_NOT_EXECUTED",
            "benchmark": bench,
        })
    for lane in manifest["lanes"]:
        put_node(lab, prefix + "lane." + lane["id"], "hypothesis", {
            "kind": "PARALLEL_RESEARCH_PROPOSAL",
            **lane,
        })
    for lane in manifest["lanes"]:
        own = prefix + "lane." + lane["id"]
        link(lab, own, "derived_from", prefix + "mission")
        for dep in lane["dependencies"]:
            link(lab, prefix + "lane." + dep, "next", own)
    return {"program": manifest["program_id"], "status": manifest["status"],
            "lanes_registered": len(manifest["lanes"]),
            "jobs_scheduled": 0, "trained_models": 0, "paid_compute_authorized": False}


def main():
    ap = argparse.ArgumentParser(
        description="Validate/bootstrap the nonexecuting frontier lane register"
    )
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("--root", type=Path)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--seconds", type=float, default=3600)
    ap.add_argument("--cpu-slots", type=int, default=2)
    args = ap.parse_args()
    manifest, historic = read_json(args.manifest), read_json(SEVEN)
    info = validate(manifest, historic)
    if args.check:
        print(json.dumps({"valid": True, **info}, indent=2))
    elif args.root is None:
        ap.error("--root is required for non-check mode")
    else:
        print(json.dumps({"valid": True, **info,
                          **bootstrap(args.root, manifest, seconds=args.seconds,
                                      cpu_slots=args.cpu_slots)}, indent=2))


if __name__ == "__main__":
    main()
