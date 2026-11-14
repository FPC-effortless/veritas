"""Optional native training observation and frozen validation slice checks."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from copy import deepcopy

from .experiment_diagnostics import _number
from .prediction_artifacts import _bytes, _hash, _require, _text


def train_step(
    model, optimizer, batch, *, step, task, classes, ignore_index=-100, module_names=None
):
    """Execute one trusted synchronous CPU dense PyTorch cross-entropy step.

    Captures first observed activation, gradient or parameter anomaly. It owns
    zero_grad and the one optimizer.step. No loss scaling or gradient accumulation.
    """
    import torch

    from .pytorch import _modules, _tensors

    _require(type(step) is int and 0 <= step <= 10**9, "invalid step")
    _require(
        task in ("classification", "next_token")
        and type(ignore_index) is int
        and -(2**63) <= ignore_index < 2**63,
        "unsupported training task",
    )
    tensors = (torch.Tensor,)
    _require(
        type(batch) is dict
        and set(batch) == {"inputs", "labels", "mask"}
        and all(isinstance(batch[k], tensors) for k in ("inputs", "labels"))
        and (batch["mask"] is None or isinstance(batch["mask"], tensors)),
        "tensor inputs, labels and optional mask required",
    )
    inputs, labels, mask = batch["inputs"], batch["labels"], batch["mask"]
    used_tensors = [inputs, labels] + ([mask] if mask is not None else [])
    _require(
        all(
            t.device.type == "cpu" and t.layout == torch.strided and 0 < t.numel() <= 1000000
            for t in used_tensors
        )
        and labels.dtype == torch.long,
        "bounded dense CPU batch required",
    )
    if task == "classification":
        _require(
            inputs.ndim >= 2
            and labels.ndim == 1
            and inputs.shape[0] == labels.shape[0]
            and mask is None,
            "classification requires [batch, ...] and [batch]",
        )
    else:
        _require(
            inputs.dtype == torch.long
            and inputs.ndim == 2
            and (inputs >= 0).all().item()
            and inputs.shape == labels.shape
            and inputs.shape[1] >= 2
            and mask is not None
            and mask.dtype == torch.bool
            and mask.shape == labels.shape
            and not mask[:, -1].any().item()
            and torch.equal(labels[~mask], torch.full_like(labels[~mask], ignore_index))
            and torch.equal(labels[:, :-1][mask[:, :-1]], inputs[:, 1:][mask[:, :-1]]),
            "next-token labels must be shifted and masked",
        )
    active = labels != ignore_index
    _require(active.any().item(), "batch has no observed targets")
    if task == "classification":
        _require(active.all().item(), "classification does not accept ignored labels")
    else:
        _require(torch.equal(active, mask), "mask and ignored target positions differ")
    _require(
        type(classes) is int and 2 <= classes <= 1000000, "declared class/vocabulary count required"
    )
    _require(
        ((labels[active] >= 0) & (labels[active] < classes)).all().item(),
        "target outside declared vocabulary",
    )

    named = list(model.named_parameters())
    params = [(name, p) for name, p in named if p.requires_grad]
    optimizer_ids = [id(p) for group in optimizer.param_groups for p in group["params"]]
    all_ids = {id(p) for _, p in named}
    _require(
        params
        and {id(p) for _, p in params} <= set(optimizer_ids)
        and set(optimizer_ids) <= all_ids
        and len(optimizer_ids) == len(set(optimizer_ids))
        and sum(p.numel() for _, p in named) <= 1000000
        and all(p.device.type == "cpu" and p.layout == torch.strided for _, p in named),
        "bounded dense model and matching optimizer required",
    )
    selected = _modules(model, module_names)
    before = {name: p.detach().clone() for name, p in params}
    first = None
    observations = {
        "outputs": 0,
        "outputs_by_module": dict.fromkeys((name for name, _ in selected), 0),
        "gradient_parameters": 0,
        "missing_gradients": [],
        "updated_parameters": None,
        "trainable_parameters": len(params),
        "frozen_parameters": len(named) - len(params),
        "loss": None,
        "active_targets": int(active.sum().item()),
    }

    def anomaly(kind, location):
        nonlocal first
        if first is None:
            first = {"step": step, "kind": kind, "location": location}

    def finite_tensor(tensor):
        return (
            tensor.layout == torch.strided
            and tensor.numel() > 0
            and (torch.isfinite(tensor.detach()).all().item())
        )

    def hook(name):
        def inspect(_module, _args, output):
            for item in _tensors(output):
                observations["outputs"] += 1
                observations["outputs_by_module"][name] += 1
                if not finite_tensor(item):
                    anomaly("NONFINITE_OR_UNSUPPORTED_ACTIVATION", name)

        return inspect

    def gradient_hook(name):
        def inspect(gradient):
            if not finite_tensor(gradient):
                anomaly("NONFINITE_OR_UNSUPPORTED_GRADIENT", name)

        return inspect

    handles = []
    outcome = "INCONCLUSIVE"
    try:
        for name, parameter in named:
            if not finite_tensor(parameter):
                anomaly("NONFINITE_OR_UNSUPPORTED_PARAMETER", name)
        if first is None:
            for name, module in selected:
                handles.append(module.register_forward_hook(hook(name)))
            for name, parameter in params:
                handles.append(parameter.register_hook(gradient_hook(name)))
            optimizer.zero_grad(set_to_none=True)
            result = model(inputs)
            _require(
                isinstance(result, torch.Tensor)
                and result.layout == torch.strided
                and result.device.type == "cpu"
                and result.is_floating_point()
                and result.shape[:-1] == labels.shape
                and result.shape[-1] == classes
                and result.numel() <= 2000000,
                "unexpected logits shape or type",
            )
            if not finite_tensor(result):
                anomaly("NONFINITE_LOGITS", "<root>")
            if first is None:
                loss = torch.nn.functional.cross_entropy(result[active], labels[active])
                if not finite_tensor(loss):
                    anomaly("NONFINITE_LOSS", "cross_entropy")
                else:
                    observations["loss"] = float(loss.detach().item())
                    if loss.requires_grad:
                        loss.backward()
                    for name, parameter in params:
                        if parameter.grad is None:
                            observations["missing_gradients"].append(name)
                            anomaly("MISSING_GRADIENT", name)
                        else:
                            observations["gradient_parameters"] += 1
                            if not finite_tensor(parameter.grad):
                                anomaly("NONFINITE_OR_UNSUPPORTED_GRADIENT", name)
                    if first is None:
                        optimizer.step()
                        for name, parameter in params:
                            if not finite_tensor(parameter):
                                anomaly("NONFINITE_PARAMETER_AFTER_UPDATE", name)
                        observations["updated_parameters"] = sum(
                            not torch.equal(p.detach(), before[name]) for name, p in params
                        )
        if observations["updated_parameters"] == 0:
            anomaly("UNCHANGED_PARAMETERS", "optimizer.step")
        outcome = (
            "FAILED"
            if first
            else "TESTED"
            if (observations["outputs"] and observations["updated_parameters"] is not None)
            else "INCONCLUSIVE"
        )
    finally:
        for handle in handles:
            handle.remove()
    return {
        "schema": "trainlab.native-training-step.v1",
        "status": outcome,
        "task": task,
        "step": step,
        "first_anomaly": first,
        "observations": observations,
        "unchanged_update": observations["updated_parameters"] == 0,
        "scope": (
            "One CPU step. Selected forward outputs and parameter gradients only. "
            "No intermediate gradients, kernels, scaling, accumulation or distributed traces."
        ),
        "scientific_qualification": "NOT_QUALIFIED",
    }


def freeze_slices(rows, *, acquired_score, max_regression):
    _bytes(rows)
    _require(type(rows) is list and 1 <= len(rows) <= 2000, "bounded labeled panel required")
    seen = set()
    for row in rows:
        _require(
            type(row) is dict
            and set(row) == {"id", "slice", "label"}
            and all(_text(row[key]) for key in row)
            and row["id"] not in seen,
            "invalid or duplicate slice panel row",
        )
        seen.add(row["id"])
    _require(
        _number(acquired_score, 0, 1) and _number(max_regression, 0, 1),
        "frozen acquisition and regression thresholds required",
    )
    panel = {
        "rows": deepcopy(rows),
        "acquired_score": acquired_score,
        "max_regression": max_regression,
    }
    return {"panel": panel, "panel_sha256": hashlib.sha256(_bytes(panel)).hexdigest()}


def slice_trajectory(panel, checkpoints, *, panel_sha256, expected_steps):
    """Score each checkpoint against one predeclared labeled panel."""
    _require(
        type(panel) is dict
        and set(panel) == {"rows", "acquired_score", "max_regression"}
        and _hash(panel_sha256)
        and hashlib.sha256(_bytes(panel)).hexdigest() == panel_sha256,
        "validation panel changed",
    )
    freeze_slices(**panel)
    _bytes([checkpoints, expected_steps])
    _require(
        type(expected_steps) is list
        and 1 <= len(expected_steps) <= 128
        and all(type(step) is int and 0 <= step <= 10**9 for step in expected_steps)
        and expected_steps == sorted(set(expected_steps)),
        "invalid checkpoint steps",
    )
    _require(
        type(checkpoints) is list and len(checkpoints) <= len(expected_steps),
        "bounded checkpoint observations required",
    )
    labels = {row["id"]: row for row in panel["rows"]}
    grouped = defaultdict(list)
    for row in labels.values():
        grouped[row["slice"]].append(row["id"])
    lookup = {}
    for check in checkpoints:
        _require(
            type(check) is dict
            and set(check) == {"step", "predictions"}
            and type(check["step"]) is int
            and check["step"] in expected_steps
            and check["step"] not in lookup
            and type(check["predictions"]) is dict
            and check["predictions"].keys() <= labels.keys()
            and all(v is None or _text(v) for v in check["predictions"].values()),
            "invalid or duplicate checkpoint observations",
        )
        lookup[check["step"]] = check["predictions"]
    result, complete, regression = {}, True, False
    for name, ids in grouped.items():
        points, best_hits, acquired, damaged = [], None, None, None
        for step in expected_steps:
            predictions = lookup.get(step, {})
            known = [i for i in ids if predictions.get(i) is not None]
            hits = sum(predictions[i] == labels[i]["label"] for i in known)
            score = None
            if len(known) != len(ids):
                complete = False
            else:
                score = hits / len(ids)
                if (
                    best_hits is not None
                    and (best_hits - hits) / len(ids) > panel["max_regression"]
                    and damaged is None
                ):
                    damaged = step
                    regression = True
                if score >= panel["acquired_score"]:
                    acquired = step if acquired is None else acquired
                    best_hits = hits if best_hits is None else max(hits, best_hits)
            points.append({"step": step, "accuracy": score, "observed": len(known)})
        result[name] = {
            "rows": len(ids),
            "points": points,
            "first_acquired": acquired,
            "first_regression": damaged,
        }
    return {
        "schema": "trainlab.slice-trajectory.v1",
        "status": "FAILED" if regression else "TESTED" if complete else "INCONCLUSIVE",
        "panel_sha256": panel_sha256,
        "slices": result,
        "complete": complete,
        "scope": "Declared data and slice trajectories. No causal forgetting conclusion.",
        "scientific_qualification": "NOT_QUALIFIED",
    }
