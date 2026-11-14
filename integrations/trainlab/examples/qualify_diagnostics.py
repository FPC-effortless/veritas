"""Qualify declared Forge and TrainLab checks on UCI Wine classification."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import sys
import warnings
from pathlib import Path
from time import perf_counter_ns

from forge_data.core import canonical
from forge_data.diagnostics import diagnose
from forge_data.quality_diagnostics import transformation_audit
from trainlab.diagnostic_qualification import score
from trainlab.experiment_diagnostics import classification_diagnostics
from trainlab.runner import LabError, digest, read_json, write_json

TIME = "2026-01-01T00:00:00Z"
CHECKS = ("MISSING_FEATURE", "SPLIT_CONTENT_OVERLAP", "EVALUATION_FIT", "COLLAPSED_OUTPUT")
CASES = ("clean", "missing-feature", "overlap", "evaluation-fit", "constant-output")
REPEATS = list(range(5))
LICENSE = {
    "dataset": "Wine",
    "credit": "Aeberhard, S. and Forina, M. (1991). Wine. UCI Machine Learning Repository.",
    "source": "https://doi.org/10.24432/C5PC7J",
    "license": "CC BY 4.0",
    "license_url": "https://creativecommons.org/licenses/by/4.0/",
    "changes": "scikit-learn encoding, new split and ID assignments, injected faults",
}
BOUNDARY = {
    "includes": "read selected view, scale, fit logistic regression, predict, compute work hash",
    "added": "exact data audit, transform audit, classification metrics, finding normalization",
    "excludes": "dependency imports, preparation, evidence writes, scoring and process startup",
    "clock": "perf_counter_ns",
    "pair_order": "AB on even repeats, BA on odd repeats",
}


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def version_info():
    return {
        name: importlib.metadata.version(name)
        for name in ("scikit-learn", "numpy", "scipy", "threadpoolctl")
    }


def prepare(root):
    from sklearn.datasets import load_wine
    from sklearn.model_selection import train_test_split

    wine = load_wine()
    indices = list(range(len(wine.data)))
    train, validation = train_test_split(
        indices, test_size=0.25, stratify=wine.target, random_state=514
    )
    fields = list(wine.feature_names)
    rows = [
        {
            "id": f"wine-{i:03}",
            "split": split,
            "features": {k: float(v) for k, v in zip(fields, wine.data[i], strict=True)},
            "label": str(wine.target[i]),
        }
        for split, members in [("train", sorted(train)), ("validation", sorted(validation))]
        for i in members
    ]
    target = next(row for row in rows if row["split"] == "validation")
    source = next(
        row for row in rows if row["split"] == "train" and row["label"] == target["label"]
    )
    target_id, source_id = target["id"], source["id"]
    locations = {name: [] for name in CHECKS}
    locations["SPLIT_CONTENT_OVERLAP"] = [f"{source_id}/{target_id}"]
    locations["EVALUATION_FIT"] = [
        f"scale/{row['id']}" for row in rows if row["split"] == "validation"
    ]
    locations["COLLAPSED_OUTPUT"] = ["validation"]

    # The public pipeline receives only the view and execution switches.
    # Expected fault locations are stored in a separate auditor input.
    panel, workloads = [], {}
    for case in CASES:
        view = {
            "schema": "forge.diagnostic-input.v1",
            "feature_fields": fields,
            "group_fields": [],
            "rows": json.loads(json.dumps(rows)),
        }
        changed = next(row for row in view["rows"] if row["id"] == target_id)
        faults = set()
        if case == "missing-feature":
            del changed["features"][fields[0]]
            faults.add(("MISSING_FEATURE", f"{target_id}/{fields[0]}"))
        if case == "overlap":
            changed["features"] = dict(source["features"])
            faults.add(("SPLIT_CONTENT_OVERLAP", f"{source_id}/{target_id}"))
        if case == "evaluation-fit":
            faults.update(("EVALUATION_FIT", location) for location in locations["EVALUATION_FIT"])
        if case == "constant-output":
            faults.add(("COLLAPSED_OUTPUT", "validation"))
        path = root / f"{case}.json"
        write_json(path, view)
        config = {
            "view": path.name,
            "view_sha256": digest(path),
            "evaluation_fit": case == "evaluation-fit",
            "constant_output": case == "constant-output",
            "versions": version_info(),
            "driver_sha256": digest(Path(__file__)),
        }
        workloads[case] = config
        # The localizer is judged on a predefined subset of negative cells. All
        # remaining findings are counted as unadjudicated and prevent completion.
        negatives = {
            "MISSING_FEATURE": [f"{target_id}/{f}" for f in fields] + [f"{source_id}/{fields[0]}"],
            "SPLIT_CONTENT_OVERLAP": locations["SPLIT_CONTENT_OVERLAP"],
            "EVALUATION_FIT": locations["EVALUATION_FIT"],
            "COLLAPSED_OUTPUT": locations["COLLAPSED_OUTPUT"],
        }
        panel.append(
            {
                "id": case,
                "workload_sha256": sha(config),
                "targets": [
                    {"check": k, "location": loc, "fault": (k, loc) in faults}
                    for k, ids in negatives.items()
                    for loc in ids
                ],
            }
        )
    write_json(
        root / "fault-panel.json",
        {
            "schema": "trainlab.diagnostic-fault-panel.v1",
            "repeats": REPEATS,
            "cases": panel,
        },
    )
    write_json(
        root / "workloads.json",
        {
            "dataset": LICENSE,
            "dataset_sha256": sha(rows),
            "boundary": BOUNDARY,
            "workloads": workloads,
        },
    )
    return workloads


def pipeline(root, config, *, instrumented):
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import StandardScaler

    started = perf_counter_ns()
    path = root / config["view"]
    if digest(path) != config["view_sha256"]:
        raise LabError("classification view changed")
    view = read_json(path)
    rows, fields = view["rows"], view["feature_fields"]
    training = [r for r in rows if r["split"] == "train"]
    validation = [r for r in rows if r["split"] == "validation"]
    fitted = rows if config["evaluation_fit"] else training

    def inputs(records):
        return [[row["features"].get(f, 0.0) for f in fields] for row in records]

    scaler = StandardScaler().fit(inputs(fitted))
    y_train = [r["label"] for r in training]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        model = LogisticRegression(max_iter=300).fit(scaler.transform(inputs(training)), y_train)
    probabilities = model.predict_proba(scaler.transform(inputs(validation))).tolist()
    classes = model.classes_.tolist()
    if config["constant_output"]:
        probabilities = [[1.0, 0.0, 0.0] for _ in validation]
    outputs = [
        {
            "id": row["id"],
            "label": row["label"],
            "probabilities": p,
            "prediction": classes[max(range(len(p)), key=p.__getitem__)],
        }
        for row, p in zip(validation, probabilities, strict=True)
    ]
    fit_ids = [row["id"] for row in fitted]
    work = sha(
        {
            "outputs": outputs,
            "fit_ids": fit_ids,
            "coef": model.coef_.tolist(),
            "intercept": model.intercept_.tolist(),
        }
    )
    reports, checks = None, []
    if instrumented:
        reports = {
            "exact": diagnose(path, sha256=config["view_sha256"]),
            "transforms": transformation_audit(
                path,
                sha256=config["view_sha256"],
                transforms=[
                    {
                        "id": "scale",
                        "outputs": fields,
                        "fit_scope": "fitted",
                        "fit_ids": fit_ids,
                        "uses_target": False,
                    }
                ],
                availability=[
                    {"id": row["id"], "field": f, "available_at": TIME, "prediction_at": TIME}
                    for row in rows
                    for f in fields
                ],
            ),
            "classification": classification_diagnostics(outputs, classes=classes),
        }
        checks = observations(reports)
    return {
        "elapsed": perf_counter_ns() - started,
        "work": work,
        "reports": reports,
        "checks": checks,
        "outputs": outputs,
    }


def observations(reports):
    exact, transforms, behavior = (reports[k] for k in ("exact", "transforms", "classification"))
    findings = {name: set() for name in CHECKS}
    for item in exact["findings"]:
        rows = item["rows"]
        if item["kind"] == "MISSING_FEATURE":
            findings["MISSING_FEATURE"].add(f"{rows[0]['id']}/{item['field']}")
        elif item["kind"] == "SPLIT_CONTENT_OVERLAP":
            ordered = sorted(rows, key=lambda r: r["split"])
            findings["SPLIT_CONTENT_OVERLAP"].add("/".join(r["id"] for r in ordered))
    transform = transforms["observations"]
    for item in transform["findings"]:
        if item["kind"] == "EVALUATION_FIT":
            findings["EVALUATION_FIT"].add(f"{item['transform']}/{item['row']}")
    if len(behavior["observations"]["prediction_counts"]) == 1:
        findings["COLLAPSED_OUTPUT"].add("validation")
    exact_complete = exact["state"] == "COMPLETE" and not exact["findings_omitted"]
    coverage = {
        "MISSING_FEATURE": exact_complete,
        "SPLIT_CONTENT_OVERLAP": exact_complete
        and not any(r["kind"] in ("MISSING_FEATURE", "NULL_FEATURE") for r in exact["findings"]),
        "EVALUATION_FIT": transform["finding_count"] == len(transform["findings"])
        and not transform["unknown_count"]
        and not transform["missing_availability"]
        and not transform["uncovered_fields"],
        "COLLAPSED_OUTPUT": behavior["coverage"][0]["status"] == "TESTED",
    }
    return [
        {"name": k, "status": "CHECKED" if coverage[k] else "INCONCLUSIVE", "locations": sorted(v)}
        for k, v in findings.items()
    ]


def execute(root, configs):
    from threadpoolctl import threadpool_info, threadpool_limits

    work_results = []
    with threadpool_limits(limits=1):
        hardware = {
            "machine": platform.machine(),
            "platform": platform.platform(),
            "cpu": platform.processor(),
            "python": sys.version,
            "threadpools": threadpool_info(),
            "packages": version_info(),
        }
        hw = sha(hardware)
        for repeat in REPEATS:
            for case, config in configs.items():
                base_first = repeat % 2 == 0
                arms = {
                    instrumented: pipeline(root, config, instrumented=instrumented)
                    for instrumented in (not base_first, base_first)
                }
                a, b = arms[False], arms[True]
                path = root / f"{case}-{repeat}-diagnostics.json"
                write_json(path, {"reports": b["reports"], "outputs": b["outputs"]})
                work_results.append(
                    {
                        "case": case,
                        "repeat": repeat,
                        "workload_sha256": sha(config),
                        "checks": b["checks"],
                        "timing": {
                            "baseline_ns": a["elapsed"],
                            "diagnostic_ns": b["elapsed"],
                            "baseline_work_sha256": a["work"],
                            "diagnostic_work_sha256": b["work"],
                            "hardware_sha256": hw,
                            "boundary_sha256": sha(BOUNDARY),
                        },
                    }
                )
    write_json(root / "runtime.json", hardware)
    write_json(
        root / "observations.json",
        {
            "schema": "trainlab.diagnostic-fault-observations.v1",
            "runs": work_results,
        },
    )


def verify_evidence(root):
    # Recount from saved tool artifacts, independent of the scorer's outcome loop.
    expected = read_json(root / "fault-panel.json")["cases"]
    recorded = read_json(root / "observations.json")["runs"]
    by_case = {c["id"]: c["targets"] for c in expected}
    hits = alarms = misses = clean = unobserved = 0
    for run in recorded:
        raw = read_json(root / f"{run['case']}-{run['repeat']}-diagnostics.json")
        if observations(raw["reports"]) != run["checks"]:
            raise LabError("saved diagnostics disagree with normalized observations")
        checks = {c["name"]: c for c in run["checks"]}
        for target in by_case[run["case"]]:
            check = checks[target["check"]]
            found = target["location"] in check["locations"]
            if not found and check["status"] != "CHECKED":
                unobserved += 1
            elif target["fault"]:
                hits += found
                misses += not found
            elif found:
                alarms += 1
            else:
                clean += 1
    return {
        "true_positive": hits,
        "false_positive": alarms,
        "false_negative": misses,
        "true_negative": clean,
        "unobserved": unobserved,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    configs = prepare(root)
    panel_path, observation_path = root / "fault-panel.json", root / "observations.json"
    panel_pin = digest(panel_path)
    execute(root, configs)
    result = score(
        panel_path,
        observation_path,
        panel_sha256=panel_pin,
        observations_sha256=digest(observation_path),
    )
    result["source_sha256"] = digest(Path(__file__))
    recount = verify_evidence(root)
    if any(result["counts"][key] != value for key, value in recount.items()):
        raise LabError("qualification recount disagrees")
    write_json(root / "independent-recount.json", recount)
    write_json(root / "qualification.json", result)
    write_json(
        root / "manifest.json",
        {
            "files": {path.name: digest(path) for path in sorted(root.iterdir())},
            "scope": "Public local evidence. Keep the manifest digest outside this directory.",
        },
    )
    print(
        json.dumps(
            {
                "root": str(root),
                "status": result["status"],
                "counts": result["counts"],
                "rates": result["rates"],
                "overhead": result["overhead"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
