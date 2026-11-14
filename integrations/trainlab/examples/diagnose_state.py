"""Public store lifecycle, reduction and repair controls through the ecosystem."""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
from pathlib import Path

CUTOFF = "2026-11-14T00:00:00Z"


class Store:
    def __init__(self, fault):
        self.data, self.fault = {}, fault

    def reset(self):
        self.data = {}

    def update(self, event):
        if event["op"] == "set":
            self.data[event["key"]] = event["value"]
        elif event["op"] == "delete":
            if self.fault != "stale":
                self.data.pop(event["key"], None)
            if self.fault == "collateral":
                self.data.pop("b", None)
        else:
            raise ValueError("unsupported store event")

    def query(self, key):
        return self.data.get(key)

    def snapshot(self):
        return self.data if self.fault == "alias" else copy.deepcopy(self.data)

    def restore(self, snapshot):
        self.data = snapshot if self.fault == "alias" else copy.deepcopy(snapshot)


def view(source, manifest):
    from forge_data.dataset import Dataset

    dataset = Dataset(source / "dataset", manifest_sha256=manifest)
    return {
        split: [
            {"id": r["record_id"], **r["features"]}
            for r in dataset.examples(split, cutoff=CUTOFF, feature_fields=["value", "group"])
        ]
        for split in ("train", "validation")
    }


def worker():
    from forge_data.core import canonical
    from research_lab.ecosystem import _runtime, _sha
    from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
    from trainlab.runner import LabError, digest, read_json, write_json
    from trainlab.state_diagnostics import (
        lifecycle,
        minimize_failure,
        restore_isolation,
        verify_repair,
        write_intervention,
    )

    source = Path.cwd()
    protocol = read_json(source / "protocol.json")
    if protocol["runtime"] != _runtime():
        raise LabError("runtime changed")
    data = view(source, protocol["manifest_sha256"])
    if canonical(data) != canonical(read_json(source / "view.json")):
        raise LabError("Forge selection changed")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    case = protocol["case"]
    store, peer = Store(case), Store(case)
    operations = {k: getattr(store, k) for k in ("reset", "update", "query", "snapshot")}
    operations.update(
        {"peer_" + k: getattr(peer, k) for k in ("reset", "update", "query", "restore")}
    )
    queries = [{"id": "a", "input": "a"}, {"id": "b", "input": "b"}]
    value = data["validation"][0]["value"]
    initial = [
        {"op": "set", "key": "a", "value": value},
        {"op": "set", "key": "b", "value": value + 1},
    ]
    event = {"op": "delete", "key": "a"}
    histories = [{"op": "set", "key": "noise-" + str(i), "value": i} for i in range(12)]
    histories += initial + [event]
    query = "b" if case == "collateral" else "a"

    def failure_probe(events):
        candidate, oracle = Store(case), {}
        for e in events:
            candidate.update(e)
            if e["op"] == "set":
                oracle[e["key"]] = e["value"]
            else:
                oracle.pop(e["key"], None)
        return canonical(candidate.query(query)) != canonical(oracle.get(query))

    def predict(fault, row, key):
        model = Store(fault)
        model.update({"op": "set", "key": "a", "value": row["value"]})
        model.update({"op": "set", "key": "b", "value": row["value"] + 1})
        model.update(event)
        return model.query(key)

    operations.update(
        {
            "failure_probe": failure_probe,
            "before_predict": lambda row, key: predict(case, row, key),
            "after_predict": lambda row, key: predict("clean", row, key),
        }
    )
    reports = {}
    operations["persist"] = lambda: write_json(output / "state-reports.json", reports)

    def check(ctx):
        reports["lifecycle"] = lifecycle(
            ctx,
            initial=initial,
            initial_expected={"a": value, "b": value + 1},
            queries=queries,
            steps=[
                {
                    "id": "delete",
                    "event": event,
                    "expected": {"a": None, "b": value + 1},
                    "touched": ["a"],
                }
            ],
            supported_ops=["set", "delete"],
        )
        reports["intervention"] = write_intervention(
            ctx, initial=initial, event=event, queries=queries
        )
        reports["restore"] = restore_isolation(
            ctx,
            initial=initial,
            queries=queries,
            expected={"a": value, "b": value + 1},
            mutation={"op": "set", "key": "a", "value": value + 2},
            mutated_expected={"a": value + 2, "b": value + 1},
            peer_mutation={"op": "set", "key": "b", "value": value + 3},
            peer_mutated_expected={"a": value, "b": value + 3},
        )
        reports["reducer"] = minimize_failure(
            histories,
            lambda events: ctx.invoke("failure_probe", events, phase="verify"),
            max_calls=50,
            max_seconds=10,
        )
        panels = {}
        for name, row, key in [
            ("fresh", data["validation"][2], "a"),
            ("regression", data["validation"][1], "b"),
        ]:
            panels[name] = [
                {
                    "id": row["id"],
                    "group": row["group"],
                    "expected": None if key == "a" else row["value"] + 1,
                    "before": {
                        "status": "observed",
                        "value": ctx.invoke("before_predict", row, key, phase="answer"),
                    },
                    "after": {
                        "status": "observed",
                        "value": ctx.invoke("after_predict", row, key, phase="answer"),
                    },
                }
            ]
        reports["repair"] = verify_repair(
            panels,
            required_ids={k: [r["id"] for r in rows] for k, rows in panels.items()},
            freshness={
                "evaluation_sha256": _sha(panels),
                "frozen_before_evaluation": True,
                "used_for_selection": False,
            },
            selection_groups=[r["group"] for r in data["train"] + data["validation"][:1]],
            hypotheses=[
                {"id": "update-path", "description": "An update operation corrupts declared state."}
            ],
            interventions=[
                {
                    "hypothesis_id": "update-path",
                    "observation": "See paired omitted-write outputs.",
                    "evidence_sha256": _sha(reports["intervention"]),
                }
            ],
        )
        ctx.invoke("persist", phase="persist")
        return {
            "status": "TESTED",
            "summary": "Store controls executed; inspect individual reports.",
            "metrics": {"reports": len(reports)},
        }

    adapter = Adapter(
        "store-controls",
        operations,
        {"persists": "dictionary", "query_mutates": False, "reset": "fresh dictionary"},
    )
    identities = {
        "model": _sha({"store_fault": case}),
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
        max_calls=200,
        max_seconds=30,
        required_phases=("setup", "update", "answer", "persist"),
    ).run([Diagnostic("state_controls", "1", (), check, "Constructed stores; not learned memory")])
    if protocol["runtime"] != _runtime() or len(reports) != 5:
        raise LabError("incomplete state diagnostic execution or changed runtime")
    write_json(output / "metrics.json", {"reports": len(reports)})


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
            "observation": {"value": i + 1, "group": f"subject-{i}"},
            "action": None,
            "outcome": {
                "status": "observed",
                "verified": True,
                "available_at": CUTOFF,
                "value": i + 1,
            },
        }
        for i in range(128)
    ]
    (source / "rows.jsonl").write_bytes(b"".join(canonical(r) for r in rows))
    write_json(
        source / "source.json",
        {
            "dataset_id": "state-diagnostic-controls",
            "source_id": "constructed/state-controls",
            "source_version": "1",
            "adapter": "operations-jsonl",
            "license_id": "Apache-2.0",
            "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/528",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": "state-diagnostic-controls",
        },
    )
    release(source / "rows.jsonl", source / "source.json", source / "dataset")
    manifest = digest(source / "dataset/manifest.json")
    write_json(source / "view.json", view(source, manifest))
    write_json(
        source / "protocol.json",
        {
            "schema": "veritas.state-diagnostic-example.v1",
            "case": case,
            "manifest_sha256": manifest,
            "runtime": _runtime(),
            "model_fits": 0,
            "freshness_boundary": "Distinct subjects share a generator; independence unproven.",
        },
    )
    write_json(
        source / "recipe.json",
        {
            "schema": "trainlab.experiment.v2",
            "name": "state-" + case,
            "description": "Constructed store diagnostic controls; zero model fits",
            "command": [sys.executable, "driver.py", "--worker"],
            "seed": 1,
            "timeout_seconds": 60,
            "source_kind": "CONSTRUCTED",
            "split_identity": manifest,
            "inputs": [
                "driver.py",
                "protocol.json",
                "view.json",
                "dataset/manifest.json",
                "dataset/train.jsonl",
                "dataset/validation.jsonl",
                "dataset/test.jsonl",
            ],
            "artifacts": ["state-reports.json", "diagnostics/report.json"],
            "metrics": {"reports": "max"},
            "budget": {"model_fits": 0},
            "workload": {"kind": "debug", "training_method": None, "execution": "single_process"},
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
    lab, results = Controller(root / "research_lab"), []
    for case in ("clean", "stale", "collateral", "alias"):
        source = root / "sources" / case
        manifest = prepare(source, case)
        import_forge(lab, source / "dataset", manifest)
        receipt = run_experiment(source / "recipe.json", root / "runs")
        directory = root / "runs" / receipt["id"]
        if receipt["status"] != "succeeded" or not verify_run(directory)["valid"]:
            raise LabError("state diagnostic execution failed; retain run for inspection")
        import_trainlab(lab, directory)
        path = directory / "output/state-reports.json"
        report = read_json(path)
        node = "state-diagnosis." + _sha(report)[:24]
        put_node(lab, node, "finding", {"report": report, "artifact_sha256": digest(path)})
        link(lab, node, "derived_from", "trainlab." + receipt["id"])
        link(lab, node, "derived_from", "forge." + manifest[:24])
        results.append(
            {
                "case": case,
                "run_id": receipt["id"],
                "statuses": {k: v["status"] for k, v in report.items()},
                "reduced_events": report["reducer"]["observations"]["candidate"],
            }
        )
    write_json(
        root / "summary.json",
        {"runs": results, "model_fits": 0, "scientific_qualification": "NOT_QUALIFIED"},
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
