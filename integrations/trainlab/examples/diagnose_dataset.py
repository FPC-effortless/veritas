"""Public tabular clean/fault diagnosis through Forge, TrainLab and Research Lab."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

CUTOFF = "2026-11-14T00:00:00Z"
FIELDS = ["x", "context"]
SOURCE = "constructed/dataset-diagnosis"
SALT = "dataset-diagnosis-controls"


def views_match(expected, actual):
    from forge_data.core import canonical

    return canonical(expected) == canonical(actual)


def view(source, manifest):
    from forge_data.dataset import Dataset

    dataset = Dataset(source / "dataset", manifest_sha256=manifest)
    rows = []
    for split in ("train", "validation"):
        for row in dataset.examples(split, cutoff=CUTOFF, feature_fields=FIELDS + ["entity"]):
            rows.append({"id": row["record_id"], "split": split,
                         "features": {key: row["features"][key] for key in FIELDS},
                         "groups": {"entity": row["features"]["entity"]},
                         "label": row["target"]["value"] if row["target"] else None})
    return {"schema": "forge.diagnostic-input.v1", "feature_fields": FIELDS,
            "group_fields": ["entity"], "rows": rows}


def worker():
    from forge_data.diagnostics import diagnose
    from research_lab.ecosystem import _runtime, _sha
    from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
    from trainlab.runner import LabError, digest, read_json, write_json

    source = Path.cwd()
    protocol = read_json(source / "protocol.json")
    if protocol["runtime"] != _runtime():
        raise LabError("frozen diagnostic runtime changed")
    if not views_match(view(source, protocol["manifest_sha256"]), read_json(source / "view.json")):
        raise LabError("diagnostic view differs from Forge selection")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    result = {}

    def scan():
        result.update(diagnose(source / "view.json", sha256=protocol["view_sha256"],
                               max_rows=protocol["max_rows"], max_findings=100))

    def persist():
        write_json(output / "dataset-report.json", result)

    def execution(ctx):
        ctx.invoke("scan", phase="verify")
        ctx.invoke("persist", phase="persist")
        return {"status": "TESTED", "summary": "Report generated; dataset acceptance not inferred.",
                "metrics": {"scanned_rows": result["scope"]["scanned_rows"],
                            "findings": result["findings_total"]}}

    adapter = Adapter("dataset-diagnosis", {"scan": scan, "persist": persist},
                      {"persists": "none", "query_mutates": False, "reset": "not_applicable"})
    identities = {"model": _sha({"model": "NONE_DATASET_ONLY"}),
                  "dataset": protocol["view_sha256"], "code": digest(source / "driver.py"),
                  "configuration": _sha({"recipe": digest(source / "recipe.json"),
                                         "protocol": digest(source / "protocol.json")})}
    Workbench(adapter, identities, output / "diagnostics", max_calls=2, max_seconds=30,
              required_phases=("verify", "persist")).run([
                  Diagnostic("scan_execution", "1", ("scan", "persist"), execution,
                             "dataset report generation only; inspect dataset-report coverage")])
    if protocol["runtime"] != _runtime() or not result:
        raise LabError("runtime changed or diagnostic scan did not complete")
    write_json(output / "metrics.json", {"scanned_rows": result["scope"]["scanned_rows"]})


def prepare(source, case):
    from forge_data.core import _assign, canonical, release
    from research_lab.ecosystem import _runtime
    from trainlab.runner import digest, write_json

    source.mkdir(parents=True)
    shutil.copyfile(__file__, source / "driver.py")
    rows = [{"episode_id": f"episode-{i}", "subject_id": f"subject-{i}",
             "record_id": f"record-{i}", "observed_at": CUTOFF, "available_at": CUTOFF,
             "observation": {"x": i, "context": i % 4, "entity": f"entity-{i}"},
             "action": None, "outcome": {"status": "observed", "verified": True,
                                          "available_at": CUTOFF, "value": i % 2}}
            for i in range(128)]
    # Faults are declared before release, never injected into a frozen snapshot.
    assignment = _assign({SOURCE + "\0" + r["subject_id"] for r in rows}, SALT)
    train = [r for r in rows if assignment[SOURCE + "\0" + r["subject_id"]] == "train"]
    validation = [r for r in rows if assignment[SOURCE + "\0" + r["subject_id"]] == "validation"]
    if case != "clean":
        validation[0]["observation"] = dict(train[0]["observation"])
        validation[0]["outcome"]["value"] = 1 - train[0]["outcome"]["value"]
        validation[1]["observation"]["x"] = None
    (source / "rows.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    write_json(source / "source.json", {
        "dataset_id": "tabular-diagnostic-controls", "source_id": SOURCE,
        "source_version": "clean" if case == "clean" else "injected-faults",
        "adapter": "operations-jsonl", "license_id": "Apache-2.0",
        "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/523",
        "ai_use_allowed": True, "redistribution_allowed": True, "privacy_reviewed": True,
        "split_salt": SALT,
    })
    release(source / "rows.jsonl", source / "source.json", source / "dataset")
    manifest = digest(source / "dataset/manifest.json")
    write_json(source / "view.json", view(source, manifest))
    protocol = {"schema": "veritas.dataset-diagnostic-example.v1", "case": case,
                "manifest_sha256": manifest, "view_sha256": digest(source / "view.json"),
                "runtime": _runtime(), "max_rows": 1 if case == "fault-prefix" else 10000}
    write_json(source / "protocol.json", protocol)
    recipe = {"schema": "trainlab.experiment.v2", "name": "dataset-" + case,
              "description": "Public constructed dataset diagnosis; no model training",
              "command": [sys.executable, "driver.py", "--worker"], "seed": 1,
              "timeout_seconds": 60, "source_kind": "CONSTRUCTED", "split_identity": manifest,
              "inputs": ["driver.py", "protocol.json", "view.json", "dataset/manifest.json",
                         "dataset/train.jsonl", "dataset/validation.jsonl", "dataset/test.jsonl"],
              "artifacts": ["dataset-report.json", "diagnostics/report.json"],
              "metrics": {"scanned_rows": "max"}, "budget": {"model_fits": 0},
              "workload": {"kind": "debug", "training_method": None, "execution": "single_process"},
              "checks": {}}
    write_json(source / "recipe.json", recipe)
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
    for case in ("clean", "fault", "fault-prefix"):
        source = root / "sources" / case
        manifest = prepare(source, case)
        import_forge(lab, source / "dataset", manifest)
        receipt = run_experiment(source / "recipe.json", root / "runs")
        directory = root / "runs" / receipt["id"]
        if receipt["status"] != "succeeded" or not verify_run(directory)["valid"]:
            raise LabError("dataset diagnosis execution failed; retain the run for inspection")
        import_trainlab(lab, directory)
        path = directory / "output/dataset-report.json"
        report = read_json(path)
        node = "dataset-diagnosis." + _sha(report)[:24]
        put_node(lab, node, "finding", {"report": report, "artifact_sha256": digest(path)})
        link(lab, node, "derived_from", "trainlab." + receipt["id"])
        link(lab, node, "derived_from", "forge." + manifest[:24])
        results.append({"case": case, "run_id": receipt["id"], "state": report["state"],
                        "coverage": report["coverage"], "scope": report["scope"],
                        "findings_total": report["findings_total"]})
    write_json(root / "summary.json",
               {"runs": results, "scientific_qualification": "NOT_QUALIFIED"})
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
