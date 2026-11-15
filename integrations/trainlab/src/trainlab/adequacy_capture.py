"""Owned, bounded CPU classification capture around the native training observer.

Trusted local execution, not a sandbox or remote attestation. Only authorized
TRAIN exports are read; no Forge TEST release is opened by this adapter.
"""

from __future__ import annotations

import hashlib
import json
import platform
import random
import sys
from pathlib import Path
from time import perf_counter

from . import training_observer
from .prediction_artifacts import _bytes, _hash, _require, _text
from .research_adequacy import recipe_identity
from .runner import _constant, _finite, _pairs, contained_file, digest, read_json


def _state_hash(model):
    hasher = hashlib.sha256()
    for name, tensor in model.state_dict().items():
        hasher.update(_bytes([name, str(tensor.dtype), list(tensor.shape)]))
        # No NumPy dependency. Dense CPU tensors only, bounded by model admission.
        import torch

        hasher.update(bytes(tensor.detach().contiguous().view(torch.uint8).flatten().tolist()))
    return hasher.hexdigest()


def capture_training(
    config, input_root, *, data_file, producer_file, model, steps, batch_size, learning_rate, seed
):
    """Own SGD, sampling and observer calls; return (execution_receipt, capture_report).

    Supported model: exact Linear or Sequential of Linear/ReLU/Tanh (no subclasses,
    buffers, external hooks, dropout, custom forward, accelerator or mixed precision).
    TRAIN export rows use Forge Dataset.examples shape, not a caller-provided counter.
    """
    import torch

    _require(
        type(steps) is int
        and 1 <= steps <= 10000
        and type(batch_size) is int
        and 1 <= batch_size <= 1024
        and _finite(learning_rate)
        and 0 < learning_rate <= 1
        and type(seed) is int
        and 0 <= seed <= 2**32 - 1,
        "bounded capture regime required",
    )
    _require(
        type(config) is dict
        and type(config.get("inputs")) is list
        and len(set(config["inputs"])) == len(config["inputs"])
        and data_file in config["inputs"]
        and producer_file in config["inputs"]
        and type(config.get("seed")) is int
        and seed == config["seed"],
        "data and producer must be declared inputs",
    )
    root = Path(input_root).resolve()
    inputs = {name: digest(contained_file(root, name)) for name in config["inputs"]}
    pointer = config.get("research_adequacy")
    _require(
        type(pointer) is dict
        and pointer.get("file") in inputs
        and inputs[pointer["file"]] == pointer.get("sha256")
        and producer_file != pointer["file"]
        and data_file != pointer["file"],
        "capture requires a pinned research contract",
    )
    contract = read_json(contained_file(root, pointer["file"]))
    _require(
        contract.get("recipe_sha256") == recipe_identity(config)
        and contract.get("inputs") == {k: v for k, v in inputs.items() if k != pointer["file"]},
        "capture inputs or recipe differ from frozen contract",
    )
    document = read_json(contained_file(root, data_file))
    data_source = contained_file(root, data_file).read_bytes().decode("utf-8")
    _require(
        hashlib.sha256(data_source.encode("utf-8")).hexdigest() == inputs[data_file],
        "TRAIN export changed while capturing source",
    )
    _require(
        type(document) is dict
        and set(document)
        == {"schema", "split", "forge_manifest_sha256", "feature_field", "classes", "examples"}
        and document["schema"] == "trainlab.forge-train-export.v1"
        and document["split"] == "train"
        and _hash(document["forge_manifest_sha256"])
        and _text(document["feature_field"])
        and type(document["classes"]) is int
        and 2 <= document["classes"] <= 1000,
        "pinned TRAIN-only classification export required",
    )
    rows = document["examples"]
    _require(type(rows) is list and 1 <= len(rows) <= 10000, "bounded training rows required")
    vectors, labels, groups, identities = [], [], set(), set()
    for row in rows:
        _require(
            type(row) is dict
            and set(row) == {"record_id", "episode_id", "subject_id", "features", "target"}
            and all(_text(row[k]) for k in ("record_id", "episode_id", "subject_id"))
            and row["record_id"] not in identities
            and type(row["features"]) is dict
            and document["feature_field"] in row["features"]
            and type(row["target"]) is dict,
            "invalid or duplicate Forge training example",
        )
        vector, label = row["features"][document["feature_field"]], row["target"].get("value")
        _require(
            type(vector) is list
            and 1 <= len(vector) <= 1024
            and all(_finite(v) for v in vector)
            and type(label) is int
            and 0 <= label < document["classes"],
            "finite classification features/targets required",
        )
        _require(not vectors or len(vector) == len(vectors[0]), "inconsistent feature width")
        vectors.append(vector)
        labels.append(label)
        groups.add(row["subject_id"])
        identities.add(row["record_id"])
    _require(len(vectors) * len(vectors[0]) <= 1000000, "training tensor limit exceeded")
    allowed = (torch.nn.Linear, torch.nn.Sequential, torch.nn.ReLU, torch.nn.Tanh)
    _require(
        type(model) in (torch.nn.Linear, torch.nn.Sequential)
        and all(
            type(module) in allowed
            and not module._forward_hooks
            and not module._forward_pre_hooks
            and not module._backward_hooks
            and "forward" not in module.__dict__
            for module in model.modules()
        )
        and not list(model.buffers()),
        "unsupported model or pre-existing instrumentation",
    )
    params = list(model.parameters())
    _require(
        params
        and sum(p.numel() for p in params) <= 1000000
        and all(
            p.device.type == "cpu"
            and p.layout == torch.strided
            and p.dtype == torch.float32
            and p.requires_grad
            for p in params
        ),
        "dense float32 trainable CPU model required",
    )
    x, y = torch.tensor(vectors, dtype=torch.float32), torch.tensor(labels, dtype=torch.long)
    _require(torch.isfinite(x).all().item(), "features overflow float32")
    optimizer = torch.optim.SGD(params, lr=learning_rate)
    model.train()
    initial = _state_hash(model)
    architecture = [
        {"name": name, "type": type(module).__name__, "representation": repr(module)}
        for name, module in model.named_modules()
    ]
    rng = random.Random(seed)
    trace, batches, error = [], [], None
    sampled_groups = set()
    started = perf_counter()
    for step in range(steps):
        indices = [rng.randrange(len(rows)) for _ in range(batch_size)]
        sampled_groups.update(rows[i]["subject_id"] for i in indices)
        batches.append(hashlib.sha256(_bytes(indices)).hexdigest())
        try:
            observation = training_observer.train_step(
                model,
                optimizer,
                {"inputs": x[indices], "labels": y[indices], "mask": None},
                step=step,
                task="classification",
                classes=document["classes"],
            )
            trace.append(observation)
            if observation["status"] != "TESTED":
                break
        except Exception as exc:
            error = type(exc).__name__
            break
    elapsed = perf_counter() - started
    predictions, evaluation_error = [], None
    model.eval()
    try:
        with torch.no_grad():
            for offset in range(0, len(rows), batch_size):
                logits = model(x[offset : offset + batch_size])
                _require(
                    type(logits) is torch.Tensor
                    and logits.device.type == "cpu"
                    and logits.shape == (min(batch_size, len(rows) - offset), document["classes"])
                    and torch.isfinite(logits).all().item(),
                    "invalid final classification output",
                )
                predictions.extend(logits.argmax(dim=-1).tolist())
    except Exception as exc:
        evaluation_error = type(exc).__name__
    evaluation_complete = evaluation_error is None and len(predictions) == len(labels)
    accuracy = (
        sum(p == y for p, y in zip(predictions, labels)) / len(labels)
        if evaluation_complete
        else None
    )
    evaluation = {
        "schema": "trainlab.capture-classification.v1",
        "split": "train",
        "status": "COMPLETE" if evaluation_complete else "INCOMPLETE",
        "metric": "accuracy",
        "accuracy": accuracy,
        "predictions": predictions,
        "predictions_sha256": hashlib.sha256(_bytes(predictions)).hexdigest(),
        "targets_sha256": hashlib.sha256(_bytes(labels)).hexdigest(),
        "target_count": len(labels),
        "error_type": evaluation_error,
    }
    try:
        intact = all(digest(contained_file(root, name)) == pin for name, pin in inputs.items())
    except (OSError, ValueError):
        intact = False
    completed = (
        len(trace) == steps
        and error is None
        and intact
        and evaluation_complete
        and all(item["status"] == "TESTED" for item in trace)
    )
    observations = {
        "capture_complete": int(completed),
        "input_integrity": int(intact),
        "parameters": sum(p.numel() for p in params),
        "optimizer_updates": sum(
            item["observations"]["updated_parameters"] is not None for item in trace
        ),
        "successful_updates": sum(item["status"] == "TESTED" for item in trace),
        "changed_updates": sum(
            (item["observations"]["updated_parameters"] or 0) > 0 for item in trace
        ),
        "answer_exposures": sum(item["observations"]["active_targets"] for item in trace),
        "elapsed_training_seconds": elapsed,
        "training_groups": len(groups),
        "sampled_training_groups": len(sampled_groups),
        "training_rows": len(rows),
        "feature_width": len(vectors[0]),
        "classes": document["classes"],
        "learning_rate": learning_rate,
        "batch_size": batch_size,
        "seed": seed,
        "nonfinite_or_other_failed_steps": sum(item["status"] == "FAILED" for item in trace),
    }
    receipt = {
        "schema": "trainlab.execution-adequacy-observations.v1",
        "recipe_sha256": recipe_identity(config),
        "inputs": inputs,
        "producer": {"file": producer_file, "sha256": inputs[producer_file]},
        "observations": observations,
    }
    report = {
        "schema": "trainlab.adequacy-capture.v1",
        "status": "COMPLETE" if completed else "INCOMPLETE",
        "receipt": receipt,
        "requested_steps": steps,
        "error_type": error,
        "steps": trace,
        "evaluation": evaluation,
        "data_source": data_source,
        "batch_indices_sha256": batches,
        "regime": {
            "optimizer": "torch.optim.SGD",
            "learning_rate": learning_rate,
            "batch_size": batch_size,
            "seed": seed,
        },
        "receipt_sha256": hashlib.sha256(_bytes(receipt)).hexdigest(),
        "session_seconds": elapsed,
        "model": {
            "architecture": architecture,
            "parameters": [
                {"name": name, "shape": list(p.shape), "numel": p.numel()}
                for name, p in model.named_parameters()
            ],
            "initial_state_sha256": initial,
            "final_state_sha256": _state_hash(model),
        },
        "dataset": {
            "file": data_file,
            "sha256": inputs[data_file],
            "forge_manifest_sha256": document["forge_manifest_sha256"],
            "rows": len(rows),
            "groups": len(groups),
            "feature_width": len(vectors[0]),
            "classes": document["classes"],
            "split": "train",
            "lineage": "EXPORT_DECLARED_NOT_RELEASE_RECOMPUTED",
        },
        "runtime": {
            "python": sys.version,
            "platform": platform.platform(),
            "torch": str(torch.__version__),
            "torch_build": torch.__config__.show(),
            "observer_sha256": digest(Path(training_observer.__file__)),
            "capture_sha256": digest(Path(__file__)),
        },
        "scope": "Owned CPU float32 SGD classification loop; trusted in-process code. "
        "No arbitrary-framework instrumentation, restart, independent execution attestation, "
        "Forge export-lineage verification or scientific suitability guarantee.",
        "accounting_scope": (
            "Recorded native observer returns only; counters are lower bounds after an exception."
        ),
        "qualification": "NOT_QUALIFIED",
    }
    _bytes(report)  # Same bounded finite-JSON ceiling as replay verification.
    return receipt, report


def verify_capture(report, receipt, config, input_hashes):
    """Replay supported observer accounting, not authenticate the producing process."""
    _bytes(report)
    _bytes(receipt)
    _require(
        type(report) is dict
        and report.get("schema") == "trainlab.adequacy-capture.v1"
        and report.get("qualification") == "NOT_QUALIFIED"
        and report.get("receipt") == receipt
        and report.get("receipt_sha256") == hashlib.sha256(_bytes(receipt)).hexdigest()
        and receipt.get("schema") == "trainlab.execution-adequacy-observations.v1"
        and receipt.get("recipe_sha256") == recipe_identity(config)
        and receipt.get("inputs") == input_hashes
        and set(input_hashes) == set(config["inputs"])
        and all(_hash(v) for v in input_hashes.values()),
        "capture/receipt binding mismatch",
    )
    producer = receipt.get("producer")
    _require(
        type(producer) is dict
        and set(producer) == {"file", "sha256"}
        and producer["file"] in input_hashes
        and producer["sha256"] == input_hashes[producer["file"]],
        "capture producer mismatch",
    )
    data, model, runtime = report.get("dataset"), report.get("model"), report.get("runtime")
    _require(
        type(data) is dict
        and data.get("file") in input_hashes
        and data.get("sha256") == input_hashes[data["file"]]
        and data.get("split") == "train"
        and _hash(data.get("forge_manifest_sha256"))
        and data.get("lineage") == "EXPORT_DECLARED_NOT_RELEASE_RECOMPUTED"
        and all(
            type(data.get(k)) is int and data[k] > 0
            for k in ("rows", "groups", "feature_width", "classes")
        ),
        "capture dataset provenance mismatch",
    )
    _require(
        type(runtime) is dict
        and set(runtime)
        == {"python", "platform", "torch", "torch_build", "observer_sha256", "capture_sha256"}
        and all(_text(runtime.get(k)) for k in ("python", "platform", "torch"))
        and type(runtime.get("torch_build")) is str
        and 0 < len(runtime["torch_build"]) <= 16000
        and all(_hash(runtime.get(k)) for k in ("observer_sha256", "capture_sha256")),
        "capture runtime identity missing",
    )
    _require(
        type(model) is dict
        and all(_hash(model.get(k)) for k in ("initial_state_sha256", "final_state_sha256")),
        "captured model state identities missing",
    )
    parameters = model.get("parameters")
    _require(type(parameters) is list and parameters, "captured parameter metadata required")
    names, count = set(), 0
    for p in parameters:
        _require(
            type(p) is dict
            and set(p) == {"name", "shape", "numel"}
            and _text(p["name"])
            and p["name"] not in names
            and type(p["shape"]) is list
            and 1 <= len(p["shape"]) <= 2
            and all(type(n) is int and n > 0 for n in p["shape"]),
            "invalid captured parameter shape",
        )
        n = 1
        for d in p["shape"]:
            n *= d
        _require(type(p["numel"]) is int and p["numel"] == n, "parameter size mismatch")
        count += n
        names.add(p["name"])
    _require(count <= 1000000, "captured model bound exceeded")
    values, steps = receipt.get("observations"), report.get("steps")
    _require(
        type(values) is dict
        and all(_finite(v) for v in values.values())
        and type(steps) is list
        and len(steps) <= 10000
        and type(report.get("requested_steps")) is int
        and 1 <= report["requested_steps"] <= 10000
        and len(steps) <= report["requested_steps"],
        "invalid capture observations",
    )
    batch_size = values.get("batch_size")
    _require(type(batch_size) is int and 1 <= batch_size <= 1024, "invalid captured batch size")
    for i, step in enumerate(steps):
        _require(
            type(step) is dict
            and step.get("schema") == "trainlab.native-training-step.v1"
            and type(step.get("step")) is int
            and step["step"] == i
            and step.get("task") == "classification"
            and step.get("status") in ("TESTED", "FAILED", "INCONCLUSIVE")
            and step.get("scientific_qualification") == "NOT_QUALIFIED",
            "invalid observer step sequence",
        )
        obs = step.get("observations")
        _require(
            type(obs) is dict
            and type(obs.get("active_targets")) is int
            and obs["active_targets"] == batch_size
            and obs.get("trainable_parameters") == len(parameters)
            and obs.get("frozen_parameters") == 0,
            "observer exposure or parameter metadata mismatch",
        )
        updated = obs.get("updated_parameters")
        _require(
            updated is None or type(updated) is int and 0 <= updated <= len(parameters),
            "invalid observed update count",
        )
        if step["status"] == "TESTED":
            _require(
                step.get("first_anomaly") is None
                and updated is not None
                and updated > 0
                and _finite(obs.get("loss"))
                and not obs.get("missing_gradients")
                and obs.get("gradient_parameters") == len(parameters),
                "successful step contradicts observer evidence",
            )
        else:
            _require(i == len(steps) - 1, "capture continued after unsuccessful step")
    _require(
        values.get("input_integrity") in (0, 1)
        and _finite(report.get("session_seconds"))
        and report["session_seconds"] >= 0,
        "invalid capture integrity/time",
    )
    evaluation = report.get("evaluation")
    _require(
        type(evaluation) is dict
        and set(evaluation)
        == {
            "schema",
            "split",
            "status",
            "metric",
            "accuracy",
            "predictions",
            "predictions_sha256",
            "targets_sha256",
            "target_count",
            "error_type",
        }
        and evaluation["schema"] == "trainlab.capture-classification.v1"
        and evaluation["split"] == "train"
        and evaluation["metric"] == "accuracy"
        and evaluation["status"] in ("COMPLETE", "INCOMPLETE")
        and type(evaluation["predictions"]) is list
        and all(
            type(p) is int and 0 <= p < data.get("classes", 0) for p in evaluation["predictions"]
        )
        and evaluation["predictions_sha256"]
        == hashlib.sha256(_bytes(evaluation["predictions"])).hexdigest()
        and _hash(evaluation["targets_sha256"])
        and type(evaluation["target_count"]) is int
        and evaluation["target_count"] == data.get("rows"),
        "invalid captured classification evidence",
    )
    evaluation_complete = (
        evaluation["error_type"] is None
        and len(evaluation["predictions"]) == evaluation["target_count"]
    )
    _require(
        evaluation["status"] == ("COMPLETE" if evaluation_complete else "INCOMPLETE")
        and (
            _finite(evaluation["accuracy"]) and 0 <= evaluation["accuracy"] <= 1
            if evaluation_complete
            else evaluation["accuracy"] is None
        ),
        "evaluation completion contradicts predictions",
    )
    metrics = {}
    _require(type(report.get("data_source")) is str, "retained TRAIN export source required")
    retained_data = report["data_source"].encode("utf-8")
    data_bytes = retained_data
    if data_bytes is not None:
        _require(
            type(data_bytes) is bytes
            and len(data_bytes) <= 1024 * 1024
            and hashlib.sha256(data_bytes).hexdigest() == data["sha256"],
            "rescore requires exact frozen TRAIN export bytes",
        )
        document = json.loads(data_bytes, object_pairs_hook=_pairs, parse_constant=_constant)
        _require(
            type(document) is dict
            and set(document)
            == {"schema", "split", "forge_manifest_sha256", "feature_field", "classes", "examples"}
            and document.get("schema") == "trainlab.forge-train-export.v1"
            and _text(document.get("feature_field"))
            and document.get("split") == "train"
            and type(document.get("examples")) is list
            and len(document["examples"]) == data["rows"]
            and document.get("forge_manifest_sha256") == data["forge_manifest_sha256"]
            and document.get("classes") == data["classes"],
            "rescore export identity mismatch",
        )
        labels, subjects, records, subject_order = [], set(), set(), []
        for row in document["examples"]:
            _require(
                type(row) is dict
                and set(row) == {"record_id", "episode_id", "subject_id", "features", "target"}
                and _text(row.get("episode_id"))
                and type(row.get("target")) is dict
                and type(row["target"].get("value")) is int
                and 0 <= row["target"]["value"] < data["classes"],
                "invalid rescore target",
            )
            _require(
                _text(row.get("subject_id"))
                and _text(row.get("record_id"))
                and row["record_id"] not in records
                and type(row.get("features")) is dict
                and type(row["features"].get(document.get("feature_field"))) is list
                and len(row["features"][document["feature_field"]]) == data["feature_width"]
                and all(_finite(v) for v in row["features"][document["feature_field"]]),
                "rescore row or feature structure mismatch",
            )
            subjects.add(row["subject_id"])
            subject_order.append(row["subject_id"])
            records.add(row["record_id"])
            labels.append(row["target"]["value"])
        _require(len(subjects) == data["groups"], "capture group count differs from source")
        _require(
            hashlib.sha256(_bytes(labels)).hexdigest() == evaluation["targets_sha256"],
            "evaluation targets differ from frozen TRAIN export",
        )
        if evaluation_complete:
            accuracy = sum(p == y for p, y in zip(evaluation["predictions"], labels)) / len(labels)
            _require(
                accuracy == evaluation["accuracy"], "reported accuracy contradicts predictions"
            )
            metrics["accuracy"] = accuracy
    complete = (
        len(steps) == report["requested_steps"]
        and report.get("error_type") is None
        and evaluation_complete
        and values["input_integrity"] == 1
        and all(s["status"] == "TESTED" for s in steps)
    )
    expected = {
        "capture_complete": int(complete),
        "parameters": count,
        "optimizer_updates": sum(
            s["observations"]["updated_parameters"] is not None for s in steps
        ),
        "successful_updates": sum(s["status"] == "TESTED" for s in steps),
        "changed_updates": sum((s["observations"]["updated_parameters"] or 0) > 0 for s in steps),
        "answer_exposures": len(steps) * batch_size,
        "elapsed_training_seconds": report["session_seconds"],
        "nonfinite_or_other_failed_steps": sum(s["status"] == "FAILED" for s in steps),
    }
    _require(
        all(type(values.get(k)) is type(v) and values[k] == v for k, v in expected.items())
        and report.get("status") == ("COMPLETE" if complete else "INCOMPLETE"),
        "capture aggregate accounting changed",
    )
    regime = report.get("regime")
    _require(
        type(regime) is dict
        and set(regime) == {"optimizer", "learning_rate", "batch_size", "seed"}
        and regime["optimizer"] == "torch.optim.SGD"
        and type(regime["seed"]) is int
        and 0 <= regime["seed"] <= 2**32 - 1
        and type(config.get("seed")) is int
        and regime["seed"] == config["seed"]
        and _finite(regime["learning_rate"])
        and 0 < regime["learning_rate"] <= 1
        and all(values.get(k) == regime[k] for k in ("seed", "batch_size", "learning_rate")),
        "capture regime accounting changed",
    )
    for source, target in [
        ("rows", "training_rows"),
        ("groups", "training_groups"),
        ("feature_width", "feature_width"),
        ("classes", "classes"),
    ]:
        _require(
            type(data.get(source)) is int
            and data[source] > 0
            and values.get(target) == data[source],
            "capture dataset accounting changed",
        )
    batches = report.get("batch_indices_sha256")
    _require(
        type(batches) is list
        and len(batches) == len(steps) + int(report.get("error_type") is not None)
        and len(batches) <= report["requested_steps"],
        "capture attempted-batch count changed",
    )
    rng = random.Random(regime["seed"])
    expected_batches, sampled = [], set()
    for _ in batches:
        indices = [rng.randrange(data["rows"]) for _ in range(batch_size)]
        expected_batches.append(hashlib.sha256(_bytes(indices)).hexdigest())
        sampled.update(subject_order[i] for i in indices)
    _require(
        values.get("sampled_training_groups") == len(sampled),
        "sampled group count differs from actual schedule",
    )
    _require(batches == expected_batches, "captured sampler schedule changed")
    replay = {
        "recipe_sha256": recipe_identity(config),
        "inputs": input_hashes,
        "producer": producer,
        "dataset": data,
        "model": model,
        "regime": regime,
        "runtime": runtime,
        "batches": batches,
        "steps": steps,
        "requested_steps": report["requested_steps"],
        "error_type": report.get("error_type"),
        "evaluation": evaluation,
        "observations": {k: v for k, v in values.items() if k != "elapsed_training_seconds"},
    }
    return {
        "valid": True,
        "replay_sha256": hashlib.sha256(_bytes(replay)).hexdigest(),
        "status": "VERIFIED_COMPLETE" if complete else "INCOMPLETE",
        "admissible": int(complete and "accuracy" in metrics),
        "metrics": metrics,
        "metric_scope": "TRAIN_EXPORT_ONLY",
        "qualification": "NOT_QUALIFIED",
        "scope": "Recomputed supported synchronous CPU observer accounting; "
        "producer process authenticity and export lineage are not attested.",
    }
