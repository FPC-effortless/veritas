"""Public constructed adapter acceptance; fixed weights, no research training."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
from trainlab.runner import LabError, digest, read_json, run_experiment, verify_run, write_json

BACKENDS = ("cli", "store", "sklearn", "torch", "wrong")
CUTOFF = "2026-11-14T00:00:00Z"


def versions():
    result = {}
    for package in ("scikit-learn", "torch", "numpy"):
        try:
            result[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            result[package] = None
    return result


def worker(backend):
    from forge_data.dataset import Dataset
    from research_lab.ecosystem import _runtime, _sha

    protocol = read_json(Path("protocol.json"))
    if protocol["runtime"] != _runtime() or protocol["backend_versions"] != versions():
        raise LabError("frozen diagnostic runtime changed")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    model, data = {}, {}

    def load():
        if backend == "sklearn":
            import numpy as np
            from sklearn.linear_model import LinearRegression
            estimator = LinearRegression()
            estimator.coef_, estimator.intercept_ = np.array([2.0]), 0.0
            estimator.n_features_in_ = 1
            model["predict"] = lambda xs: estimator.predict(np.array(xs).reshape(-1, 1)).tolist()
        elif backend == "torch":
            import torch
            estimator = torch.nn.Linear(1, 1)
            with torch.no_grad():
                estimator.weight.fill_(2)
                estimator.bias.zero_()
            estimator.eval()
            def predict(xs):
                with torch.no_grad():
                    return estimator(torch.tensor(xs, dtype=torch.float32).reshape(-1, 1)) \
                        .flatten().tolist()
            model["predict"] = predict
        elif backend == "cli":
            def predict(xs):
                call = subprocess.run([sys.executable, "driver.py", "--predict", json.dumps(xs)],
                                      check=True, capture_output=True, text=True, timeout=5)
                return json.loads(call.stdout)
            model["predict"] = predict
        elif backend == "store":
            model["state"] = {}
            model["predict"] = lambda xs: [model["state"].get(x) for x in xs]
        else:
            model["predict"] = lambda xs: [3 * x for x in xs]  # Deliberate wrong-model control.

    def preprocess():
        dataset = Dataset(Path("dataset"), manifest_sha256=protocol["manifest_sha256"])
        rows = dataset.examples("validation", cutoff=CUTOFF, feature_fields=["x"])
        if not rows:
            raise LabError("empty constructed validation")
        data["xs"] = [row["features"]["x"] for row in rows]

    def update():
        model["state"].update({x: 2 * x for x in data["xs"]})

    def agreement():
        predictions = data["predictions"]
        expected = [2 * x for x in data["xs"]]
        valid = isinstance(predictions, list) and len(predictions) == len(expected)
        return valid and predictions == expected

    def persist():
        write_json(output / "predictions.json", {"predictions": data.get("predictions")})

    operations = {"load": load, "preprocess": preprocess,
                  "predict": lambda xs: model["predict"](xs), "verify": agreement,
                  "persist": persist}
    if backend == "store":
        operations.update(update=update, reset=lambda: model["state"].clear())
    package = {"sklearn": "sklearn", "torch": "torch"}.get(backend)
    if package and importlib.util.find_spec(package) is None:
        operations = {}  # Missing backend is explicitly unsupported, never a clean pass.
    state = {"persists": "key-value records until reset" if backend == "store" else "weights only",
             "query_mutates": False,
             "reset": "clear all records" if backend == "store" else "not_applicable"}
    adapter = Adapter(backend, operations, state)

    def outcome(ok, summary):
        return {"status": "TESTED" if ok else "FAILED", "summary": summary,
                "metrics": {"agreement": int(ok)}}

    def loaded(ctx):
        ctx.invoke("load", phase="load")
        return outcome(True, "Fixed-weight constructed model loaded.")

    def inputs(ctx):
        ctx.invoke("preprocess", phase="preprocess")
        if backend == "store":
            ctx.invoke("update", phase="update")
        return outcome(True, "Forge validation inputs selected; TEST not selected or scored.")

    def answers(ctx):
        data["predictions"] = ctx.invoke("predict", data["xs"], phase="answer", condition="cold")
        return outcome(ctx.invoke("verify", phase="verify"),
                       "Constructed y=2x reference agreement.")

    def reset(ctx):
        ctx.invoke("reset", phase="update")
        cleared = ctx.invoke("predict", data["xs"], phase="answer", condition="warm")
        ctx.invoke("update", phase="update")
        restored = ctx.invoke("predict", data["xs"], phase="answer", condition="warm")
        return outcome(cleared == [None] * len(data["xs"]) and restored == data["predictions"],
                       "Explicit store clear/repopulate semantics; not a neural-memory result.")

    def persisted(ctx):
        ctx.invoke("persist", phase="persist")
        return outcome(True, "Prediction artifact retained.")

    def gradients(ctx):
        from trainlab.diagnostics import require_finite
        count = require_finite("gradients", ctx.invoke("gradients", phase="verify"))
        return {"status": "TESTED", "summary": "Exposed gradient values finite.",
                "metrics": {"values": count}}

    checks = [Diagnostic("load", "1", ("load",), loaded, "constructed fixed model"),
              Diagnostic("inputs", "1", ("preprocess",), inputs, "public Forge validation"),
              Diagnostic("answers", "1", ("predict", "verify"), answers, "y=2x scalar examples"),
              Diagnostic("state_reset", "1", ("reset", "update", "predict"), reset,
                         "declared store clear and repopulation"),
              Diagnostic("persist", "1", ("persist",), persisted, "prediction JSON"),
              Diagnostic("gradients", "1", ("gradients",), gradients, "exposed gradients only")]
    identities = {"model": _sha({"backend": backend, "fixed_rule": "y=2x except wrong y=3x",
                                 "versions": versions()}),
                  "dataset": protocol["manifest_sha256"], "code": digest(Path("driver.py")),
                  "configuration": digest(Path(backend + ".json"))}
    report = Workbench(adapter, identities, output / "diagnostics", max_calls=30, max_seconds=30,
                       required_phases=("load", "preprocess", "answer", "verify", "persist")
                       + (("update",) if backend == "store" else ())).run(checks)
    if protocol["runtime"] != _runtime():
        raise LabError("runtime changed during diagnostic session")
    write_json(output / "metrics.json", {"checks_tested": sum(
        row["status"] == "TESTED" for row in report["coverage"])})


def run(root, backends):
    from forge_data.core import canonical, release
    from research_lab.adapters import import_forge, import_trainlab
    from research_lab.core import Controller
    from research_lab.ecosystem import _runtime, _sha
    from research_lab.evidence import link, put_node

    root.mkdir(parents=True, mode=0o700, exist_ok=False)
    source = root / "source"
    source.mkdir()
    shutil.copyfile(__file__, source / "driver.py")
    rows = [{"episode_id": f"example-{i}", "subject_id": f"subject-{i}",
             "record_id": f"record-{i}", "observed_at": CUTOFF, "available_at": CUTOFF,
             "observation": {"x": i}, "action": None,
             "outcome": {"status": "unknown", "verified": False}} for i in range(128)]
    (source / "rows.jsonl").write_bytes(b"".join(canonical(row) for row in rows))
    write_json(source / "source.json", {
        "dataset_id": "diagnostic-workbench-control", "source_id": "constructed/y2x",
        "source_version": "1", "adapter": "operations-jsonl", "license_id": "Apache-2.0",
        "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/519",
        "ai_use_allowed": True, "redistribution_allowed": True, "privacy_reviewed": True,
        "split_salt": "diagnostic-workbench-fixed-control",
    })
    release(source / "rows.jsonl", source / "source.json", source / "dataset")
    manifest = digest(source / "dataset/manifest.json")
    protocol = {"schema": "veritas.diagnostic-example.v1", "manifest_sha256": manifest,
                "runtime": _runtime(), "backend_versions": versions(), "backends": backends}
    write_json(source / "protocol.json", protocol)
    lab = Controller(root / "research_lab")
    import_forge(lab, source / "dataset", manifest)
    summary = []
    for backend in backends:
        recipe = {"schema": "trainlab.experiment.v2", "name": "diagnose-" + backend,
                  "description": "Public fixed-weight diagnostic acceptance, no training",
                  "command": [sys.executable, "driver.py", "--worker", backend],
                  "seed": 1, "timeout_seconds": 90, "source_kind": "CONSTRUCTED",
                  "split_identity": manifest,
                  "inputs": ["driver.py", "protocol.json", "dataset/manifest.json",
                             "dataset/train.jsonl", "dataset/validation.jsonl",
                             "dataset/test.jsonl"],
                  "artifacts": ["diagnostics/report.json", "predictions.json"],
                  "metrics": {"checks_tested": "max"},
                  "budget": {"model_fits": 0}, "workload": {"kind": "debug",
                  "training_method": None, "execution": "single_process"}, "checks": {}}
        write_json(source / (backend + ".json"), recipe)
        receipt = run_experiment(source / (backend + ".json"), root / "runs")
        directory = root / "runs" / receipt["id"]
        if not verify_run(directory)["valid"]:
            raise LabError("diagnostic execution receipt integrity failed")
        import_trainlab(lab, directory)
        path = directory / "output/diagnostics/report.json"
        report = read_json(path) if path.exists() else None
        if report:
            node = "diagnostic." + _sha(report)[:24]
            put_node(lab, node, "finding", {"report": report, "artifact_sha256": digest(path)})
            link(lab, node, "derived_from", "trainlab." + receipt["id"])
            link(lab, node, "derived_from", "forge." + manifest[:24])
        summary.append({"backend": backend, "run_id": receipt["id"], "status": receipt["status"],
                        "coverage": report["coverage"] if report else None,
                        "session": report["session"] if report else None})
    write_json(root / "summary.json", {"runs": summary,
                                      "scientific_qualification": "NOT_QUALIFIED"})
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--backends", nargs="+", choices=BACKENDS,
                        default=["cli", "store", "wrong"])
    parser.add_argument("--worker", choices=BACKENDS)
    parser.add_argument("--predict")
    args = parser.parse_args()
    if args.predict is not None:
        print(json.dumps([2 * x for x in json.loads(args.predict)]))
    elif args.worker:
        worker(args.worker)
    elif args.root and len(set(args.backends)) == len(args.backends):
        run(args.root.resolve(), args.backends)
    else:
        parser.error("new --root and unique --backends required")
