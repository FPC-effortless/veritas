"""Matched learning specifications and audits; execution uses TrainLab's runner.

This module does not implement an optimizer or load models. Trusted training
commands consume the frozen recipe and emit update evidence for these checks.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from ..runner import LabError, contained_file, load_config, read_json, run_experiment


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as error:
        raise LabError("recipe metadata must be finite JSON values") from error


def _number(value, minimum=0):
    return type(value) in (int, float) and math.isfinite(value) and value >= minimum


def training_recipe(
    *,
    name,
    parent_checkpoint_sha256,
    seed,
    updates,
    task_schedule_sha256=None,
    language_schedule_sha256=None,
    task_targets_per_update=128,
    language_targets_per_update=0,
    task_weight=1.0,
    language_weight=0.0,
    optimizer=None,
    learning_rate_schedule=None,
    clip_norm=1.0,
    reset_policy="per_sequence",
    snapshot_updates=None,
):
    """Freeze a fresh-optimizer, fixed-final continuation recipe and its identity."""
    if (
        not isinstance(name, str)
        or not name.strip()
        or len(name) > 200
        or not _hash(parent_checkpoint_sha256)
    ):
        raise LabError("recipe needs a bounded name and exact parent checkpoint SHA256")
    if (
        type(seed) is not int
        or not 0 <= seed < 2**32
        or type(updates) is not int
        or not 1 <= updates <= 10_000_000
    ):
        raise LabError("invalid fixed seed or update budget")
    if any(
        type(n) is not int or n < 0 for n in (task_targets_per_update, language_targets_per_update)
    ):
        raise LabError("target budgets must be nonnegative integers")
    if (
        not all(_number(w) for w in (task_weight, language_weight))
        or task_weight + language_weight <= 0
    ):
        raise LabError("at least one finite positive objective weight is required")
    for weight, targets, schedule in (
        (task_weight, task_targets_per_update, task_schedule_sha256),
        (language_weight, language_targets_per_update, language_schedule_sha256),
    ):
        if weight > 0 and (targets == 0 or not _hash(schedule)):
            raise LabError("active objectives require labels and a pinned schedule")
        if weight == 0 and (targets != 0 or schedule is not None):
            raise LabError("inactive objectives cannot declare consumed labels or schedules")
    if (
        not _number(clip_norm)
        or clip_norm <= 0
        or reset_policy not in ("per_sequence", "explicit_state")
    ):
        raise LabError("declare a positive clip norm and supported state reset policy")
    optimizer = copy.deepcopy(
        optimizer
        if optimizer is not None
        else {
            "name": "AdamW",
            "learning_rate": 0.003,
            "betas": [0.9, 0.999],
            "eps": 1e-8,
            "weight_decay": 0.01,
        }
    )
    schedule = copy.deepcopy(
        learning_rate_schedule if learning_rate_schedule is not None else {"kind": "constant"}
    )
    if (
        not isinstance(optimizer, dict)
        or not optimizer.get("name")
        or not isinstance(schedule, dict)
        or not schedule.get("kind")
    ):
        raise LabError("optimizer and learning-rate schedule require named specifications")
    for key in ("learning_rate", "lr", "eps"):
        if key in optimizer and (not _number(optimizer[key]) or optimizer[key] <= 0):
            raise LabError("optimizer learning rate and epsilon must be finite positive numbers")
    if "weight_decay" in optimizer and not _number(optimizer["weight_decay"]):
        raise LabError("optimizer weight decay must be finite and nonnegative")
    if "betas" in optimizer and (
        not isinstance(optimizer["betas"], (list, tuple))
        or len(optimizer["betas"]) != 2
        or any(not _number(v) or v >= 1 for v in optimizer["betas"])
    ):
        raise LabError("optimizer betas must be two finite numbers in [0,1)")
    _canonical(optimizer)
    _canonical(schedule)
    snapshots = (0, 1, updates) if snapshot_updates is None else snapshot_updates
    if (
        not isinstance(snapshots, (list, tuple))
        or not snapshots
        or any(type(n) is not int or not 0 <= n <= updates for n in snapshots)
    ):
        raise LabError("snapshot updates must be a bounded integer list")
    snapshots = sorted(set(snapshots))
    if snapshots[0] != 0 or snapshots[-1] != updates:
        raise LabError("snapshot updates must include original and fixed-final states")
    recipe = {
        "schema": "trainlab.latent-learning.v1",
        "name": name,
        "parent_checkpoint_sha256": parent_checkpoint_sha256,
        "seed": seed,
        "updates": updates,
        "objective": {
            "task_weight": task_weight,
            "language_weight": language_weight,
            "reduction": "sum of weighted mean losses; no implicit halving",
        },
        "task_schedule_sha256": task_schedule_sha256,
        "language_schedule_sha256": language_schedule_sha256,
        "task_targets_per_update": task_targets_per_update,
        "language_targets_per_update": language_targets_per_update,
        "budget": {
            "optimizer_updates": updates,
            "task_targets": updates * task_targets_per_update,
            "language_targets": updates * language_targets_per_update,
        },
        "optimizer": optimizer,
        "optimizer_fresh": True,
        "learning_rate_schedule": schedule,
        "clip_norm": clip_norm,
        "reset_policy": reset_policy,
        "snapshot_updates": snapshots,
        "checkpoint_selection": "fixed_final",
        "scope": "matched declared exposure budgets; equal compute is not implied",
    }
    recipe["recipe_sha256"] = hashlib.sha256(_canonical(recipe)).hexdigest()
    return recipe


def _validate_recipe(recipe):
    if not isinstance(recipe, dict) or recipe.get("schema") != "trainlab.latent-learning.v1":
        raise LabError("unsupported latent learning recipe")
    payload = {key: value for key, value in recipe.items() if key != "recipe_sha256"}
    if recipe.get("recipe_sha256") != hashlib.sha256(_canonical(payload)).hexdigest():
        raise LabError("frozen learning recipe identity differs")
    required = (
        "name",
        "parent_checkpoint_sha256",
        "seed",
        "updates",
        "task_schedule_sha256",
        "language_schedule_sha256",
        "task_targets_per_update",
        "language_targets_per_update",
        "optimizer",
        "learning_rate_schedule",
        "clip_norm",
        "reset_policy",
        "snapshot_updates",
    )
    try:
        rebuilt = training_recipe(
            **{key: recipe[key] for key in required},
            task_weight=recipe["objective"]["task_weight"],
            language_weight=recipe["objective"]["language_weight"],
        )
    except (KeyError, TypeError) as error:
        raise LabError("learning recipe has missing or invalid fields") from error
    if rebuilt != recipe:
        raise LabError("learning recipe contains inconsistent fields or budgets")


def audit_matched_recipes(
    left,
    right,
    *,
    match_task_schedule=True,
    match_language_schedule=False,
    equal_budgets=("task_targets",),
):
    """Check only declared matching invariants; objective effects remain explicit."""
    _validate_recipe(left)
    _validate_recipe(right)
    keys = [
        "parent_checkpoint_sha256",
        "seed",
        "updates",
        "optimizer",
        "optimizer_fresh",
        "learning_rate_schedule",
        "clip_norm",
        "reset_policy",
        "snapshot_updates",
        "checkpoint_selection",
    ]
    if match_task_schedule:
        keys.append("task_schedule_sha256")
    if match_language_schedule:
        keys.append("language_schedule_sha256")
    checks = {key: left[key] == right[key] for key in keys}
    unavailable = [
        key
        for key in keys
        if key.endswith("schedule_sha256") and (left[key] is None or right[key] is None)
    ]
    for budget in equal_budgets:
        if budget not in left["budget"] or budget not in right["budget"]:
            raise LabError("unknown matching budget")
        checks["budget." + budget] = left["budget"][budget] == right["budget"][budget]
    return {
        "status": "UNKNOWN" if unavailable else "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "unavailable": unavailable,
        "left_recipe_sha256": left["recipe_sha256"],
        "right_recipe_sha256": right["recipe_sha256"],
        "left_objective": left["objective"],
        "right_objective": right["objective"],
        "left_budget": left["budget"],
        "right_budget": right["budget"],
        "scope": "matched declared recipe; execution and equal compute are not established",
    }


def audit_seed_panel(seeds, required_seeds):
    if (
        not isinstance(seeds, (list, tuple))
        or not isinstance(required_seeds, (list, tuple))
        or not required_seeds
    ):
        raise LabError("seed panel requires explicit observed and required lists")
    if any(type(v) is not int or not 0 <= v < 2**32 for v in (*seeds, *required_seeds)) or len(
        set(required_seeds)
    ) != len(required_seeds):
        raise LabError("invalid or duplicate required seeds")
    duplicates = sorted(seed for seed in set(seeds) if seeds.count(seed) > 1)
    missing, extra = (
        sorted(set(required_seeds) - set(seeds)),
        sorted(set(seeds) - set(required_seeds)),
    )
    return {
        "status": "PASS" if not (duplicates or missing or extra) else "FAIL",
        "required_seeds": list(required_seeds),
        "observed_seeds": list(seeds),
        "missing": missing,
        "extra": extra,
        "duplicates": duplicates,
        "scope": "fixed seeds; no seed-population uncertainty inferred",
    }


def audit_training_events(
    recipe,
    events,
    *,
    expected_batch_hashes=None,
    observed_seed=None,
    optimizer_fresh=None,
    reset_policy=None,
    source_hashes_before=None,
    source_hashes_after=None,
):
    """Validate update order, losses, finite gradients, clipping and matched batches.

    Every event declares update, losses (task/language), preclip_gradient_norm,
    clipped, gradients_finite, weights_finite and optional schedule batch hashes.
    Missing provenance is UNKNOWN, never an inferred successful scientific run.
    """
    _validate_recipe(recipe)
    if not isinstance(events, list) or len(events) > recipe["updates"]:
        raise LabError("events must be a bounded update list")
    failures, missing = [], []
    if len(events) != recipe["updates"]:
        missing.append("fixed update budget incomplete")
    for expected, event in enumerate(events, 1):
        if (
            not isinstance(event, dict)
            or type(event.get("update")) is not int
            or event["update"] != expected
        ):
            raise LabError("training events are duplicated, skipped, or out of order")
        losses = event.get("losses")
        if not isinstance(losses, dict):
            raise LabError("training event requires named objective losses")
        if set(losses) - {"task", "language"}:
            raise LabError("training event contains undeclared objective components")
        combined = 0.0
        for component in ("task", "language"):
            weight = recipe["objective"][component + "_weight"]
            if weight:
                if not _number(losses.get(component)):
                    raise LabError("active objective loss is missing, nonfinite, or negative")
                combined += weight * losses[component]
            elif component in losses:
                raise LabError("inactive objective appears in training event")
        if "combined_objective" not in event:
            missing.append(f"update {expected}: combined objective")
        elif not _number(event["combined_objective"]) or not math.isclose(
            event["combined_objective"], combined, rel_tol=1e-6, abs_tol=1e-8
        ):
            failures.append(f"update {expected}: combined objective differs")
        norm = event.get("preclip_gradient_norm")
        if not _number(norm):
            raise LabError("preclip gradient norm must be finite and nonnegative")
        if type(event.get("clipped")) is not bool or event["clipped"] != (
            norm > recipe["clip_norm"]
        ):
            failures.append(f"update {expected}: clipping flag differs")
        for name in ("gradients_finite", "weights_finite"):
            if event.get(name) is not True:
                failures.append(f"update {expected}: {name} not verified")
    for name, actual, expected in (
        ("seed", observed_seed, recipe["seed"]),
        ("optimizer_fresh", optimizer_fresh, True),
        ("reset_policy", reset_policy, recipe["reset_policy"]),
    ):
        if actual is None:
            missing.append(name)
        elif type(actual) is not type(expected) or actual != expected:
            failures.append(name + " differs")
    if expected_batch_hashes is None:
        missing.append("schedule batch identities")
    else:
        if not isinstance(expected_batch_hashes, dict):
            raise LabError("expected batch hashes require a component mapping")
        for component in ("task", "language"):
            if not recipe["objective"][component + "_weight"]:
                continue
            hashes = expected_batch_hashes.get(component)
            if (
                not isinstance(hashes, (list, tuple))
                or len(hashes) != recipe["updates"]
                or not all(_hash(v) for v in hashes)
            ):
                raise LabError("expected batch hashes must cover the exact active schedule")
            for event, expected_hash in zip(events, hashes):
                if event.get(component + "_batch_sha256") != expected_hash:
                    failures.append(f"update {event['update']}: {component} schedule differs")
    if source_hashes_before is None or source_hashes_after is None:
        missing.append("source preservation")
    elif (
        not isinstance(source_hashes_before, dict)
        or not source_hashes_before
        or not all(_hash(v) for v in source_hashes_before.values())
    ):
        raise LabError("source preservation needs a nonempty path/hash inventory")
    elif source_hashes_before != source_hashes_after:
        failures.append("source inputs or parent checkpoints changed")
    return {
        "status": "FAIL" if failures else "UNKNOWN" if missing else "PASS",
        "recipe_sha256": recipe["recipe_sha256"],
        "observed_updates": len(events),
        "planned_updates": recipe["updates"],
        "failures": failures,
        "missing_evidence": missing,
        "scientific_qualification": "NOT_QUALIFIED",
        "scope": "training implementation evidence only",
    }


def _exact(a, b):
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        if (
            not isinstance(a, np.ndarray)
            or not isinstance(b, np.ndarray)
            or a.dtype != b.dtype
            or a.shape != b.shape
        ):
            return False
        if a.dtype.kind in "biufc" and (not np.isfinite(a).all() or not np.isfinite(b).all()):
            return False
        return np.array_equal(a, b)
    if type(a) is not type(b):
        return False
    if isinstance(a, np.generic):
        return _exact(a.item(), b.item())
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_exact(a[key], b[key]) for key in a)
    if isinstance(a, (list, tuple)):
        return len(a) == len(b) and all(_exact(x, y) for x, y in zip(a, b))
    if isinstance(a, (float, complex)) and not bool(np.isfinite(a)):
        return False
    return a == b


def _has_capture(value, depth=0):
    """Empty placeholders are not captures; zero-valued measurements are valid.

    Nested optimizer state may legitimately contain an empty state mapping
    (e.g. stateless SGD), provided its parameter groups are actually captured.
    RNG tuples may contain a null Gaussian cache and gradients may name unused
    parameters with null values; another nonempty numeric/byte capture is needed.
    """
    if depth > 32:
        raise LabError("first-update evidence exceeds bounded nesting")
    if isinstance(value, np.ndarray):
        return value.size > 0 and value.dtype.kind in "biufc"
    if isinstance(value, np.generic):
        return _has_capture(value.item(), depth + 1)
    if isinstance(value, dict):
        return any(_has_capture(item, depth + 1) for item in value.values())
    if isinstance(value, (tuple, list)):
        return any(_has_capture(item, depth + 1) for item in value)
    return type(value) in (int, float, complex) or isinstance(value, bytes) and bool(value)


def audit_first_update(reference, observed):
    """Exact parity for replay, removed-forward and resume engineering controls."""
    names = ("logits", "loss", "gradients", "norm", "state", "optimizer", "rng")
    if not isinstance(reference, dict) or not isinstance(observed, dict):
        raise LabError("first-update verification requires named evidence objects")
    missing = [
        name
        for name in names
        if name not in reference
        or name not in observed
        or not _has_capture(reference[name])
        or not _has_capture(observed[name])
    ]
    checks = {
        name: bool(_exact(reference[name], observed[name])) for name in names if name not in missing
    }
    return {
        "status": "FAIL" if not all(checks.values()) else "UNKNOWN" if missing else "PASS",
        "checks": checks,
        "missing_evidence": missing,
        "scope": "exact fixed engineering update; not a new scientific fit",
    }


def runner_config(
    recipe,
    *,
    recipe_input,
    command,
    inputs,
    artifacts,
    metrics,
    split_identity,
    source_kind,
    timeout_seconds,
    research_adequacy,
):
    """Translate to the existing controlled runner; never bypass adequacy gates."""
    _validate_recipe(recipe)
    if not isinstance(inputs, list) or recipe_input not in inputs:
        raise LabError("the serialized learning recipe must be a declared runner input")
    if not isinstance(research_adequacy, dict):
        raise LabError("research training requires the existing pinned adequacy pointer")
    config = {
        "schema": "trainlab.experiment.v2",
        "name": recipe["name"],
        "description": "Fixed latent-study continuation: " + recipe["recipe_sha256"],
        "command": command,
        "seed": recipe["seed"],
        "timeout_seconds": timeout_seconds,
        "source_kind": source_kind,
        "split_identity": split_identity,
        "inputs": inputs,
        "artifacts": artifacts,
        "metrics": metrics,
        "budget": recipe["budget"],
        "workload": {
            "kind": "train",
            "training_method": "continual",
            "execution": "single_process",
        },
        "checks": {},
        "execution_purpose": "research",
        "research_adequacy": research_adequacy,
    }
    _canonical(config)
    return copy.deepcopy(config)


def run_training_recipe(config_path, runs_root, *, recipe_input):
    """Run an explicitly supplied trusted command through TrainLab's own gates."""
    path = Path(config_path)
    config = load_config(path)
    if recipe_input not in config["inputs"]:
        raise LabError("learning recipe is not bound as a runner input")
    recipe = read_json(contained_file(path.resolve().parent, recipe_input))
    _validate_recipe(recipe)
    if (
        config.get("execution_purpose", "research") != "research"
        or config["seed"] != recipe["seed"]
        or config["budget"] != recipe["budget"]
    ):
        raise LabError("runner purpose, seed or budgets differ from the frozen learning recipe")
    if config.get("workload", {}).get("kind") != "train":
        raise LabError("learning recipe requires a training workload")
    return run_experiment(path, Path(runs_root))
