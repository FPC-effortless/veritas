"""Run frozen diagnostic plans through TrainLab's existing capability Workbench."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import os
import shutil
import sys
import zipfile
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import numpy as np

from ..research_diagnostics import Adapter, Diagnostic, Workbench
from ..runner import contained_file, digest, read_json, write_json
from .artifacts import (
    canonical,
    decode_result,
    encode_result,
    implementation_identity,
    load_inputs,
    pinned_bytes,
    pinned_json,
    require,
    resolve,
    seal_bundle,
    validate_plan,
    verify_bundle,
)
from .registry import get_operation

MAX_EXPORT_BYTES = 2 * 1024 * 1024 * 1024
MAX_EXPORT_FILES = 8192


def _capabilities(value):
    if isinstance(value, dict):
        if any(key in value for key in ("literal", "bytes_hex", "artifact", "result")):
            return
        if "capability" in value:
            yield value["capability"]
            yield from _capabilities(value.get("context", {}))
            return
        for item in value.values():
            yield from _capabilities(item)
    elif isinstance(value, list):
        for item in value:
            yield from _capabilities(item)


def _load_adapter(plan, source, *, allow_native):
    if "adapter" not in plan:
        return Adapter(
            "saved-observations",
            {},
            {
                "persists": "none; independently copied saved observations",
                "query_mutates": False,
                "reset": "each diagnostic receives fresh input copies",
            },
        )
    require(allow_native, "native adapter execution requires explicit --allow-native")
    item = plan["adapter"]
    payload = pinned_bytes(source, item, maximum=2 * 1024 * 1024)
    # This is explicitly trusted local code, under the same authority as a recipe.
    # A private immutable-by-convention snapshot closes hash-then-import races
    # against the original path and avoids unbound pre-existing bytecode caches.
    with TemporaryDirectory(prefix="veritas-latent-adapter-") as temporary:
        path = Path(temporary) / "adapter.py"
        path.write_bytes(payload)
        spec = importlib.util.spec_from_file_location("_veritas_latent_user_adapter", path)
        require(spec is not None and spec.loader is not None, "cannot load trusted adapter")
        module = importlib.util.module_from_spec(spec)
        previous = sys.modules.get(spec.name)
        sys.modules[spec.name] = module
        try:
            spec.loader.exec_module(module)
            factory = getattr(module, item["factory"], None)
            require(callable(factory), "trusted adapter factory is missing")
            adapter = factory(copy.deepcopy(plan), source)
            require(isinstance(adapter, Adapter), "factory must return existing TrainLab Adapter")
            return adapter
        finally:
            if previous is None:
                sys.modules.pop(spec.name, None)
            else:
                sys.modules[spec.name] = previous


def _capture_inputs(plan, source, root):
    destination = root / "inputs"
    destination.mkdir(mode=0o700)
    items = list(plan["artifacts"].values())
    if "adapter" in plan:
        items.append(plan["adapter"])
    copied = set()
    for item in items:
        name = item["path"]
        if name in copied:
            continue
        src = contained_file(source, name)
        require(digest(src) == item["sha256"], "input changed while capturing evidence")
        target = destination / name
        require(not target.exists(), "input destinations collide")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        require(digest(target) == item["sha256"], "captured input hash mismatch")
        copied.add(name)
    require(not (destination / "plan.json").exists(), "input cannot occupy reserved plan.json")
    write_json(destination / "plan.json", plan)


def _status(result):
    top = result[0] if isinstance(result, tuple) and result else result
    if isinstance(top, dict) and top.get("schema") == "trainlab.experiment-diagnostics.v1":
        checks = top.get("coverage", [])
        require(
            isinstance(checks, list)
            and all(
                isinstance(row, dict)
                and row.get("status")
                in ("TESTED", "FAILED", "INCONCLUSIVE", "UNSUPPORTED", "NOT_RUN")
                for row in checks
            ),
            "invalid reused experiment diagnostic coverage",
        )
        statuses = [row["status"] for row in checks]
        if "FAILED" in statuses:
            return "FAILED"
        return (
            "TESTED"
            if statuses and all(status == "TESTED" for status in statuses)
            else "INCONCLUSIVE"
        )
    if isinstance(top, dict) and top.get("status") in ("FAILED", "INCONCLUSIVE", "TESTED"):
        return top["status"]
    if isinstance(top, dict) and top.get("status") in ("FAIL", "PASS", "UNKNOWN"):
        return {"FAIL": "FAILED", "PASS": "TESTED", "UNKNOWN": "INCONCLUSIVE"}[top["status"]]
    return "TESTED"


def run_plan(plan_path, output, *, allow_native=False, selected=None, render_figures=True):
    path, root = Path(plan_path).resolve(), Path(output)
    plan = validate_plan(read_json(path, limit=16 * 1024 * 1024))
    operations = {job["id"]: get_operation(job["operation"]) for job in plan["jobs"]}
    inputs = load_inputs(plan, path.parent)
    adapter = _load_adapter(plan, path.parent, allow_native=allow_native)
    require("analysis" not in adapter.operations, "analysis is a reserved adapter operation")
    ops = dict(adapter.operations)
    ops["analysis"] = lambda operation, args, kwargs: operation.function()(*args, **kwargs)
    adapter = Adapter(adapter.name, ops, adapter.state_semantics, adapter.asynchronous)
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    _capture_inputs(plan, path.parent, root)
    result_root = root / "results"
    result_root.mkdir(mode=0o700)
    implementation = implementation_identity()
    write_json(root / "implementation.json", implementation)
    results, checks, captures = {}, [], []

    def make_check(job, operation):
        def check(ctx):
            def callback(capability, normalize, context):
                def invoke(*args, **kwargs):
                    data = ctx.invoke(capability, *args, **context, **kwargs, phase="answer")
                    if normalize:
                        from .calibration import log_softmax

                        return log_softmax(np.asarray(data))
                    return data

                return invoke

            args = resolve(job.get("args", []), inputs, results, callback=callback)
            kwargs = resolve(job.get("kwargs", {}), inputs, results, callback=callback)
            if operation.mode == "native":
                result = operation.function()(ctx, *args, **kwargs)
            elif operation.mode == "capture":
                result = ctx.invoke(
                    operation.name.split(".", 1)[1], *args, **kwargs, phase="answer"
                )
            elif operation.mode == "callback":
                result = operation.function()(*args, **kwargs)
            else:
                result = ctx.invoke("analysis", operation, args, kwargs, phase="verify")
            encoded = encode_result(result, result_root, job["id"])
            # Both first-run and replay consumers see the same canonical value
            # (including mapping order and tuple-to-list JSON normalization).
            results[job["id"]] = decode_result(encoded, result_root)
            if operation.mode != "analysis" or list(_capabilities(job)):
                captures.append(job["id"])
            status = _status(result)
            return {
                "status": status,
                "summary": f"Observed {operation.name}; retained full result.",
                "metrics": {"result_written": 1},
            }

        return check

    for job in plan["jobs"]:
        operation = operations[job["id"]]
        requirements = set(operation.requires) | set(_capabilities(job))
        if job["operation"] == "interventions.component_lesions":
            conditions = job.get("kwargs", {}).get("conditions", {})
            if isinstance(conditions, dict) and any(
                isinstance(v, dict) for v in conditions.values()
            ):
                requirements.update(("edit_state", "select_state"))
        if operation.mode == "analysis":
            requirements.add("analysis")
        checks.append(
            Diagnostic(
                job["id"],
                "v1",
                tuple(sorted(requirements)),
                make_check(job, operation),
                job.get("scope", "Declared observed panel; no automatic scientific claim"),
            )
        )
    phases = (
        ("verify",) if all(op.mode == "analysis" for op in operations.values()) else ("answer",)
    )
    bench = Workbench(
        adapter, plan["identities"], root / "ledger", **plan["budget"], required_phases=phases
    )
    report = None
    try:
        report = bench.run(checks, selected=selected)
    finally:
        if report is None and (root / "ledger/report.json").is_file():
            report = read_json(root / "ledger/report.json", limit=16 * 1024 * 1024)
        coverage = report["coverage"] if report else []
        write_json(
            root / "captures.json",
            {
                "native_or_callback_jobs": captures,
                "result_jobs": sorted(results),
                "model_training_executed_by_suite": False,
            },
        )
        from .reporting import render

        render_plan = plan if render_figures else {**plan, "figures": []}
        summary = render(render_plan, results, coverage, root, inputs=inputs)
        state = report["state"] if report else "PARTIAL"
        if summary["figure_errors"]:
            state = "PARTIAL"
        pin = seal_bundle(
            root,
            plan_sha256=digest(root / "inputs/plan.json"),
            implementation=implementation,
            state=state,
        )
    return {
        "root": str(root.resolve()),
        "bundle_sha256": pin,
        "state": state,
        "figure_errors": summary["figure_errors"],
        "coverage": [
            {"name": row["name"], "status": row["status"], "reason": row["reason"]}
            for row in report["coverage"]
        ],
        "scientific_qualification": "NOT_QUALIFIED",
    }


def reanalyze(source, expected_sha256, output, *, render_figures=True):
    """Replay numerical analysis; native/callback captures are never executed."""
    source, root = Path(source), Path(output)
    bundle = verify_bundle(source, expected_sha256)
    current = implementation_identity()
    require(current == bundle["implementation"], "analysis implementation/runtime changed")
    saved_files = {item["path"]: item for item in bundle["files"]}
    require(
        saved_files["inputs/plan.json"]["sha256"] == bundle["plan_sha256"],
        "saved plan identity mismatch",
    )
    plan = validate_plan(pinned_json(source, saved_files["inputs/plan.json"]))
    inputs = load_inputs(plan, source / "inputs")
    recorded = pinned_json(source, saved_files["ledger/report.json"])
    by_id = {row["name"]: row for row in recorded["coverage"]}
    capture_doc = pinned_json(source, saved_files["captures.json"])
    captured = set(capture_doc["native_or_callback_jobs"])
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    results_root = root / "results"
    results_root.mkdir()
    results, comparisons, coverage = {}, [], []
    for job in plan["jobs"]:
        identity, operation = job["id"], get_operation(job["operation"])
        status = by_id[identity]
        if identity not in capture_doc["result_jobs"]:
            coverage.append(copy.deepcopy(status))
            continue
        saved = pinned_json(source, saved_files[f"results/{identity}.json"])["value"]
        needs_native = operation.mode != "analysis" or bool(list(_capabilities(job)))
        require(needs_native == (identity in captured), "capture provenance mismatch")
        if needs_native:
            result = decode_result(saved, source / "results")
            replay_kind = "REUSED_VERIFIED_CAPTURE"
        else:
            args = resolve(job.get("args", []), inputs, results)
            kwargs = resolve(job.get("kwargs", {}), inputs, results)
            result = operation.function()(*args, **kwargs)
            replay_kind = "RECOMPUTED_ANALYSIS"
        encoded = encode_result(result, results_root, identity)
        equal = canonical(encoded) == canonical(saved)
        comparisons.append({"id": identity, "kind": replay_kind, "byte_exact": equal})
        results[identity] = decode_result(encoded, results_root)
        coverage.append(
            {
                **status,
                "status": status["status"] if equal else "FAILED",
                "reason": replay_kind if equal else "NUMERICAL_REPLAY_MISMATCH",
            }
        )
    from .reporting import render

    render(
        plan if render_figures else {**plan, "figures": []}, results, coverage, root, inputs=inputs
    )
    result = {
        "schema": "trainlab.latent-reanalysis.v1",
        "source_bundle_sha256": expected_sha256,
        "comparisons": comparisons,
        "byte_exact": bool(comparisons) and all(row["byte_exact"] for row in comparisons),
        "analysis_jobs_recomputed": sum(
            row["kind"] == "RECOMPUTED_ANALYSIS" for row in comparisons
        ),
        "native_captures_reused": sum(
            row["kind"] == "REUSED_VERIFIED_CAPTURE" for row in comparisons
        ),
        "model_forwards": 0,
        "training_updates": 0,
        "timing_reruns": 0,
        "scope": "same-code saved-output reanalysis; not independent scientific replication",
    }
    write_json(root / "reanalysis.json", result)
    return result


def export_bundle(source, expected_sha256, destination):
    """Publish a verified private archive without exposing partial exports."""
    source, destination = Path(source).resolve(), Path(destination)
    doc = verify_bundle(source, expected_sha256)
    require(
        not destination.exists()
        and not destination.is_symlink()
        and not destination.resolve().is_relative_to(source),
        "export needs a new destination outside the source bundle",
    )
    names = [row["path"] for row in doc["files"]] + ["bundle.json", "SHA256SUMS"]
    expected_hashes = {row["path"]: row["sha256"] for row in doc["files"]}
    expected_sizes = {row["path"]: row["bytes"] for row in doc["files"]}
    expected_hashes["bundle.json"] = expected_sha256
    expected_sizes["bundle.json"] = (source / "bundle.json").stat().st_size
    checksums = "".join(f"{row['sha256']}  {row['path']}\n" for row in doc["files"]).encode()
    expected_hashes["SHA256SUMS"] = hashlib.sha256(checksums).hexdigest()
    expected_sizes["SHA256SUMS"] = len(checksums)
    require(
        len(names) <= MAX_EXPORT_FILES and sum(expected_sizes.values()) <= MAX_EXPORT_BYTES,
        "export exceeds supported file or byte limit",
    )
    temporary = None
    try:
        # Like the existing run-store backup, stage mode-600 bytes beside the
        # destination and publish with a no-overwrite hard link after verification.
        with NamedTemporaryFile(
            dir=destination.parent, prefix=".latent-export-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for name in sorted(names):
                    hasher, size = hashlib.sha256(), 0
                    with contained_file(source, name).open("rb") as input_stream:
                        with archive.open(name, "w") as output_stream:
                            while block := input_stream.read(65536):
                                size += len(block)
                                require(
                                    size <= expected_sizes[name],
                                    "exported content differs from the pinned evidence",
                                )
                                output_stream.write(block)
                                hasher.update(block)
                    require(
                        size == expected_sizes[name]
                        and hasher.hexdigest() == expected_hashes[name],
                        "exported content differs from the pinned evidence",
                    )
            stream.flush()
            os.fsync(stream.fileno())
        with zipfile.ZipFile(temporary) as archive:
            require(sorted(archive.namelist()) == sorted(names), "archive integrity mismatch")
            for name in names:
                hasher, size = hashlib.sha256(), 0
                with archive.open(name) as captured:
                    while block := captured.read(65536):
                        size += len(block)
                        require(size <= expected_sizes[name], "archive size mismatch")
                        hasher.update(block)
                require(
                    size == expected_sizes[name] and hasher.hexdigest() == expected_hashes[name],
                    "exported content differs from the pinned evidence",
                )
        archive_sha256 = digest(temporary)
        os.link(temporary, destination)
        if os.name == "posix":
            descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return {
            "path": str(destination.resolve()),
            "sha256": archive_sha256,
            "bundle_sha256": expected_sha256,
            "files": len(names),
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def worker(plan_path, *, allow_native=False):
    """Existing TrainLab command boundary; retain a portable evidence ZIP receipt."""
    require("TRAINLAB_OUTPUT_DIR" in os.environ, "worker requires the existing TrainLab runner")
    output = Path(os.environ["TRAINLAB_OUTPUT_DIR"])
    run = run_plan(plan_path, output / "latent", allow_native=allow_native)
    exported = export_bundle(
        output / "latent", run["bundle_sha256"], output / "latent-evidence.zip"
    )
    counts = {
        name: sum(row["status"] == name for row in run["coverage"])
        for name in ("TESTED", "FAILED", "INCONCLUSIVE", "UNSUPPORTED", "NOT_RUN")
    }
    write_json(output / "latent-receipt.json", {**run, "archive": exported})
    write_json(
        output / "metrics.json",
        {f"diagnostics_{key.lower()}": value for key, value in counts.items()},
    )
    return run
