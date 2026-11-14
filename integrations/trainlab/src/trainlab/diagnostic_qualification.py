"""Replay diagnostic sensitivity, localization and overhead on a declared fault panel."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from statistics import median

from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _require, _text
from .runner import LabError, _constant, _pairs

COUNTS = (
    "true_positive",
    "false_positive",
    "true_negative",
    "false_negative",
    "unobserved",
    "unadjudicated",
    "detected_checks",
    "checked_fault_checks",
)
CHECK_STATES = ("CHECKED", "INCONCLUSIVE", "UNSUPPORTED", "NOT_RUN", "EXECUTION_FAILED")


def _pinned(path, pin):
    path = Path(path)
    _require(
        _hash(pin)
        and not any(p.is_symlink() for p in (path, *path.absolute().parents))
        and path.is_file(),
        "pinned regular file required",
    )
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(
        len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == pin,
        "qualification document size or hash mismatch",
    )
    try:
        document = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid qualification document") from exc
    _bytes(document)
    return document


def _objects(rows, limit, *, empty=False):
    _require(
        type(rows) is list
        and (empty or rows)
        and len(rows) <= limit
        and all(type(row) is dict for row in rows),
        "expected bounded object rows",
    )


def _panel(doc):
    _require(
        type(doc) is dict
        and set(doc) == {"schema", "repeats", "cases"}
        and doc["schema"] == "trainlab.diagnostic-fault-panel.v1",
        "invalid fault panel",
    )
    repeats = doc["repeats"]
    _require(
        type(repeats) is list
        and 1 <= len(repeats) <= 64
        and all(type(i) is int and 0 <= i <= 10**9 for i in repeats)
        and len(set(repeats)) == len(repeats),
        "invalid repeat identities",
    )
    _objects(doc["cases"], 256)
    cases = {}
    for row in doc["cases"]:
        _require(
            set(row) == {"id", "workload_sha256", "targets"}
            and _text(row["id"])
            and row["id"] not in cases
            and _hash(row["workload_sha256"]),
            "invalid or duplicate case",
        )
        _objects(row["targets"], 1000)
        targets = {}
        for t in row["targets"]:
            _require(
                set(t) == {"check", "location", "fault"}
                and _text(t["check"])
                and _text(t["location"])
                and type(t["fault"]) is bool,
                "invalid exact-location target",
            )
            by_check = targets.setdefault(t["check"], {})
            _require(t["location"] not in by_check, "duplicate target location")
            by_check[t["location"]] = t["fault"]
        cases[row["id"]] = (row["workload_sha256"], targets)
    _require(
        sum(len(t) for _, groups in cases.values() for t in groups.values()) * len(repeats)
        <= 100000,
        "fault panel exceeds scoring budget",
    )
    return repeats, cases


def _times(row):
    if row is None:
        return None
    durations = {"baseline_ns", "diagnostic_ns"}
    pins = {"baseline_work_sha256", "diagnostic_work_sha256", "hardware_sha256", "boundary_sha256"}
    _require(
        type(row) is dict
        and set(row) == durations | pins
        and all(type(row[k]) is int and 0 < row[k] <= 10**15 for k in durations)
        and all(_hash(row[k]) for k in pins),
        "invalid matched-work timings",
    )
    return row


def _runs(doc, repeats, cases):
    _require(
        type(doc) is dict
        and set(doc) == {"schema", "runs"}
        and doc["schema"] == "trainlab.diagnostic-fault-observations.v1",
        "invalid observations",
    )
    _objects(doc["runs"], 16384, empty=True)
    result = {}
    for row in doc["runs"]:
        _require(
            set(row) == {"case", "repeat", "workload_sha256", "checks", "timing"}
            and _text(row["case"])
            and row["case"] in cases
            and type(row["repeat"]) is int
            and row["repeat"] in repeats
            and row["workload_sha256"] == cases[row["case"]][0],
            "unexpected case, repeat or workload",
        )
        key = row["case"], row["repeat"]
        _require(key not in result, "duplicate case/repeat")
        _objects(row["checks"], 1000, empty=True)
        checks = {}
        declared = cases[row["case"]][1]
        for check in row["checks"]:
            _require(
                set(check) == {"name", "status", "locations"}
                and _text(check["name"])
                and check["name"] in declared
                and check["name"] not in checks
                and check["status"] in CHECK_STATES,
                "invalid, undeclared or duplicate check",
            )
            loc = check["locations"]
            _require(
                type(loc) is list
                and len(loc) <= 1000
                and all(_text(i) for i in loc)
                and len(set(loc)) == len(loc),
                "invalid or duplicate finding locations",
            )
            checks[check["name"]] = check["status"], set(loc)
        result[key] = checks, _times(row["timing"])
    return result


def _outcomes(targets, observed):
    counts = dict.fromkeys(COUNTS, 0)
    for name, expected in targets.items():
        state, findings = observed.get(name, ("NOT_RUN", set()))
        counts["unadjudicated"] += len(findings - expected.keys())
        if any(expected.values()) and state == "CHECKED":
            counts["checked_fault_checks"] += 1
            counts["detected_checks"] += bool(findings)
        for location, fault in expected.items():
            predicted = location in findings
            if not predicted and state != "CHECKED":
                counts["unobserved"] += 1
            elif predicted:
                counts["true_positive" if fault else "false_positive"] += 1
            else:
                counts["false_negative" if fault else "true_negative"] += 1
    return counts


def _overhead(rows, required_repeats):
    matched = [t for t in rows if t and t["baseline_work_sha256"] == t["diagnostic_work_sha256"]]
    context = {(t["hardware_sha256"], t["boundary_sha256"]) for t in matched}
    comparable = len(matched) == required_repeats and len(context) == 1
    differences = [t["diagnostic_ns"] - t["baseline_ns"] for t in matched] if comparable else []
    ratios = [t["diagnostic_ns"] / t["baseline_ns"] for t in matched] if comparable else []
    return {
        "status": "TESTED" if comparable else "INCONCLUSIVE",
        "matched_repeats": len(matched),
        "required_repeats": required_repeats,
        "median_difference_ns": median(differences) if differences else None,
        "difference_range_ns": [min(differences), max(differences)] if differences else None,
        "median_ratio": median(ratios) if ratios else None,
    }


def _rate(numerator, denominator):
    return {
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator if denominator else None,
    }


def score(panel_path, observations_path, *, panel_sha256, observations_sha256):
    """Verify exact inputs and score adjudicated locations with explicit coverage."""
    repeats, cases = _panel(_pinned(panel_path, panel_sha256))
    runs = _runs(_pinned(observations_path, observations_sha256), repeats, cases)
    counts = dict.fromkeys(COUNTS, 0)
    rows, overhead, incomplete = [], {}, False
    for case, (_, targets) in cases.items():
        timing_rows = []
        for repeat in repeats:
            observed, timing = runs.get((case, repeat), ({}, None))
            scores = _outcomes(targets, observed)
            missing = sorted(
                k for k in targets if observed.get(k, ("NOT_RUN", set()))[0] != "CHECKED"
            )
            incomplete |= bool(missing or scores["unadjudicated"])
            for key, value in scores.items():
                counts[key] += value
            rows.append(
                {
                    "case": case,
                    "repeat": repeat,
                    "counts": scores,
                    "incomplete_checks": missing,
                    "timing": timing,
                }
            )
            timing_rows.append(timing)
        overhead[case] = _overhead(timing_rows, len(repeats))
        incomplete |= overhead[case]["status"] != "TESTED"
    tp, fp, tn, fn = (
        counts[k] for k in ("true_positive", "false_positive", "true_negative", "false_negative")
    )
    return {
        "schema": "trainlab.diagnostic-qualification.v1",
        "status": "INCONCLUSIVE" if incomplete else "TESTED",
        "panel_sha256": panel_sha256,
        "observations_sha256": observations_sha256,
        "counts": counts,
        "runs": rows,
        "overhead": overhead,
        "rates": {
            "detection_rate": _rate(counts["detected_checks"], counts["checked_fault_checks"]),
            "fault_location_recall": _rate(tp, tp + fn),
            "localization_precision": _rate(tp, tp + fp),
            "false_alarm_rate": _rate(fp, fp + tn),
        },
        "scope": "Adjudicated locations on this panel. Repeats reuse the same cases.",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--panel", type=Path, required=True)
    parser.add_argument("--panel-sha256", required=True)
    parser.add_argument("--observations", type=Path, required=True)
    parser.add_argument("--observations-sha256", required=True)
    args = parser.parse_args()
    try:
        result = score(
            args.panel,
            args.observations,
            panel_sha256=args.panel_sha256,
            observations_sha256=args.observations_sha256,
        )
    except (LabError, OSError) as exc:
        parser.exit(2, f"qualification error: {exc}\n")
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
