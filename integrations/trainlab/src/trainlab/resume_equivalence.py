"""Compare observable training state at and after a checkpoint boundary."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from fractions import Fraction
from pathlib import Path

from .experiment_diagnostics import _number
from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _require, _text
from .runner import LabError, _constant, _pairs


def _read(path, pin):
    path = Path(path)
    _require(
        _hash(pin) and path.is_file() and not path.is_symlink(),
        "pinned regular JSON file required",
    )
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(
        len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == pin,
        "resume evidence size/hash mismatch",
    )
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid resume evidence JSON") from exc
    _bytes(value)
    return value


def _plan(plan):
    _require(
        type(plan) is dict
        and set(plan)
        == {
            "schema",
            "context_sha256",
            "checkpoint_sha256",
            "steps",
            "components",
        }
        and plan["schema"] == "trainlab.resume-plan.v1"
        and _hash(plan["context_sha256"])
        and _hash(plan["checkpoint_sha256"]),
        "invalid resume plan",
    )
    steps = plan["steps"]
    _require(
        type(steps) is list
        and 2 <= len(steps) <= 1000
        and all(type(i) is int and 0 <= i <= 10**9 for i in steps)
        and all(after == before + 1 for before, after in zip(steps, steps[1:])),
        "consecutive steps including the resume boundary required",
    )
    components = plan["components"]
    _require(
        type(components) is dict
        and 1 <= len(components) <= 64
        and all(_text(k) for k in components),
        "bounded named components required",
    )
    for rule in components.values():
        _require(
            type(rule) is dict
            and (
                rule == {"kind": "exact"}
                or set(rule) == {"kind", "atol", "rtol", "length"}
                and rule["kind"] == "numeric"
                and _number(rule["atol"], 0, 1e20)
                and _number(rule["rtol"], 0, 1)
                and type(rule["length"]) is int
                and 1 <= rule["length"] <= 100000
            ),
            "invalid component comparison rule",
        )
    return steps, components


def _trace(trace, plan, plan_pin, role):
    _require(
        type(trace) is dict
        and set(trace)
        == {
            "schema",
            "role",
            "plan_sha256",
            "context_sha256",
            "checkpoint_sha256",
            "samples",
        }
        and trace["schema"] == "trainlab.resume-trace.v1"
        and trace["role"] == role
        and trace["plan_sha256"] == plan_pin
        and all(trace[k] == plan[k] for k in ("context_sha256", "checkpoint_sha256")),
        "trace does not bind the expected role, plan, context and checkpoint",
    )
    samples = trace["samples"]
    _require(
        type(samples) is list and len(samples) <= len(plan["steps"]),
        "bounded resume samples required",
    )
    allowed = set(plan["steps"])
    prior = -1
    rows = {}
    for sample in samples:
        _require(
            type(sample) is dict
            and set(sample) == {"step", "components"}
            and type(sample["step"]) is int
            and sample["step"] in allowed
            and sample["step"] > prior
            and type(sample["components"]) is dict
            and sample["components"].keys() <= plan["components"].keys(),
            "unexpected, duplicate or unordered resume sample",
        )
        row = sample["components"]
        for name, value in row.items():
            rule = plan["components"][name]
            if value is not None and rule["kind"] == "numeric":
                _require(
                    type(value) is list
                    and len(value) == rule["length"]
                    and all(_number(v) for v in value),
                    "invalid numeric state sample",
                )
        prior = sample["step"]
        rows[prior] = row
    return rows


def _measure(left, right, rule):
    if rule["kind"] == "exact":
        return _bytes(left) == _bytes(right), None
    maximum, equal = 0, True
    absolute, relative = rule["atol"], rule["rtol"]
    for a, b in zip(left, right, strict=True):
        # Large integers can round to the same binary64 value. Exact ratios keep
        # both the tolerance decision and the reported discrepancy meaningful.
        if type(a) is int or type(b) is int or (type(absolute) is int and absolute > 2**53):
            left_value, right_value = Fraction(a), Fraction(b)
            delta = abs(left_value - right_value)
            limit = max(
                Fraction(absolute), Fraction(relative) * max(abs(left_value), abs(right_value))
            )
            equal &= delta <= limit
            size = delta.numerator if delta.denominator == 1 else float(delta)
        else:
            size = abs(a - b)
            equal &= math.isclose(a, b, rel_tol=relative, abs_tol=absolute)
        maximum = max(maximum, size)
    return equal, maximum


def compare(
    plan_path, reference_path, resumed_path, *, plan_sha256, reference_sha256, resumed_sha256
):
    """Compare pinned traces and preserve missing coverage and first observed mismatch."""
    plan = _read(plan_path, plan_sha256)
    steps, rules = _plan(plan)
    reference = _trace(_read(reference_path, reference_sha256), plan, plan_sha256, "reference")
    resumed = _trace(_read(resumed_path, resumed_sha256), plan, plan_sha256, "resumed")
    coverage = {}
    for name, rule in rules.items():
        observed, missing, differences = 0, [], []
        maximum = None
        for step in steps:
            left = reference.get(step, {}).get(name)
            right = resumed.get(step, {}).get(name)
            if left is None or right is None:
                missing.append(step)
                continue
            observed += 1
            equal, delta = _measure(left, right, rule)
            if delta is not None:
                maximum = delta if maximum is None else max(delta, maximum)
            if not equal:
                differences.append(step)
        coverage[name] = {
            "status": "FAILED" if differences else "INCONCLUSIVE" if missing else "TESTED",
            "observed_steps": observed,
            "missing_steps": missing,
            "differing_steps": differences,
            "max_absolute_difference": maximum,
        }
    earliest = min(
        (row["differing_steps"][0] for row in coverage.values() if row["differing_steps"]),
        default=None,
    )
    complete = all(not row["missing_steps"] for row in coverage.values())
    return {
        "schema": "trainlab.resume-equivalence.v1",
        "status": "FAILED" if earliest is not None else "TESTED" if complete else "INCONCLUSIVE",
        "plan_sha256": plan_sha256,
        "reference_sha256": reference_sha256,
        "resumed_sha256": resumed_sha256,
        "checkpoint_step": steps[0],
        "coverage_complete": complete,
        "components": coverage,
        "first_observed_difference": earliest,
        "first_observed_components": sorted(
            k for k, r in coverage.items() if earliest in r["differing_steps"]
        ),
        "scope": "Declared channels and tolerances. Trace provenance is caller supplied.",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("plan", "reference", "resumed"):
        parser.add_argument(f"--{name}", type=Path, required=True)
        parser.add_argument(f"--{name}-sha256", required=True)
    args = parser.parse_args()
    try:
        report = compare(
            args.plan,
            args.reference,
            args.resumed,
            plan_sha256=args.plan_sha256,
            reference_sha256=args.reference_sha256,
            resumed_sha256=args.resumed_sha256,
        )
    except (LabError, OSError) as exc:
        parser.exit(2, f"resume comparison: {exc}\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
