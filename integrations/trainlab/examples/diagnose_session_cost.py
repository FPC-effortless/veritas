"""Bounded CPU session controls through Forge, TrainLab and Research Lab."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

CUTOFF = "2026-11-14T00:00:00Z"
FIELDS = ["key", "value", "query"]
LIMITS = {
    "wall_seconds": 5,
    "cpu_seconds": 2,
    "address_space_bytes": 256 * 1024**2,
    "file_bytes": 1024**2,
}
POINTS = [(backend, length) for length in (8, 16) for backend in ("store", "replay")]
REPEATS = 100


def view(source, manifest):
    from forge_data.dataset import Dataset

    dataset = Dataset(source / "dataset", manifest_sha256=manifest)
    return [
        {"id": row["record_id"], **row["features"]}
        for row in dataset.examples("validation", cutoff=CUTOFF, feature_fields=FIELDS)
    ]


def session(backend, length, output):
    # Only stdlib imports and unlabeled public input enter this trusted CPU target.
    events = json.loads(Path("events.json").read_text())[:length]
    predictions = []
    for repeat in range(REPEATS):
        memory, history = {}, []
        for event in events:
            if backend == "store":
                memory[event["key"]] = event["value"]
                answer = memory.get(event["query"])
            elif backend == "replay":
                history.append((event["key"], event["value"]))
                answer = next((v for k, v in reversed(history) if k == event["query"]), None)
            else:
                raise ValueError("unknown backend")
            predictions.append({"id": f"{repeat}:{event['id']}", "answer": answer})
    output.write_text(json.dumps(predictions))


def expected_predictions(events):
    # Separate history oracle in the supervisor; no target predictions reused.
    answers = []
    for repeat in range(REPEATS):
        for i, event in enumerate(events):
            matches = [e for e in events[: i + 1] if e["key"] == event["query"]]
            answers.append(
                {
                    "id": f"{repeat}:{event['id']}",
                    "answer": matches[-1]["value"] if matches else None,
                }
            )
    return answers


def worker():
    from forge_data.core import canonical
    from research_lab.ecosystem import _runtime, _sha
    from trainlab.experiment_diagnostics import quality_cost
    from trainlab.research_diagnostics import Adapter, Diagnostic, Workbench
    from trainlab.resource_diagnostics import EXECUTION, run_command
    from trainlab.runner import LabError, digest, read_json, write_json

    source, output = Path.cwd(), Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    protocol = read_json(source / "protocol.json")
    if protocol["runtime"] != _runtime():
        raise LabError("runtime changed")
    events = view(source, protocol["manifest_sha256"])
    if canonical(events) != canonical(read_json(source / "events.json")) or len(events) < 16:
        raise LabError("Forge selection changed or too short")
    reports, points = {}, []
    identities = {
        "model": _sha("constructed-store-and-history-controls"),
        "dataset": digest(source / "events.json"),
        "code": digest(source / "driver.py"),
        "configuration": _sha([digest(source / "protocol.json"), digest(source / "recipe.json")]),
    }

    def measure(backend, length):
        name = f"{backend}-{length}"
        root = output / name
        command = (
            [sys.executable, "-c", "pass"]
            if backend == "noop"
            else [
                sys.executable,
                str(source / "driver.py"),
                "--session",
                backend,
                "--length",
                str(length),
                "--predictions",
                str(root / "predictions.json"),
            ]
        )
        receipt = run_command(
            command,
            root,
            cwd=source,
            identities={**identities, "model": _sha(backend)},
            workload_sha256=_sha([events[:length], REPEATS, "update-query-v1"]),
            limits=LIMITS,
            execution=EXECUTION,
        )
        reports[name] = {"receipt": receipt, "quality": None, "predictions_sha256": None}
        if backend != "noop" and (root / "predictions.json").is_file():
            predictions = read_json(root / "predictions.json")
            expected = expected_predictions(events[:length])
            # Mapping/order/count must match exactly; malformed outputs cannot earn credit.
            exact = (
                type(predictions) is list
                and len(predictions) == len(expected)
                and all(
                    type(p) is dict and set(p) == {"id", "answer"} and p["id"] == e["id"]
                    for p, e in zip(predictions, expected)
                )
            )
            quality = (
                sum(canonical(p) == canonical(e) for p, e in zip(predictions, expected))
                / len(expected)
                if exact
                else 0.0
            )
            reports[name].update(
                quality=quality, predictions_sha256=digest(root / "predictions.json")
            )
        if backend != "noop":
            points.append(
                {
                    "id": name,
                    "quality": reports[name]["quality"] or 0.0,
                    "session_seconds": receipt["wall_seconds"],
                    "cost_status": receipt["cost_coverage"],
                    **{
                        k: receipt[k]
                        for k in ("workload_sha256", "hardware_sha256", "boundary_sha256")
                    },
                }
            )
        return receipt["wall_seconds"]

    def persist():
        write_json(
            output / "session-reports.json",
            {
                "sessions": reports,
                "quality_cost": {
                    str(length): quality_cost([p for p in points if p["id"].endswith(f"-{length}")])
                    for length in (8, 16)
                },
                "scope": "Constructed CPU controls; startup included; no model ranking.",
                "startup_control": "noop-0; do not subtract or interpret as calibrated overhead",
                "scientific_qualification": "NOT_QUALIFIED",
            },
        )

    operations = {f"{b}-{n}": (lambda b=b, n=n: measure(b, n)) for b, n in POINTS}
    operations.update({"noop-0": lambda: measure("noop", 0), "persist": persist})
    adapter = Adapter(
        "cpu-session-controls",
        operations,
        {
            "persists": "one fresh process per session",
            "query_mutates": False,
            "reset": "new_process",
        },
    )

    def check(ctx):
        for name in operations:
            ctx.invoke(name, phase="persist" if name == "persist" else "verify")
        return {
            "status": "TESTED",
            "summary": "Five bounded session attempts retained.",
            "metrics": {"sessions": len(reports)},
        }

    Workbench(
        adapter,
        identities,
        output / "diagnostics",
        max_calls=6,
        max_seconds=40,
        required_phases=("verify", "persist"),
    ).run(
        [
            Diagnostic(
                "session_execution",
                "1",
                tuple(operations),
                check,
                "Public CPU controls; no architecture fitting or GPU work",
            )
        ]
    )
    if protocol["runtime"] != _runtime() or len(reports) != 5:
        raise LabError("incomplete session execution or changed runtime")
    write_json(output / "metrics.json", {"sessions": len(reports)})


def prepare(source):
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
            "observation": {"key": i % 8, "value": i, "query": (i + 3) % 11},
            "action": None,
            "outcome": {"status": "observed", "verified": True, "available_at": CUTOFF, "value": 0},
        }
        for i in range(256)
    ]
    (source / "rows.jsonl").write_bytes(b"".join(canonical(r) for r in rows))
    write_json(
        source / "source.json",
        {
            "dataset_id": "cpu-session-controls",
            "source_id": "constructed/session-controls",
            "source_version": "1",
            "adapter": "operations-jsonl",
            "license_id": "Apache-2.0",
            "provenance_uri": "https://github.com/FPC-effortless/veritas/issues/532",
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
            "split_salt": "session-controls",
        },
    )
    release(source / "rows.jsonl", source / "source.json", source / "dataset")
    manifest = digest(source / "dataset/manifest.json")
    write_json(source / "events.json", view(source, manifest))
    write_json(
        source / "protocol.json",
        {
            "schema": "veritas.session-controls.v1",
            "manifest_sha256": manifest,
            "runtime": _runtime(),
            "repeats": REPEATS,
            "limits": LIMITS,
            "model_fits": 0,
            "execution": "CPU synchronous trusted commands",
        },
    )
    artifacts = ["session-reports.json", "diagnostics/report.json"]
    for backend, length in [*POINTS, ("noop", 0)]:
        artifacts.extend(
            f"{backend}-{length}/{name}"
            for name in (
                "request.json",
                "receipt.json",
                "limits-applied.json",
                "stdout.log",
                "stderr.log",
            )
        )
        if backend != "noop":
            artifacts.append(f"{backend}-{length}/predictions.json")
    write_json(
        source / "recipe.json",
        {
            "schema": "trainlab.experiment.v2",
            "name": "cpu-session-controls",
            "description": "Public constructed CPU cost controls; zero model fits",
            "command": [sys.executable, "driver.py", "--worker"],
            "seed": 1,
            "timeout_seconds": 60,
            "source_kind": "CONSTRUCTED",
            "split_identity": manifest,
            "inputs": [
                "driver.py",
                "protocol.json",
                "events.json",
                "dataset/manifest.json",
                "dataset/train.jsonl",
                "dataset/validation.jsonl",
                "dataset/test.jsonl",
            ],
            "artifacts": artifacts,
            "metrics": {"sessions": "max"},
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
    source = root / "source"
    manifest = prepare(source)
    lab = Controller(root / "research_lab")
    import_forge(lab, source / "dataset", manifest)
    receipt = run_experiment(source / "recipe.json", root / "runs")
    directory = root / "runs" / receipt["id"]
    if receipt["status"] != "succeeded" or not verify_run(directory)["valid"]:
        raise LabError("session diagnostic execution failed; retain run for inspection")
    import_trainlab(lab, directory)
    path = directory / "output/session-reports.json"
    report = read_json(path)
    node = "cpu-sessions." + _sha(report)[:24]
    put_node(lab, node, "finding", {"report": report, "artifact_sha256": digest(path)})
    link(lab, node, "derived_from", "trainlab." + receipt["id"])
    link(lab, node, "derived_from", "forge." + manifest[:24])
    summary = {
        "run_id": receipt["id"],
        "sessions": {
            k: {
                "state": v["receipt"]["state"],
                "wall_seconds": v["receipt"]["wall_seconds"],
                "quality": v["quality"],
            }
            for k, v in report["sessions"].items()
        },
        "model_fits": 0,
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(root / "summary.json", summary)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--session", choices=("store", "replay"))
    parser.add_argument("--length", type=int, choices=(8, 16))
    parser.add_argument("--predictions", type=Path)
    args = parser.parse_args()
    if args.session and args.length and args.predictions:
        session(args.session, args.length, args.predictions)
    elif args.worker:
        worker()
    elif args.root:
        run(args.root.resolve())
    else:
        parser.error("new --root required")
