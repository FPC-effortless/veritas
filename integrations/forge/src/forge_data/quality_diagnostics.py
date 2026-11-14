"""Bounded dataset quality evidence; reviewed assertions are not verified label truth."""

from __future__ import annotations

import copy
import math
from bisect import bisect_right
from collections import Counter
from itertools import islice, product
from pathlib import Path

from .core import ForgeError, _timestamp, canonical, hash_bytes
from .dataset import _hash, _json
from .diagnostics import MAX_BYTES, _fields, _require, _text, _validate


def _bound(value, depth=0):
    _require(depth <= 32, "JSON nesting exceeds 32")
    if type(value) is dict:
        _require(all(type(k) is str for k in value), "string JSON keys required")
        for item in value.values():
            _bound(item, depth + 1)
    elif type(value) is list:
        for item in value:
            _bound(item, depth + 1)
    else:
        _require(value is None or type(value) in (str, bool, int, float), "plain JSON required")
        if type(value) in (int, float):
            try:
                _require(math.isfinite(value), "finite number required")
            except OverflowError as exc:
                raise ForgeError("numeric value too large") from exc
    if depth == 0:
        try:
            _require(len(canonical(value)) <= MAX_BYTES, "document exceeds 16 MiB")
        except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
            raise ForgeError("invalid bounded JSON") from exc


def _load(path, sha256):
    _require(_hash(sha256), "pinned input SHA256 required")
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    _require(len(data) <= MAX_BYTES and hash_bytes(data) == sha256, "input size/hash mismatch")
    document = _json(data)
    _bound(document)
    _validate(document)  # Reject TEST anywhere, before any bounded scan.
    return document


def _report(kind, inputs, status, **observations):
    _bound(inputs)
    report = {
        "schema": "forge.quality-diagnostics.v1",
        "version": "1",
        "kind": kind,
        "input_sha256": hash_bytes(canonical(inputs)),
        "status": status,
        "observations": observations,
        "scientific_qualification": "NOT_QUALIFIED",
    }
    _bound(report)
    return copy.deepcopy(report)


def _unit(value):
    return type(value) in (int, float) and 0 <= value <= 1


def distributions(
    reference_path,
    current_path,
    *,
    reference_sha256,
    current_sha256,
    fields,
    thresholds,
    reference_split="train",
    current_split="validation",
    max_rows=10000,
    rare_count=2,
):
    """Descriptive empirical distances, not statistical significance or causal drift."""
    reference, current = (
        _load(reference_path, reference_sha256),
        _load(current_path, current_sha256),
    )
    _require(
        type(fields) is dict
        and 1 <= len(fields) <= 32
        and all(
            k in reference["feature_fields"]
            and k in current["feature_fields"]
            and v in ("numeric", "categorical")
            for k, v in fields.items()
        ),
        "declared feature kinds required",
    )
    _require(
        type(thresholds) is dict
        and set(thresholds) == {"numeric", "categorical", "missingness"}
        and all(_unit(v) for v in thresholds.values()),
        "explicit distance thresholds required",
    )
    _require(
        reference_split in ("train", "validation")
        and current_split in ("train", "validation")
        and type(max_rows) is int
        and 1 <= max_rows <= 100000
        and type(rare_count) is int
        and 1 <= rare_count <= 100000,
        "invalid scan parameters",
    )
    all_rows = [
        [r for r in doc["rows"] if r["split"] == split]
        for doc, split in ((reference, reference_split), (current, current_split))
    ]
    selected = [rows[:max_rows] for rows in all_rows]
    partial = any(len(a) != len(b) for a, b in zip(all_rows, selected))
    checks = []
    for field, kind in fields.items():
        known, missing, invalid = [], [], []
        for rows in selected:
            values = [r["features"].get(field) for r in rows]
            missing.append(sum(v is None for v in values))

            def valid(v):
                return (
                    type(v) in (int, float)
                    if kind == "numeric"
                    else type(v) in (str, bool, int, float)
                )

            invalid.append(sum(v is not None and not valid(v) for v in values))
            known.append([v for v in values if v is not None and valid(v)])
        distance, categories = None, None
        if all(known):
            if kind == "numeric":
                left, right = sorted(known[0]), sorted(known[1])
                distance = max(
                    abs(bisect_right(left, x) / len(left) - bisect_right(right, x) / len(right))
                    for x in set(left + right)
                )
            else:
                counts = [Counter(canonical(v) for v in values) for values in known]
                union = sorted(set(counts[0]) | set(counts[1]))
                distance = (
                    sum(
                        abs(counts[0][v] / len(known[0]) - counts[1][v] / len(known[1]))
                        for v in union
                    )
                    / 2
                )
                categories = {
                    "total": len(union),
                    "shown": min(len(union), 100),
                    "rare_current": sum(0 < counts[1][v] <= rare_count for v in union),
                    "novel_current": sum(counts[0][v] == 0 for v in counts[1]),
                    "counts": [
                        {"value": _json(v), "reference": counts[0][v], "current": counts[1][v]}
                        for v in union[:100]
                    ],
                }
        delta = (
            abs(missing[0] / len(selected[0]) - missing[1] / len(selected[1]))
            if all(selected)
            else None
        )
        violation = (
            any(invalid)
            or (distance is not None and distance > thresholds[kind])
            or (delta is not None and delta > thresholds["missingness"])
        )
        status = (
            "FAILED"
            if violation
            else "UNSUPPORTED"
            if distance is None
            else "INCONCLUSIVE"
            if partial or any(missing)
            else "TESTED"
        )
        checks.append(
            {
                "field": field,
                "kind": kind,
                "status": status,
                "known": [len(v) for v in known],
                "missing": missing,
                "invalid": invalid,
                "distance": distance,
                "missingness_delta": delta,
                "categories": categories,
            }
        )
    status = (
        "FAILED"
        if any(c["status"] == "FAILED" for c in checks)
        else "TESTED"
        if all(c["status"] == "TESTED" for c in checks)
        else "INCONCLUSIVE"
    )
    return _report(
        "distributions",
        [
            reference_sha256,
            current_sha256,
            fields,
            thresholds,
            reference_split,
            current_split,
            max_rows,
            rare_count,
        ],
        status,
        checks=checks,
        selected_rows=[len(x) for x in selected],
        available_rows=[len(x) for x in all_rows],
        partial=partial,
        methods={"numeric": "empirical KS distance", "categorical": "total variation"},
        inference="No p-values, independent-sampling guarantee, units or causal degradation claim.",
    )


def adjudicate(path, *, sha256, reviews):
    """Return a new document; source is never modified. Reviewer identity is declared."""
    document = _load(path, sha256)
    _bound(reviews)
    _require(
        type(reviews) is list and 1 <= len(reviews) <= 10000, "bounded review decisions required"
    )
    rows = {r["id"]: r for r in document["rows"]}
    seen = set()
    for review in reviews:
        _require(
            type(review) is dict
            and set(review) == {"id", "decision", "old_label", "new_label", "reviewer", "rationale"}
            and type(review["id"]) is str
            and review["id"] in rows
            and review["id"] not in seen
            and review["decision"] in ("accept", "reject", "unresolved")
            and _text(review["reviewer"])
            and _text(review["rationale"]),
            "invalid adjudication",
        )
        _require(
            canonical(rows[review["id"]].get("label")) == canonical(review["old_label"]),
            "stale label precondition",
        )
        seen.add(review["id"])
    changed = copy.deepcopy(document)
    changed_rows = {r["id"]: r for r in changed["rows"]}
    applied = []
    for review in reviews:
        if review["decision"] == "accept":
            changed_rows[review["id"]]["label"] = copy.deepcopy(review["new_label"])
            applied.append(review["id"])
    _bound(changed)
    return _report(
        "adjudication",
        [sha256, reviews],
        "INCONCLUSIVE" if any(r["decision"] == "unresolved" for r in reviews) else "TESTED",
        parent_sha256=sha256,
        document_sha256=hash_bytes(canonical(changed)),
        document=changed,
        decisions=reviews,
        applied_ids=applied,
        trust="Reviewer assertions; identity and corrected-label truth not independently verified.",
        repair_effect="NOT_MEASURED",
    )


def transformation_audit(path, *, sha256, transforms, availability):
    """Inspect declared fit membership and feature availability, not trainer execution."""
    document = _load(path, sha256)
    _bound([transforms, availability])
    _require(type(transforms) is list and 1 <= len(transforms) <= 64, "bounded transforms required")
    rows = {r["id"]: r for r in document["rows"]}
    fields = set(document["feature_fields"])
    seen, covered, findings, unknown = set(), set(), [], []
    for transform in transforms:
        _require(
            type(transform) is dict
            and set(transform) == {"id", "outputs", "fit_scope", "fit_ids", "uses_target"}
            and _text(transform["id"])
            and transform["id"] not in seen
            and transform["fit_scope"] in ("stateless", "fitted", "unknown")
            and (transform["uses_target"] is None or type(transform["uses_target"]) is bool),
            "invalid transformation declaration",
        )
        seen.add(transform["id"])
        _fields(transform["outputs"])
        _require(set(transform["outputs"]) <= fields, "unknown output feature")
        covered.update(transform["outputs"])
        fit_ids = transform["fit_ids"]
        _require(
            fit_ids is None
            or (
                type(fit_ids) is list
                and len(fit_ids) <= 100000
                and all(_text(i) for i in fit_ids)
                and len(set(fit_ids)) == len(fit_ids)
            ),
            "invalid transformation fit IDs",
        )
        if transform["fit_scope"] == "stateless":
            _require(fit_ids == [], "stateless transforms must have empty fit IDs")
        elif transform["fit_scope"] == "unknown" or not fit_ids:
            unknown.append({"transform": transform["id"], "kind": "UNKNOWN_FIT"})
        if transform["uses_target"] is True:
            findings.append({"transform": transform["id"], "kind": "TARGET_DERIVED"})
        elif transform["uses_target"] is None:
            unknown.append({"transform": transform["id"], "kind": "UNKNOWN_TARGET_DEPENDENCE"})
        for row_id in fit_ids or []:
            if row_id not in rows:
                unknown.append(
                    {"transform": transform["id"], "row": row_id, "kind": "UNKNOWN_FIT_ROW"}
                )
            elif rows[row_id]["split"] != "train":
                findings.append(
                    {"transform": transform["id"], "row": row_id, "kind": "EVALUATION_FIT"}
                )
    _require(
        type(availability) is list and len(availability) <= 100000, "bounded availability required"
    )
    seen = set()
    for item in availability:
        _require(
            type(item) is dict
            and set(item) == {"id", "field", "available_at", "prediction_at"}
            and type(item["id"]) is str
            and item["id"] in rows
            and type(item["field"]) is str
            and item["field"] in fields,
            "invalid availability row",
        )
        key = (item["id"], item["field"])
        _require(key not in seen, "duplicate availability row")
        seen.add(key)
        available = (
            _timestamp(item["available_at"], "available_at")
            if item["available_at"] is not None
            else None
        )
        prediction = (
            _timestamp(item["prediction_at"], "prediction_at")
            if item["prediction_at"] is not None
            else None
        )
        if available is None or prediction is None:
            unknown.append({"row": item["id"], "field": item["field"], "kind": "UNKNOWN_TIME"})
        elif available > prediction:
            findings.append({"row": item["id"], "field": item["field"], "kind": "FUTURE_FEATURE"})
    missing_availability = len(rows) * len(fields) - len(seen)
    return _report(
        "transformations",
        [sha256, transforms, availability],
        "FAILED"
        if findings
        else "INCONCLUSIVE"
        if unknown or missing_availability or fields - covered
        else "TESTED",
        findings=findings[:100],
        finding_count=len(findings),
        unknown=unknown[:100],
        unknown_count=len(unknown),
        missing_availability=missing_availability,
        uncovered_fields=sorted(fields - covered),
        witness_limit=100,
        trust="Declared provenance only; absence of undeclared leakage is not established.",
    )


def near_duplicates(path, *, sha256, field, threshold=0.8, max_pairs=10000, max_tokens=512):
    """Cross-split whitespace-token-set Jaccard candidates; no semantic leakage verdict."""
    document = _load(path, sha256)
    _require(
        field in document["feature_fields"]
        and _unit(threshold)
        and threshold > 0
        and type(max_pairs) is int
        and 0 <= max_pairs <= 100000
        and type(max_tokens) is int
        and 1 <= max_tokens <= 10000,
        "invalid near-duplicate parameters",
    )
    partitions, unsupported = {"train": [], "validation": []}, []
    for row in document["rows"]:
        value = row["features"].get(field)
        tokens = value.casefold().split() if type(value) is str else []
        if not tokens or len(tokens) > max_tokens:
            unsupported.append(row["id"])
            continue
        partitions[row["split"]].append((row["id"], set(tokens)))
    possible = len(partitions["train"]) * len(partitions["validation"])
    findings, matches, examined = [], 0, 0
    for left, right in islice(product(partitions["train"], partitions["validation"]), max_pairs):
        examined += 1
        similarity = len(left[1] & right[1]) / len(left[1] | right[1])
        if similarity >= threshold:
            matches += 1
            if len(findings) < 100:
                findings.append(
                    {"train_id": left[0], "validation_id": right[0], "similarity": similarity}
                )
    status = (
        "NOT_RUN"
        if not max_pairs
        else "UNSUPPORTED"
        if not possible
        else "INCONCLUSIVE"
        if matches or unsupported or examined < possible
        else "TESTED"
    )
    return _report(
        "near_duplicates",
        [sha256, field, threshold, max_pairs, max_tokens],
        status,
        findings=findings,
        match_count=matches,
        examined_pairs=examined,
        possible_supported_pairs=possible,
        unsupported_rows=unsupported[:100],
        unsupported_count=len(unsupported),
        witness_limit=100,
        interpretation="Lexical review candidates, not proof of duplicate meaning or leakage.",
    )
