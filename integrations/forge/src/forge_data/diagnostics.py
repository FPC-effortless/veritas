"""Bounded exact-content diagnostics for explicitly selected train/validation views.

No label corrections, inferred causal independence, or scientific qualification.
This local format is not a sanitizer: row IDs and hashes can reveal information.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from .core import ForgeError, canonical, hash_bytes
from .dataset import _json

MAX_BYTES = 16 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise ForgeError(message)


def _text(value):
    return isinstance(value, str) and 0 < len(value.strip()) <= 2000 and "\0" not in value


def _fields(values, *, empty=False):
    _require(type(values) is list and (empty or values) and len(values) <= 32
             and all(_text(v) for v in values) and len(set(values)) == len(values),
             "bounded distinct field names required")


def _validate(document):
    _require(type(document) is dict and set(document) == {
        "schema", "feature_fields", "group_fields", "rows"}
        and document["schema"] == "forge.diagnostic-input.v1", "invalid diagnostic input")
    _fields(document["feature_fields"])
    _fields(document["group_fields"], empty=True)
    rows = document["rows"]
    _require(type(rows) is list and 1 <= len(rows) <= 100000, "bounded nonempty rows required")
    seen = set()
    for row in rows:
        _require(type(row) is dict and {"id", "split", "features"} <= set(row)
                 and set(row) <= {"id", "split", "features", "label", "groups"}
                 and _text(row["id"]) and row["id"] not in seen,
                 "invalid or duplicate row identity")
        seen.add(row["id"])
        _require(row["split"] in ("train", "validation"), "only train/validation views supported")
        _require(type(row["features"]) is dict and type(row.get("groups", {})) is dict,
                 "features and groups must be objects")
        _require(all(v is None or type(v) in (str, bool, int, float)
                     for v in row.get("groups", {}).values()), "scalar group identities required")


def diagnose(path, *, sha256, max_rows=10000, max_findings=100):
    """Read/hash/validate one bounded view, then diagnose its ordered row prefix.

    Parsing and structural validation inspect the full bounded document, including
    rejecting TEST anywhere. max_rows limits diagnostic work, not parse cost/RAM.
    Finding counts describe unique content/group signatures, never all row pairs.
    """
    _require(isinstance(sha256, str) and re.fullmatch(r"[a-f0-9]{64}", sha256),
             "externally pinned SHA256 required")
    _require(type(max_rows) is int and 0 <= max_rows <= 100000
             and type(max_findings) is int and 0 <= max_findings <= 1000, "invalid scan limits")
    with Path(path).open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    _require(len(data) <= MAX_BYTES and hash_bytes(data) == sha256, "input size/hash mismatch")
    document = _json(data)
    _validate(document)
    fields, group_fields = document["feature_fields"], document["group_fields"]
    rows = document["rows"][:max_rows]
    partial = len(rows) < len(document["rows"])
    findings, finding_count = [], 0
    content, groups = {}, {key: {} for key in group_fields}
    repeated, overlaps, conflicts = set(), set(), set()
    group_overlaps = {key: set() for key in group_fields}
    group_known = dict.fromkeys(group_fields, 0)
    missing, nulls, incomplete, labeled, additional = 0, 0, 0, 0, 0
    splits = {split: 0 for split in ("train", "validation")}

    def finding(kind, references, *, field=None):
        nonlocal finding_count
        finding_count += 1
        if len(findings) >= max_findings:
            return
        item = {"kind": kind, "rows": references, "field": field,
                "interpretation": {
                    "MISSING_FEATURE": "Declared required feature is absent.",
                    "NULL_FEATURE": "Declared required feature is null.",
                    "EXACT_DUPLICATE": "Repeated selected features; review intended repetition.",
                    "SPLIT_CONTENT_OVERLAP": "Content crosses splits; causal leakage unproven.",
                    "GROUP_OVERLAP": "Declared group crosses splits; group semantics not verified.",
                    "LABEL_CONFLICT": "Labels differ for equal features; correct label unknown.",
                }[kind]}
        item["id"] = hash_bytes(canonical({"input": sha256, **item}))
        findings.append(item)

    for index, row in enumerate(rows):
        ref = {"id": row["id"], "split": row["split"], "index": index,
               "row_sha256": hash_bytes(canonical(row))}
        splits[row["split"]] += 1
        absent = [key for key in fields if key not in row["features"]]
        empty = [key for key in fields if key in row["features"] and row["features"][key] is None]
        missing += len(absent)
        nulls += len(empty)
        incomplete += bool(absent or empty)
        for key in absent:
            finding("MISSING_FEATURE", [ref], field=key)
        for key in empty:
            finding("NULL_FEATURE", [ref], field=key)
        for key in group_fields:
            value = row.get("groups", {}).get(key)
            if value is None:
                continue
            group_known[key] += 1
            signature = hash_bytes(canonical(value))
            previous = groups[key].setdefault(signature, {})
            other = previous.get("validation" if row["split"] == "train" else "train")
            if other and signature not in group_overlaps[key]:
                group_overlaps[key].add(signature)
                finding("GROUP_OVERLAP", [other, ref], field=key)
            previous.setdefault(row["split"], ref)
        if absent or empty:
            continue  # Missing features cannot form a meaningful complete-content signature.
        signature = hash_bytes(canonical({key: row["features"][key] for key in fields}))
        previous = content.get(signature)
        if previous is None:
            previous = content[signature] = {"first": ref, "splits": {}, "label": None}
        else:
            additional += 1
            if signature not in repeated:
                repeated.add(signature)
                finding("EXACT_DUPLICATE", [previous["first"], ref])
        other = previous["splits"].get("validation" if row["split"] == "train" else "train")
        if other and signature not in overlaps:
            overlaps.add(signature)
            finding("SPLIT_CONTENT_OVERLAP", [other, ref])
        previous["splits"].setdefault(row["split"], ref)
        if row.get("label") is not None:
            labeled += 1
            label = hash_bytes(canonical(row["label"]))
            prior = previous["label"]
            if prior is not None and prior[0] != label and signature not in conflicts:
                conflicts.add(signature)
                finding("LABEL_CONFLICT", [prior[1], ref])
            if prior is None:
                previous["label"] = (label, ref)

    complete_content = not partial and not incomplete
    both_splits = all(splits.values())
    coverage = []

    def check(name, status, metrics, scope):
        coverage.append({"name": name, "version": "1", "status": status if rows else "NOT_RUN",
                         "metrics": metrics, "scope": scope})

    check("completeness", "FAILED" if incomplete else "INCONCLUSIVE" if partial else "TESTED",
          {"missing_fields": missing, "null_fields": nulls, "incomplete_rows": incomplete},
          "Declared required features on scanned rows only.")
    check("duplicates", "INCONCLUSIVE" if repeated or not complete_content else "TESTED",
          {"groups": len(repeated), "additional_rows": additional},
          "Exact typed JSON equality of complete selected features; repetition may be intended.")
    check("split_content", "FAILED" if overlaps else "TESTED"
          if complete_content and both_splits else "INCONCLUSIVE", {"groups": len(overlaps)},
          "Exact content disjointness of scanned train/validation; not causal leakage proof.")
    for key in group_fields:
        known = group_known[key]
        status = "FAILED" if group_overlaps[key] else "UNSUPPORTED" if not known and not partial \
            else "TESTED" if not partial and known == len(rows) and both_splits else "INCONCLUSIVE"
        check("group:" + key, status,
              {"overlapping_groups": len(group_overlaps[key]), "known_rows": known,
               "unknown_rows": len(rows) - known}, "Declared group disjointness: " + key)
    if not group_fields:
        check("groups", "UNSUPPORTED", {}, "No group fields declared; independence unresolved.")
    label_status = "INCONCLUSIVE" if conflicts else "UNSUPPORTED" if not labeled and not partial \
        else "TESTED" if complete_content and labeled == len(rows) else "INCONCLUSIVE"
    check("labels", label_status, {"conflicting_groups": len(conflicts),
                                  "eligible_labeled_rows": labeled,
                                  "missing_or_null_labels": sum(r.get("label") is None
                                                                for r in rows),
                                  "ineligible_feature_rows": incomplete},
          "Known labels on complete identical selected features; no label truth or correction.")
    for name in ("near_duplicates", "preprocessing_leakage", "semantic_units",
                 "distribution_drift"):
        check(name, "NOT_RUN", {}, "Not implemented by this exact-content diagnostic pack.")
    return {"schema": "forge.dataset-diagnostics.v1", "input_sha256": sha256,
            "state": "PARTIAL" if partial else "COMPLETE",
            "scope": {"feature_fields": fields, "group_fields": group_fields,
                      "total_rows": len(document["rows"]), "scanned_rows": len(rows),
                      "split_rows": splits, "max_rows": max_rows, "max_findings": max_findings,
                      "selection": "INPUT_ORDER_PREFIX",
                      "structural_validation": "FULL_BOUNDED_INPUT"},
            "coverage": coverage, "findings": findings, "findings_total": finding_count,
            "findings_omitted": finding_count - len(findings),
            "scientific_qualification": "NOT_QUALIFIED"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--max-findings", type=int, default=100)
    args = parser.parse_args()
    try:
        print(json.dumps(diagnose(args.input, sha256=args.sha256, max_rows=args.max_rows,
                                  max_findings=args.max_findings), indent=2, allow_nan=False))
    except (ForgeError, OSError) as exc:
        parser.exit(2, f"dataset diagnosis failed: {exc}\n")


if __name__ == "__main__":
    main()
