"""Bounded interpretation helpers, not TRAIN-001 qualification or model execution."""

from __future__ import annotations

import hashlib
import json
import math


def unique_rows(rows, *, id_field="episode_id"):
    if not isinstance(rows, list) or not rows:
        raise ValueError("nonempty observation population required")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("observation must be an object")
        key = row.get(id_field)
        if not isinstance(key, str) or not key or key in result:
            raise ValueError("nonempty unique observation IDs required")
        result[key] = row
    return result


def score_by_id(phase):
    rows = unique_rows(phase["episodes"])
    result = {}
    for key, row in rows.items():
        score = row.get("score")
        if type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError("finite normalized observed scores required")
        result[key] = float(score)
    return result


def content_identity(episodes):
    """Hash generated episode serialization; not semantic/near-duplicate detection."""
    rows = []
    for episode in episodes:
        content = json.dumps(
            episode.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
        rows.append(
            {"episode_id": episode.episode_id, "sha256": hashlib.sha256(content).hexdigest()}
        )
    unique_rows(rows)
    return rows


def interpretation(
    reference,
    train_before,
    train_after,
    heldout_before,
    heldout_after,
    *,
    minimum_reference_score=None,
):
    """Interpret recorded scores only after an explicit target-sanity threshold.

    The threshold is caller-declared, not authenticated preregistration. This
    helper does not independently execute a scorer, training or heldout access.
    """
    phases = [reference, train_before, train_after, heldout_before, heldout_after]
    values = [score_by_id(p) for p in phases]
    if set(values[0]) != set(values[1]) or set(values[1]) != set(values[2]):
        raise ValueError("reference/train populations differ")
    if set(values[3]) != set(values[4]) or set(values[1]) & set(values[3]):
        raise ValueError("heldout populations differ or overlap train IDs")
    means = [sum(v.values()) / len(v) for v in values]
    for p, m in zip(phases, means):
        if (
            type(p.get("mean")) not in (int, float)
            or not math.isfinite(p["mean"])
            or abs(p["mean"] - m) > 1e-6
        ):
            raise ValueError("phase summary disagrees with observed scores")
    result = {
        "diagnosis": "pipeline_sanity_unassessed",
        "qualification": "NOT_QUALIFIED",
        "minimum_reference_score": minimum_reference_score,
        "criteria_provenance": "CALLER_DECLARED_NOT_PREREGISTRATION_ATTESTED",
        "scope": "Descriptive generated-panel observations, "
        "not architectural capacity or generalization.",
    }
    if minimum_reference_score is None:
        return result
    if (
        type(minimum_reference_score) not in (int, float)
        or not math.isfinite(minimum_reference_score)
        or not 0 < minimum_reference_score <= 1
    ):
        raise ValueError("explicit finite target-sanity threshold in (0,1] required")
    failures = reference.get("parse_failures")
    if failures is None:
        return result
    if type(failures) is not int or not 0 <= failures <= len(values[0]):
        raise ValueError("target parse-failure count must be a bounded integer")
    parsed = [row.get("parsed") for row in reference["episodes"]]
    if any(value is None for value in parsed):
        return result
    if any(type(value) is not bool for value in parsed):
        raise ValueError("reference parsed flags must be booleans")
    if sum(not value for value in parsed) != failures:
        raise ValueError("reference parse count disagrees with per-case flags")
    if failures != 0 or min(values[0].values()) < minimum_reference_score:
        result["diagnosis"] = "target_scorer_sanity_failed"
        return result
    _, tb, ta, hb, ha = means
    if tb == 1.0 and ta == 1.0:
        diagnosis = "already_at_training_score_ceiling"
    elif ta <= tb:
        diagnosis = "no_detected_training_score_improvement"
    elif ha <= hb:
        diagnosis = "training_score_improvement_without_detected_transfer"
    else:
        diagnosis = "observed_training_and_heldout_score_improvement"
    result["diagnosis"] = diagnosis
    result["target_sanity"] = "DECLARED_THRESHOLD_MET"
    return result
