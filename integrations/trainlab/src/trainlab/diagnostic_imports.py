"""Import local, pinned experiment records without running provider code."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

from .experiment_diagnostics import _number
from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _require, _text
from .runner import LabError, _constant, _pairs

INT64_MAX = 2**63 - 1
INT64_MIN = -(2**63)


def _document(path, pin):
    path = Path(path)
    _require(
        _hash(pin) and path.is_file() and not path.is_symlink(), "pinned regular file required"
    )
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(
        len(raw) <= MAX_BYTES and hashlib.sha256(raw).hexdigest() == pin,
        "diagnostic import content size/hash mismatch",
    )
    try:
        data = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid diagnostic import JSON") from exc
    _bytes(data)
    _require(type(data) is dict, "expected an object-shaped diagnostic export")
    return data


def _limit(record, max_events):
    _require(
        type(record) is list
        and len(record) <= 100000
        and type(max_events) is int
        and 1 <= max_events <= 10000,
        "unsupported import count or scan budget",
    )
    return record[:max_events]


def _integer(value):
    if type(value) is str and len(value) <= 20 and re.fullmatch(r"-?(?:0|[1-9][0-9]*)", value):
        value = int(value)
    _require(
        type(value) is int and INT64_MIN <= value <= INT64_MAX, "expected a signed 64-bit integer"
    )
    return value


def import_history(path, *, sha256, run_id, metric_key, max_events=10000):
    """Read one MLflow Get Metric History response without following pagination."""
    _require(_text(run_id) and _text(metric_key), "declared run and metric identity required")
    data = _document(path, sha256)
    _require(set(data) <= {"metrics", "next_page_token"}, "unknown metric response fields")
    token = data.get("next_page_token")
    _require(token is None or type(token) is str and len(token) <= 10000, "invalid page marker")
    metrics = data.get("metrics", [])
    rows, scopes = [], Counter()
    for idx, metric in enumerate(_limit(metrics, max_events)):
        needed = {"key", "value", "timestamp", "step"}
        optional = {"run_id", "dataset_name", "dataset_digest", "model_id"}
        _require(
            type(metric) is dict
            and needed <= set(metric) <= needed | optional
            and metric["key"] == metric_key
            and metric.get("run_id", run_id) == run_id
            and _number(metric["value"]),
            "invalid or cross-run metric",
        )
        scope = tuple(metric.get(k) for k in ("dataset_name", "dataset_digest", "model_id"))
        _require(all(value is None or _text(value) for value in scope), "invalid metric scope")
        step = _integer(metric["step"])
        stamp = _integer(metric["timestamp"])
        _require(stamp >= 0, "negative metric timestamp")
        scopes[scope] += 1
        rows.append(
            {
                "source_index": idx,
                "step": step,
                "value": metric["value"],
                "timestamp_ms": stamp,
                "scope": list(scope),
            }
        )
    complete = not token and len(metrics) == len(rows)
    return {
        "schema": "trainlab.external-diagnostic-import.v1",
        "format": "mlflow-metric-history",
        "source_sha256": sha256,
        "run_id": run_id,
        "metric_key": metric_key,
        "status": "TESTED" if complete and rows else "INCONCLUSIVE",
        "scopes": [
            {"dataset_name": scope[0], "dataset_digest": scope[1], "model_id": scope[2], "count": n}
            for scope, n in scopes.items()
        ],
        "rows": rows,
        "observations": {
            "scanned_rows": len(rows),
            "source_rows": len(metrics),
            "continuation_present": bool(token),
        },
        "boundary": "One local response. Run identity is caller-declared when absent from row.",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def import_trace(path, *, sha256, capture_id, max_events=10000):
    """Import complete CPU operator spans from a native PyTorch Chrome trace."""
    _require(_text(capture_id), "declared capture identity required")
    data = _document(path, sha256)
    _require(
        type(data.get("schemaVersion")) is int and data["schemaVersion"] == 1,
        "unsupported PyTorch trace export version",
    )
    events = data.get("traceEvents")
    rows, skipped, spans = [], Counter(), defaultdict(list)
    scanned = _limit(events, max_events)
    for idx, event in enumerate(scanned):
        _require(type(event) is dict and _text(event.get("ph")), "invalid trace event")
        phase, category = event["ph"], event.get("cat")
        _require(category is None or _text(category), "invalid trace category")
        if (phase, category) != ("X", "cpu_op"):
            skipped[phase, category] += 1
            continue
        _require(
            _text(event.get("name")) and _number(event.get("ts")) and _number(event.get("dur"), 0),
            "invalid CPU span",
        )
        pid, tid = _integer(event.get("pid")), _integer(event.get("tid"))
        span = {
            "source_index": idx,
            "name": event["name"],
            "process": pid,
            "thread": tid,
            "start_us": event["ts"],
            "duration_us": event["dur"],
        }
        rows.append(span)
        spans[span["name"]].append(span["duration_us"])
    complete = len(scanned) == len(events)
    summaries = [
        {"operator": name, "calls": len(durations), "inclusive_duration_us": math.fsum(durations)}
        for name, durations in sorted(spans.items())
    ]
    return {
        "schema": "trainlab.external-diagnostic-import.v1",
        "format": "pytorch-chrome-trace",
        "source_sha256": sha256,
        "capture_id": capture_id,
        "status": "TESTED" if complete and rows and not skipped else "INCONCLUSIVE",
        "rows": rows,
        "observations": {
            "source_events": len(events),
            "scanned_events": len(scanned),
            "omitted_events": len(events) - len(scanned),
            "unsupported_by_phase_category": [
                {"phase": p, "category": c, "events": n}
                for (p, c), n in sorted(skipped.items(), key=lambda x: (x[0][0], x[0][1] or ""))
            ],
            "inclusive_cpu_duration_us": math.fsum(r["duration_us"] for r in rows)
            if rows
            else None,
            "operators": summaries,
        },
        "boundary": "Inclusive CPU operator spans can overlap or nest. Units are microseconds.",
        "scientific_qualification": "NOT_QUALIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    formats = parser.add_subparsers(dest="format", required=True)
    history = formats.add_parser("mlflow")
    history.add_argument("--run-id", required=True)
    history.add_argument("--metric-key", required=True)
    trace = formats.add_parser("pytorch")
    trace.add_argument("--capture-id", required=True)
    for sub in (history, trace):
        sub.add_argument("--input", type=Path, required=True)
        sub.add_argument("--sha256", required=True)
        sub.add_argument("--max-events", type=int, default=10000)
    args = parser.parse_args()
    try:
        if args.format == "mlflow":
            value = import_history(
                args.input,
                sha256=args.sha256,
                max_events=args.max_events,
                run_id=args.run_id,
                metric_key=args.metric_key,
            )
        else:
            value = import_trace(
                args.input,
                sha256=args.sha256,
                max_events=args.max_events,
                capture_id=args.capture_id,
            )
    except (LabError, OSError) as exc:
        parser.exit(2, f"diagnostic import: {exc}\n")
    print(json.dumps(value, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
