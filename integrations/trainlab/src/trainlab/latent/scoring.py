"""Full-vocabulary, counterfactual and retention scoring from saved outputs."""

from __future__ import annotations

import numpy as np

from ..runner import LabError
from .statistics import _finite, _ids, cluster_means, make_bootstrap, record_means


def _integers(values, shape, name, upper=None):
    try:
        a = np.asarray(values)
    except (ValueError, TypeError) as error:
        raise LabError(f"{name} must be an integer array") from error
    if a.shape != shape or a.dtype.kind not in "iu" or np.any(a < 0):
        raise LabError(f"{name} must have the declared nonnegative integer shape")
    if upper is not None and np.any(a >= upper):
        raise LabError(f"{name} contains an out-of-vocabulary index")
    return a.astype(np.int64)


def classification_metrics(logits, targets, answer_ids=None):
    """Native argmax (first-index tie rule), stable NLL and full-class Brier."""
    try:
        raw = np.asarray(logits)
    except (ValueError, TypeError) as error:
        raise LabError("logits must be a rectangular numerical array") from error
    if raw.ndim < 2 or raw.shape[-1] < 2 or any(d == 0 for d in raw.shape):
        raise LabError("logits require nonempty observations and at least two classes")
    if raw.size > 20_000_000:
        raise LabError("classification batch exceeds 20000000 logits; score smaller native batches")
    x = _finite(raw, "logits")
    y = _integers(targets, x.shape[:-1], "targets", x.shape[-1])
    z = x - x.max(axis=-1, keepdims=True)
    logp = z - np.log(np.exp(z).sum(axis=-1, keepdims=True))
    p = np.exp(logp)
    target_logp = np.take_along_axis(logp, y[..., None], axis=-1)[..., 0]
    pred = x.argmax(axis=-1)
    result = {
        "native_prediction": pred,
        "native_correct": pred == y,
        "native_tie": (x == x.max(axis=-1, keepdims=True)).sum(axis=-1) > 1,
        "target_nll": -target_logp,
        "max_probability": p.max(axis=-1),
        "multiclass_brier": (p * p).sum(axis=-1) - 2 * np.exp(target_logp) + 1,
    }
    if answer_ids is not None:
        answers = np.asarray(answer_ids)
        if answers.ndim != 1 or not len(answers):
            raise LabError("answer IDs must be a nonempty class subset")
        answers = _integers(answers, answers.shape, "answer IDs", x.shape[-1])
        if len(np.unique(answers)) != len(answers):
            raise LabError("answer IDs must be unique")
        result["answer_probability_mass"] = p[..., answers].sum(axis=-1)
    if any(not np.isfinite(v).all() for v in result.values()):
        raise LabError("classification arithmetic overflowed")
    return result


def counterfactual_metrics(
    logits, targets, pair_ids, assignment, *, candidate_ids=None, unit_ids=None, strata=None
):
    """Keep swapped assignments together; one correct answer never passes a pair.

    Native ties use the model's argmax convention and are reported. Restricted
    candidate ties always fail. Units normally identify unordered key families.
    """
    try:
        raw = np.asarray(logits)
    except (ValueError, TypeError) as error:
        raise LabError("counterfactual logits must be a rectangular numerical array") from error
    if raw.ndim != 2:
        raise LabError("counterfactual logits must be rows by full vocabulary")
    row = classification_metrics(raw, targets)
    x = _finite(raw, "logits")
    y = _integers(targets, (len(x),), "targets", x.shape[1])
    pairs = _ids(pair_ids, name="pair IDs")
    a = _integers(assignment, (len(x),), "assignment", 2)
    if len(pairs) != len(x) or len(x) % 2:
        raise LabError("counterfactual pair IDs must align to an even row count")
    unique, counts = np.unique(pairs, return_counts=True)
    if np.any(counts != 2):
        raise LabError("every counterfactual pair must contain exactly two rows")
    members = np.lexsort((a, pairs)).reshape(-1, 2)
    if not np.all(a[members] == [0, 1]) or np.any(y[members[:, 0]] == y[members[:, 1]]):
        raise LabError("pairs require assignments zero/one and different targets")
    units = pairs if unit_ids is None else _ids(unit_ids)
    labels = np.zeros(len(x), dtype=np.int64) if strata is None else _ids(strata, name="strata")
    if len(units) != len(x) or len(labels) != len(x):
        raise LabError("unit IDs and strata must align to prediction rows")
    if np.any(units[members[:, 0]] != units[members[:, 1]]) or np.any(
        labels[members[:, 0]] != labels[members[:, 1]]
    ):
        raise LabError("a counterfactual pair crosses units or strata")
    pair = {
        "native_complete_pair": row["native_correct"][members].all(axis=1).astype(float),
        "native_individual_accuracy": row["native_correct"][members].mean(axis=1),
        "target_nll": row["target_nll"][members].mean(axis=1),
        "native_tie_rate": row["native_tie"][members].mean(axis=1),
        "same_native_answer": (
            row["native_prediction"][members[:, 0]] == row["native_prediction"][members[:, 1]]
        ).astype(float),
    }
    if candidate_ids is not None:
        candidates = _integers(candidate_ids, (len(x), 2), "candidates", x.shape[1])
        if np.any(candidates[:, 0] == candidates[:, 1]) or not np.all(
            (candidates == y[:, None]).any(axis=1)
        ):
            raise LabError("each row needs two distinct candidates including its target")
        if not np.array_equal(
            np.sort(candidates[members[:, 0]], axis=1), np.sort(candidates[members[:, 1]], axis=1)
        ):
            raise LabError("candidate vocabulary differs within a pair")
        alternate = np.where(candidates[:, 0] == y, candidates[:, 1], candidates[:, 0])
        margin = x[np.arange(len(x)), y] - x[np.arange(len(x)), alternate]
        if not np.isfinite(margin).all():
            raise LabError("candidate margin overflowed")
        prediction = np.where(margin > 0, y, np.where(margin < 0, alternate, -1))
        row.update(
            candidate_margin=margin,
            candidate_correct=margin > 0,
            candidate_tie=margin == 0,
            candidate_prediction=prediction,
            binary_correct_probability=np.exp(-np.logaddexp(0.0, -margin)),
        )
        pair.update(
            candidate_complete_pair=(margin[members] > 0).all(axis=1).astype(float),
            candidate_individual_accuracy=(margin[members] > 0).mean(axis=1),
            mean_candidate_margin=margin[members].mean(axis=1),
            minimum_candidate_margin=margin[members].min(axis=1),
            candidate_tie_rate=(margin[members] == 0).mean(axis=1),
            binary_correct_probability=row["binary_correct_probability"][members].mean(axis=1),
            same_candidate_answer=(prediction[members[:, 0]] == prediction[members[:, 1]]).astype(
                float
            ),
        )
    return {
        "row": row,
        "pair": pair,
        "members": members,
        "pair_ids": unique,
        "unit_ids": units[members[:, 0]],
        "strata": labels[members[:, 0]],
    }


def summarize_counterfactual(scored, *, draws=5000, seed=0):
    """Stratified family intervals plus each overlap stratum, preserving pair units."""
    units, labels = _ids(scored["unit_ids"]), _ids(scored["strata"], name="strata")
    names = list(scored["pair"])
    matrix = np.column_stack([_finite(scored["pair"][name]) for name in names])
    if len(matrix) != len(units) or len(labels) != len(units):
        raise LabError("counterfactual summaries have inconsistent pair metadata")
    for unit in np.unique(units):
        if len(np.unique(labels[units == unit])) != 1:
            raise LabError("one bootstrap family belongs to multiple overlap strata")
    result = {}
    selections = [("all", np.ones(len(units), dtype=bool))]
    selections += [(str(label), labels == label) for label in np.unique(labels)]
    if len({name for name, _ in selections}) != len(selections):
        raise LabError("stratum label 'all' is reserved for aggregate estimates")
    for name, selected in selections:
        ids, means = cluster_means(matrix[selected], units[selected])
        strata = np.asarray([labels[np.flatnonzero(units == unit)[0]] for unit in ids])
        plan = make_bootstrap(ids, strata=strata if name == "all" else None, draws=draws, seed=seed)
        summary = plan.estimate(means)
        result[name] = {
            "units": len(ids),
            "complete_pairs": int(selected.sum()),
            "metrics": {
                metric: {
                    "mean": summary["mean"][j],
                    "ci95": [summary["ci95"][0][j], summary["ci95"][1][j]],
                }
                for j, metric in enumerate(names)
            },
            "bootstrap": plan.manifest(),
        }
    return result


def calibration(confidence, correct, bins=10):
    conf, good = _finite(confidence, "confidence"), _finite(correct, "correctness")
    if (
        conf.shape != good.shape
        or not conf.size
        or np.any((conf < 0) | (conf > 1))
        or np.any((good != 0) & (good != 1))
    ):
        raise LabError("calibration needs aligned probabilities and binary correctness")
    if type(bins) is not int or not 2 <= bins <= 1000:
        raise LabError("calibration bins must be an integer in [2, 1000]")
    edges = np.linspace(0.0, 1.0, bins + 1)
    index = np.minimum(np.searchsorted(edges, conf.ravel(), side="right") - 1, bins - 1)
    count = np.bincount(index, minlength=bins)
    sums = np.bincount(index, weights=conf.ravel(), minlength=bins)
    hits = np.bincount(index, weights=good.ravel(), minlength=bins)
    rows = [
        {
            "bin": i,
            "left": float(edges[i]),
            "right": float(edges[i + 1]),
            "positions": int(count[i]),
            "mean_confidence": float(sums[i] / count[i]) if count[i] else None,
            "accuracy": float(hits[i] / count[i]) if count[i] else None,
            "ece_contribution": float(abs(hits[i] - sums[i]) / conf.size),
        }
        for i in range(bins)
    ]
    return {
        "ece": float(np.abs(hits - sums).sum() / conf.size),
        "bins": rows,
        "positions": int(conf.size),
        "uncertainty": "descriptive point only",
        "boundary_rule": "[left,right), last includes one; empty bins contribute zero",
    }


def correctness_transition_masks(left_correct, right_correct):
    """Describe reference/right -> comparison/left transitions (left minus right).

    CW is a previously correct reference becoming wrong in the comparison;
    WC is a previously wrong reference becoming correct in the comparison.
    """
    left, right = _finite(left_correct), _finite(right_correct)
    if (
        left.shape != right.shape
        or np.any((left != 0) & (left != 1))
        or np.any((right != 0) & (right != 1))
    ):
        raise LabError("correctness transitions require aligned binary values")
    a, b = left.astype(bool), right.astype(bool)
    return {"CC": b & a, "CW": b & ~a, "WC": ~b & a, "WW": ~b & ~a}


def additive_nll_decomposition(left_nll, right_nll, group_masks, *, record_ids=None):
    """Unconditional mask*delta contributions; groups sum within each source unit."""
    a, b = _finite(left_nll), _finite(right_nll)
    if a.shape != b.shape or a.ndim not in (1, 2) or not a.size or np.any(a < 0) or np.any(b < 0):
        raise LabError("NLL decomposition requires aligned nonnegative rows or windows")
    if not isinstance(group_masks, dict) or not group_masks:
        raise LabError("decomposition requires an explicit exhaustive partition")
    masks = {}
    for name, mask in group_masks.items():
        m = _finite(mask)
        if (
            not isinstance(name, str)
            or not name
            or m.shape != a.shape
            or np.any((m != 0) & (m != 1))
        ):
            raise LabError("group masks must be named binary arrays matching NLL")
        masks[name] = m.astype(bool)
    if not np.all(np.stack(list(masks.values())).sum(axis=0) == 1):
        raise LabError("decomposition groups overlap or omit observations")
    ids = np.arange(len(a)) if record_ids is None else _ids(record_ids)
    if len(ids) != len(a):
        raise LabError("record IDs must align to rows or windows")
    reduce = record_means if a.ndim == 2 else cluster_means
    units, total = reduce(a - b, ids)
    contributions, fractions = {}, {}
    for name, mask in masks.items():
        _, contributions[name] = reduce(np.where(mask, a - b, 0.0), ids)
        _, fractions[name] = reduce(mask, ids)
    if not np.allclose(
        np.stack(list(contributions.values())).sum(axis=0), total, rtol=0, atol=1e-12
    ):
        raise LabError("recordwise NLL contributions do not add to total difference")
    return {
        "unit_ids": units,
        "total_difference": total,
        "contributions": contributions,
        "fractions": fractions,
        "scope": "descriptive unconditional accounting; not causal mediation",
    }


def competence_retention_gates(
    *,
    checkpoint_id,
    task_cells,
    copy_control,
    retention_cells,
    required_delays=(0, 8),
    required_strata=("all", "shared_first", "shared_second", "neither"),
    required_domains=("Shakespeare", "Alice"),
    task_point=0.8,
    task_lower=0.7,
    copy_point=0.8,
    retention_upper=0.10,
):
    """Conjoin native-task and retention evidence for exactly one checkpoint.

    Cells contain ``checkpoint_id``, ``metric``, ``mean``, ``ci95`` plus
    ``delay``/``stratum`` or ``domain``. Copy control omits the interval.
    Task metrics are native_complete_pair; retention uses delta_target_nll.
    Missing evidence is UNKNOWN; a mismatched identity is invalid evidence.
    """
    if not isinstance(checkpoint_id, str) or not checkpoint_id:
        raise LabError("gates require an explicit checkpoint identity")
    thresholds = _finite([task_point, task_lower, copy_point, retention_upper])
    if np.any((thresholds[:3] < 0) | (thresholds[:3] > 1)):
        raise LabError("task thresholds must be probabilities")
    delays, strata, domains = list(required_delays), list(required_strata), list(required_domains)
    if (
        not delays
        or not strata
        or not domains
        or any(len(set(v)) != len(v) for v in (delays, strata, domains))
    ):
        raise LabError("gate requirements must be nonempty and unique")
    missing_metric = []

    def check(cell, interval=True, probability=False):
        if not isinstance(cell, dict) or cell.get("checkpoint_id") != checkpoint_id:
            raise LabError("gate evidence belongs to another or unidentified checkpoint")
        mean = _finite(cell.get("mean"))
        if mean.ndim:
            raise LabError("gate point estimate must be scalar")
        if probability and not 0 <= mean <= 1:
            raise LabError("task gate score is outside [0,1]")
        allowed = (
            {"native_complete_pair", "native256_complete_pair", "native256_complete_pair_accuracy"}
            if probability
            else {"delta_target_nll"}
        )
        if cell.get("metric") is None:
            missing_metric.append("task" if probability else "retention")
        elif cell["metric"] not in allowed:
            raise LabError("gate evidence has the wrong metric or native-versus-candidate scope")
        if interval:
            bounds = _finite(cell.get("ci95"))
            if bounds.shape != (2,) or bounds[0] > bounds[1]:
                raise LabError("gate interval must have two ordered finite bounds")
            if probability and np.any((bounds < 0) | (bounds > 1)):
                raise LabError("task gate interval is outside [0,1]")

    task = {}
    for cell in task_cells:
        check(cell, probability=True)
        key = (cell.get("delay"), cell.get("stratum"))
        if key in task or key[0] not in delays or key[1] not in strata:
            raise LabError("duplicate or undeclared task gate cell")
        task[key] = bool(cell["mean"] >= task_point and cell["ci95"][0] >= task_lower)
    language = {}
    for cell in retention_cells:
        check(cell)
        domain = cell.get("domain")
        if domain in language or domain not in domains:
            raise LabError("duplicate or undeclared retention gate domain")
        language[domain] = bool(cell["ci95"][1] <= retention_upper)
    if copy_control is not None:
        check(copy_control, interval=False, probability=True)
    task_known = (
        len(task) == len(delays) * len(strata)
        and copy_control is not None
        and "task" not in missing_metric
    )
    retention_known = len(language) == len(domains) and "retention" not in missing_metric
    task_pass = task_known and all(task.values()) and copy_control["mean"] >= copy_point
    retention_pass = retention_known and all(language.values())
    known = task_known and retention_known
    return {
        "checkpoint_id": checkpoint_id,
        "status": "PASS"
        if known and task_pass and retention_pass
        else "FAIL"
        if known
        else "UNKNOWN",
        "task_qualified": bool(task_pass),
        "language_retained": bool(retention_pass),
        "joint_qualified": bool(task_pass and retention_pass),
        "task_evidence_complete": task_known,
        "retention_evidence_complete": retention_known,
        "missing_metric_identity": sorted(set(missing_metric)),
        "task_cells": [
            {"delay": d, "stratum": s, "passed": task.get((d, s))} for d in delays for s in strata
        ],
        "retention_domains": {d: language.get(d) for d in domains},
        "thresholds": {
            "task_point_min": task_point,
            "task_lower95_min": task_lower,
            "copy_point_min": copy_point,
            "retention_delta_nll_upper95_max": retention_upper,
        },
        "scope": "declared engineering criteria; not frontier or release qualification",
    }
