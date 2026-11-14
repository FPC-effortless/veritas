"""Score explicitly scoped regression, token sequence and retrieval outcomes."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict
from itertools import pairwise

from .experiment_diagnostics import _items, _number
from .prediction_artifacts import _bytes, _require, _text

_FIELDS = {"id", "slice", "label", "prediction"}


def _mean(values):
    return math.fsum(values) / len(values) if values else None


def _report(task, rows, results, metrics, configuration, intervals=False):
    groups = defaultdict(list)
    for row, result in zip(rows, results, strict=True):
        groups[row["slice"]].append((row, result))

    def summarize(pairs):
        values = [result for _, result in pairs if isinstance(result, tuple)]
        missing = sum(result is None for _, result in pairs)
        observed = metrics(values) if values else None
        report = {
            "expected": len(pairs),
            "observed": len(values),
            "unobserved": missing,
            "inapplicable": len(pairs) - len(values) - missing,
            "missing_labels": sum(row["label"] is None for row, _ in pairs),
            "missing_predictions": sum(row["prediction"] is None for row, _ in pairs),
            "metrics": observed if missing == 0 else None,
            "observed_metrics": observed,
        }
        if task == "retrieval":
            report["queries_with_incomplete_judgments"] = sum(
                type(row["label"]) is dict and None in row["label"].values() for row, _ in pairs
            )
        if task == "sequence":
            report["observed_target_positions"] = sum(result[2] for result in values)
        if intervals:
            coverage = [
                row["interval"][0] <= row["label"] <= row["interval"][1]
                for row, _ in pairs
                if row["interval"] is not None and row["label"] is not None
            ]
            observed_coverage = _mean(coverage)
            report["intervals"] = {
                "expected": len(pairs),
                "observed": len(coverage),
                "coverage": observed_coverage if len(coverage) == len(pairs) else None,
                "observed_coverage": observed_coverage,
            }
        return report

    overall = summarize(list(zip(rows, results, strict=True)))
    status = "TESTED"
    if overall["unobserved"] or (intervals and overall["intervals"]["coverage"] is None):
        status = "PARTIAL"
    elif overall["observed"] == 0:
        status = "INAPPLICABLE"
    return {
        "schema": "trainlab.task-behavior.v1",
        "task": task,
        "status": status,
        "configuration": configuration,
        "input_sha256": hashlib.sha256(_bytes([task, configuration, rows])).hexdigest(),
        "overall": overall,
        "slices": {name: summarize(pairs) for name, pairs in groups.items()},
        "scientific_qualification": "NOT_QUALIFIED",
    }


def _validate(rows, fields):
    _items(rows, maximum=2000)
    _require(all(set(row) == fields and _text(row["slice"]) for row in rows), "invalid row schema")


def regression(rows, *, intervals=False):
    """Measure signed prediction error and declared closed-interval coverage."""
    _require(type(intervals) is bool, "interval coverage must be explicitly enabled")
    _validate(rows, _FIELDS | {"interval"} if intervals else _FIELDS)
    results = []
    for row in rows:
        label, predicted = row["label"], row["prediction"]
        _require(
            all(value is None or _number(value, -1e12, 1e12) for value in (label, predicted)),
            "bounded scalar label and prediction required",
        )
        interval = row.get("interval")
        _require(
            interval is None
            or (
                type(interval) is list
                and len(interval) == 2
                and all(_number(v, -1e12, 1e12) for v in interval)
                and interval[0] <= interval[1]
            ),
            "ordered interval endpoints required",
        )
        results.append(
            (predicted - label,) if label is not None and predicted is not None else None
        )

    def metrics(values):
        errors = [error for (error,) in values]
        scale = max(abs(error) for error in errors)
        rmse = (
            scale * math.sqrt(_mean([(error / scale) ** 2 for error in errors])) if scale else 0.0
        )
        return {
            "mae": _mean([abs(error) for error in errors]),
            "rmse": rmse,
            "mean_signed_error": _mean(errors),
        }

    return _report("regression", rows, results, metrics, {"intervals": intervals}, intervals)


def _edit_distance(label, predicted):
    previous = list(range(len(predicted) + 1))
    for i, target in enumerate(label, 1):
        current = [i]
        for token, (diagonal, above) in zip(predicted, pairwise(previous), strict=True):
            current.append(min(current[-1] + 1, above + 1, diagonal + (token != target)))
        previous = current
    return previous[-1]


def sequence(rows):
    """Compare ordered lists of nonempty string tokens, including empty lists."""
    _validate(rows, _FIELDS)
    cost = 0
    results = []
    for row in rows:
        label, predicted = row["label"], row["prediction"]
        _require(
            all(
                value is None
                or (type(value) is list and len(value) <= 512 and all(_text(v) for v in value))
                for value in (label, predicted)
            ),
            "bounded lists of string tokens required",
        )
        if label is None or predicted is None:
            results.append(None)
            continue
        cost += len(label) * len(predicted)
        _require(cost <= 2_000_000, "edit distance cell budget exceeded")
        results.append(
            (
                label == predicted,
                sum(expected == actual for expected, actual in zip(label, predicted, strict=False)),
                len(label),
                _edit_distance(label, predicted),
            )
        )

    def metrics(values):
        exact, matched, positions, edits = zip(*values, strict=True)
        target_count = sum(positions)
        return {
            "exact_match": _mean(exact),
            "target_position_accuracy": sum(matched) / target_count if target_count else None,
            "mean_edit_distance": _mean(edits),
        }

    return _report("sequence", rows, results, metrics, {"token_schema": "string-list"})


def retrieval(rows, *, cutoff):
    """Score declared total ranks against closed, exhaustively judged candidate sets."""
    _require(type(cutoff) is int and 1 <= cutoff <= 1000, "bounded integer cutoff required")
    _validate(rows, _FIELDS)
    results = []
    for row in rows:
        label, predicted = row["label"], row["prediction"]
        _require(
            label is None
            or (
                type(label) is dict
                and 1 <= len(label) <= 1000
                and all(_text(k) and (v is None or type(v) is bool) for k, v in label.items())
            ),
            "explicit candidate identity judgments required",
        )
        _require(
            predicted is None
            or (
                type(predicted) is list
                and len(predicted) <= 1000
                and all(_text(v) for v in predicted)
                and len(set(predicted)) == len(predicted)
                and (label is None or set(predicted) <= label.keys())
            ),
            "ordered distinct candidate predictions required",
        )
        if label is None or None in label.values():
            results.append(None)
            continue
        relevant = sum(label.values())
        if not relevant:
            results.append("inapplicable")
        elif predicted is None:
            results.append(None)
        else:
            hits = [i for i, candidate in enumerate(predicted[:cutoff], 1) if label[candidate]]
            results.append(
                (
                    math.fsum(found / rank for found, rank in enumerate(hits, 1))
                    / min(cutoff, relevant),
                    len(hits) / relevant,
                    1 / hits[0] if hits else 0.0,
                )
            )

    def metrics(values):
        names = ("average_precision", "recall", "reciprocal_rank")
        return {
            name: _mean(values)
            for name, values in zip(names, zip(*values, strict=True), strict=True)
        }

    return _report(
        "retrieval", rows, results, metrics, {"cutoff": cutoff, "order": "producer-total-order"}
    )
