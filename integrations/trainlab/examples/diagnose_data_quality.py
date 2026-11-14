"""Public dataset-quality controls composed through Forge, TrainLab and Research Lab."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

CUTOFF = "2026-11-14T00:00:00Z"
SOURCE = "constructed/data-quality-controls"
SALT = "data-quality-controls"
FIELDS = ["x", "category", "text"]


def view(source, manifest):
    from forge_data.dataset import Dataset

    dataset = Dataset(source / "dataset", manifest_sha256=manifest)
    return {
        "schema": "forge.diagnostic-input.v1",
        "feature_fields": FIELDS,
        "group_fields": [],
        "rows": [
            {
                "id": row["record_id"],
                "split": split,
                "features": row["features"],
                "label": row["target"]["value"],
            }
            for split in ("train", "validation")
            for row in dataset.examples(split, cutoff=CUTOFF, feature_fields=FIELDS)
        ],
    }


def worker():
    from forge_data.core import canonical
    from forge_data.quality_diagnostics import (
        adjudicate,
        distributions,
        near_duplicates,
        transformation_audit,
    )
    from research_lab.ecosystem import _runtime, _sha
    from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
    from trainlab.runner import LabError, digest, read_json, write_json

    source = Path.cwd()
    protocol = read_json(source / "protocol.json")
    if protocol["runtime"] != _runtime():
        raise LabError("runtime changed")
    selected = view(source, protocol["manifest_sha256"])
    if canonical(selected) != canonical(read_json(source / "view.json")):
        raise LabError("Forge selection changed")
    inputs = read_json(source / "diagnostic-inputs.json")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    reports = {}
    path, pin = source / "view.json", digest(source / "view.json")

    def scan():
        reports.update(
            {
                "distributions": distributions(
                    path,
                    path,
                    reference_sha256=pin,
                    current_sha256=pin,
                    fields={"x": "numeric", "category": "categorical"},
                    thresholds={"numeric": 0.2, "categorical": 0.2, "missingness": 0.05},
                    max_rows=1 if protocol["case"] == "partial" else 10000,
                ),
                "adjudication": adjudicate(path, sha256=pin, reviews=inputs["reviews"]),
                "transformations": transformation_audit(
                    path,
                    sha256=pin,
                    transforms=inputs["transforms"],
                    availability=inputs["availability"],
                ),
                "near_duplicates": near_duplicates(
                    path,
                    sha256=pin,
                    field="text",
                    max_pairs=1 if protocol["case"] == "partial" else 10000,
                ),
            }
        )

    def persist():
        write_json(output / "quality-reports.json", reports)
        (output / "corrected-view.json").write_bytes(
            canonical(reports["adjudication"]["observations"]["document"])
        )

    def check(ctx):
        ctx.invoke("scan", phase="verify")
        ctx.invoke("persist", phase="persist")
        return {
            "status": "TESTED",
            "summary": "Constructed dataset controls executed; inspect reports.",
            "metrics": {"packs": len(reports)},
        }

    adapter = Adapter(
        "quality-controls",
        {"scan": scan, "persist": persist},
        {"persists": "none", "query_mutates": False, "reset": "not_applicable"},
    )
    identities = {
        "model": _sha({"model": "NONE_DATASET_ONLY"}),
        "dataset": pin,
        "code": digest(source / "driver.py"),
        "configuration": _sha(
            {"protocol": digest(source / "protocol.json"), "recipe": digest(source / "recipe.json")}
        ),
    }
    Workbench(
        adapter,
        identities,
        output / "diagnostics",
        max_calls=2,
        max_seconds=30,
        required_phases=("verify", "persist"),
    ).run(
        [
            Diagnostic(
                "quality_execution",
                "1",
                ("scan", "persist"),
                check,
                "Public synthetic quality controls; no model or actual human review",
            )
        ]
    )
    if protocol["runtime"] != _runtime() or len(reports) != 4:
        raise LabError("incomplete quality diagnostics or changed runtime")
    if (
        digest(output / "corrected-view.json")
        != reports["adjudication"]["observations"]["document_sha256"]
    ):
        raise LabError("corrected view identity mismatch")
    write_json(output / "metrics.json", {"packs": len(reports)})


def prepare(source, case):
    from forge_data.core import _assign, canonical, release
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
            "observation": {"x": 1, "category": "same", "text": f"token-{i} unique-{i}"},
            "action": None,
            "outcome": {"status": "observed", "verified": True, "available_at": CUTOFF, "value": 0},
        }
        for i in range(128)
    ]
    assignment = _assign({SOURCE + "\0" + r["subject_id"] for r in rows}, SALT)
    train = [r for r in rows if assignment[SOURCE + "\0" + r["subject_id"]] == "train"]
    validation = [r for r in rows if assignment[SOURCE + "\0" + r["subject_id"]] == "validation"]
    if case == "fault":
        for row in validation:
            row["observation"].update(x=10, category="novel")
        validation[0]["observation"]["text"] = train[0]["observation"]["text"]
        validation[1]["observation"]["x"] = None
    (source / "rows.jsonl").write_bytes(b"".join(canonical(r) for r in rows))
    write_json(
        source / "source.json",
        {
            "dataset_id": "data-quality-controls",
            "source_id": SOURCE,
            "source_version": case,
            "adapter": "operations-jsonl",
            "license_id": "Apache-2.0",
            "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/530",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": SALT,
        },
    )
    release(source / "rows.jsonl", source / "source.json", source / "dataset")
    manifest = digest(source / "dataset/manifest.json")
    selected = view(source, manifest)
    write_json(source / "view.json", selected)
    transforms = [
        {
            "id": "preprocessor",
            "outputs": FIELDS,
            "fit_scope": "stateless",
            "fit_ids": [],
            "uses_target": False,
        }
    ]
    availability = [
        {"id": r["id"], "field": field, "available_at": CUTOFF, "prediction_at": CUTOFF}
        for r in selected["rows"]
        for field in FIELDS
    ]
    if case == "fault":
        transforms[0].update(
            fit_scope="fitted", fit_ids=[validation[0]["record_id"]], uses_target=True
        )
        availability[0]["available_at"] = "2026-11-15T00:00:00Z"
    elif case == "partial":
        transforms[0].update(fit_scope="unknown", fit_ids=None, uses_target=None)
        availability = []
    write_json(
        source / "diagnostic-inputs.json",
        {
            "transforms": transforms,
            "availability": availability,
            "reviews": [
                {
                    "id": train[0]["record_id"],
                    "old_label": 0,
                    "new_label": 1,
                    "reviewer": "constructed-review-fixture-not-a-human",
                    "decision": "unresolved" if case == "partial" else "accept",
                    "rationale": "Versioning control; label truth and repair benefit unknown.",
                }
            ],
        },
    )
    write_json(
        source / "protocol.json",
        {
            "schema": "veritas.data-quality-example.v1",
            "case": case,
            "manifest_sha256": manifest,
            "runtime": _runtime(),
            "model_fits": 0,
            "review_scope": "Constructed records; no actual human adjudication or truth claim.",
        },
    )
    write_json(
        source / "recipe.json",
        {
            "schema": "trainlab.experiment.v2",
            "name": "quality-" + case,
            "description": "Public constructed data-quality controls; zero model fits",
            "command": [sys.executable, "driver.py", "--worker"],
            "seed": 1,
            "timeout_seconds": 60,
            "source_kind": "CONSTRUCTED",
            "split_identity": manifest,
            "inputs": [
                "driver.py",
                "protocol.json",
                "view.json",
                "diagnostic-inputs.json",
                "dataset/manifest.json",
                "dataset/train.jsonl",
                "dataset/validation.jsonl",
                "dataset/test.jsonl",
            ],
            "artifacts": ["quality-reports.json", "corrected-view.json", "diagnostics/report.json"],
            "metrics": {"packs": "max"},
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
    for case in ("clean", "fault", "partial"):
        source = root / "sources" / case
        manifest = prepare(source, case)
        import_forge(lab, source / "dataset", manifest)
        receipt = run_experiment(source / "recipe.json", root / "runs")
        directory = root / "runs" / receipt["id"]
        if receipt["status"] != "succeeded" or not verify_run(directory)["valid"]:
            raise LabError("quality diagnostic execution failed; retain run for inspection")
        import_trainlab(lab, directory)
        path = directory / "output/quality-reports.json"
        report = read_json(path)
        node = "data-quality." + _sha(report)[:24]
        put_node(lab, node, "finding", {"report": report, "artifact_sha256": digest(path)})
        link(lab, node, "derived_from", "trainlab." + receipt["id"])
        link(lab, node, "derived_from", "forge." + manifest[:24])
        results.append(
            {
                "case": case,
                "run_id": receipt["id"],
                "statuses": {k: v["status"] for k, v in report.items()},
                "near_duplicate_candidates": report["near_duplicates"]["observations"][
                    "match_count"
                ],
                "transform_findings": report["transformations"]["observations"]["finding_count"],
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
