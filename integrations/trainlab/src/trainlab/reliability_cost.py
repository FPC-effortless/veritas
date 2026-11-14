"""Replayable CPU session costs at declared query and complete-map reliability.

Hashes bind local evidence, not execution truth, preregistration or independence.
"""

from __future__ import annotations

import math
from pathlib import Path
from statistics import median

from .assessment_diagnostics import measured_quality_session
from .competence_panels import _bound, _sha, score_panel
from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _require, _rows, _text
from .resource_diagnostics import EXECUTION, _limits
from .runner import LabError, digest, read_json, write_json

FILES = (
    "panel.json",
    "session/assessment.json",
    "session/inputs.json",
    "session/run/receipt.json",
    "session/run/request.json",
    "session/run/limits-applied.json",
    "session/run/stdout.log",
    "session/run/stderr.log",
    "session/run/predictions.json",
)
METRICS = ("query_accuracy", "map_accuracy")


def _inputs(panel, inputs):
    ids = _rows(inputs, "input")
    rows = panel["request"]["rows"]
    _require(ids == [r["id"] for r in rows], "input IDs/order differ from panel")
    _require(
        all(_sha(v["input"]) == r["input_sha256"] for v, r in zip(inputs, rows)),
        "input content differs from frozen panel",
    )
    return [{"id": c["id"], "answer": c["expected"]} for c in panel["cases"]]


def _file(root, name):
    path = root / name
    _require(
        all(not p.is_symlink() for p in [path, *path.parents]),
        "symlink in evidence path",
    )
    _require(path.resolve().is_relative_to(root), "evidence path escapes root")
    if path.exists():
        _require(path.is_file() and path.stat().st_size <= 64 * 1024**2, "invalid evidence file")
        return digest(path)
    return None


def run_panel_session(command, root, *, cwd, panel, panel_sha256, inputs, operations, limits):
    """Freeze the panel before running one trusted synchronous Linux CPU command.

    Preparation, scoring and replay are excluded from the inherited session timer.
    Interrupted supervisors may leave raw evidence without a finalized manifest.
    """
    _bound(panel, panel_sha256)
    expected = _inputs(panel, inputs)
    _require(_text(operations), "operation semantics required")
    _limits(limits)
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_json(
        root / "panel.json",
        {
            "panel": panel,
            "panel_sha256": panel_sha256,
            "operations": operations,
        },
    )
    measured_quality_session(
        command,
        root / "session",
        cwd=cwd,
        identities=panel["request"]["identities"],
        inputs=inputs,
        expected=expected,
        semantics={"query_mode": panel["query_mode"], "operations": operations},
        limits=limits,
    )
    write_json(
        root / "manifest.json",
        {
            "schema": "trainlab.panel-session-manifest.v1",
            "files": {name: _file(root, name) for name in FILES},
        },
    )
    return read_panel_session(root, digest(root / "manifest.json"))


def read_panel_session(root, manifest_sha256):
    """Verify an external manifest pin and recompute both metrics without execution.

    Ordinary failed commands retain elapsed cost and no quality point. Corrupt or
    inconsistent evidence raises LabError; it cannot silently become a failed run.
    """
    root = Path(root).absolute()
    _require(
        _hash(manifest_sha256) and _file(root, "manifest.json") == manifest_sha256,
        "manifest hash mismatch",
    )
    try:
        manifest = read_json(root / "manifest.json", limit=MAX_BYTES)
        _require(
            type(manifest) is dict
            and set(manifest) == {"schema", "files"}
            and manifest["schema"] == "trainlab.panel-session-manifest.v1"
            and type(manifest["files"]) is dict
            and set(manifest["files"]) == set(FILES),
            "invalid session manifest",
        )
        pins = manifest["files"]
        for name, pin in pins.items():
            _require(
                (pin is None or _hash(pin)) and _file(root, name) == pin,
                "artifact missing, changed or unexpectedly present",
            )
        _require(all(pins[n] for n in FILES[:5]), "required evidence absent")
        envelope = read_json(root / "panel.json", limit=MAX_BYTES)
        _require(
            type(envelope) is dict
            and set(envelope) == {"panel", "panel_sha256", "operations"}
            and _text(envelope["operations"]),
            "invalid frozen panel envelope",
        )
        panel, pin = envelope["panel"], envelope["panel_sha256"]
        _bound(panel, pin)
        inputs = read_json(root / "session/inputs.json", limit=MAX_BYTES)
        expected = _inputs(panel, inputs)
        assessment = read_json(root / "session/assessment.json", limit=MAX_BYTES)
        receipt = read_json(root / "session/run/receipt.json", limit=MAX_BYTES)
        request = read_json(root / "session/run/request.json", limit=MAX_BYTES)
        semantics = {"query_mode": panel["query_mode"], "operations": envelope["operations"]}
        workload = _sha([inputs, expected, semantics, "canonical-json-exact-query-accuracy-v1"])
        identities = panel["request"]["identities"]
        _require(
            assessment["schema"] == "trainlab.assessment-diagnostics.v1"
            and assessment["kind"] == "measured_quality"
            and receipt["schema"] == "trainlab.resource-session.v1"
            and _bytes(assessment["receipt"]) == _bytes(receipt)
            and assessment["receipt_sha256"] == pins["session/run/receipt.json"]
            and assessment["expected_sha256"] == _sha(expected)
            and assessment["query_semantics"] == semantics
            and receipt["identities"] == request["identities"] == identities
            and receipt["workload_sha256"] == request["workload_sha256"] == workload,
            "session/panel binding mismatch",
        )
        _limits(receipt["limits"])
        _require(
            receipt["hardware_sha256"] == _sha(receipt["hardware"])
            and receipt["boundary_sha256"]
            == _sha([receipt["boundary"], receipt["limits"], receipt["execution"]])
            and receipt["limits"] == request["limits"]
            and receipt["execution"] == request["execution"] == EXECUTION,
            "resource context mismatch",
        )
        seconds = receipt["wall_seconds"]
        _require(
            type(seconds) in (int, float) and math.isfinite(seconds) and seconds >= 0,
            "finite elapsed cost required",
        )
        _require(
            set(receipt["artifacts"]) == {"stdout.log", "stderr.log", "limits-applied.json"},
            "receipt artifact inventory mismatch",
        )
        for name, artifact_pin in receipt["artifacts"].items():
            _require(
                name in ("stdout.log", "stderr.log", "limits-applied.json")
                and artifact_pin == pins["session/run/" + name],
                "receipt artifact mismatch",
            )
        complete = assessment["status"] == "TESTED"
        observations = []
        if complete:
            _require(
                receipt["state"] == "SUCCEEDED"
                and receipt["cost_coverage"] == "MEASURED"
                and receipt["limits_applied"] is True
                and receipt["request_unchanged"] is True
                and receipt["request_sha256"] == pins["session/run/request.json"]
                and all(pins.values())
                and assessment["scoring_error"] is None
                and assessment["predictions_sha256"] == pins["session/run/predictions.json"],
                "complete-session evidence missing",
            )
            predictions = read_json(root / "session/run/predictions.json", limit=MAX_BYTES)
            _require(
                _rows(predictions, "answer") == [r["id"] for r in expected],
                "prediction IDs/order mismatch",
            )
            observations = [
                {"id": r["id"], "status": "observed", "value": r["answer"]} for r in predictions
            ]
        else:
            _require(
                assessment["status"] == "INCONCLUSIVE"
                and assessment["point"] is None
                and assessment["quality"] is None,
                "inconsistent failed-session assessment",
            )
        competence = score_panel(panel, observations, panel_sha256=pin)
        metrics = {k: competence["report"]["overall"][k] for k in METRICS}
        # Model/code/configuration identities differ across arms. Actual inputs,
        # expected outputs, map membership and declared semantics must not differ.
        context = {k: v for k, v in panel.items() if k != "request"}
        context["request"] = {k: v for k, v in panel["request"].items() if k != "identities"}
        contexts = {k: _sha([context, envelope["operations"], k, "exact-json-v1"]) for k in METRICS}
        points = {k: None for k in METRICS}
        if complete:
            base_point = {
                "id": "session",
                "quality": metrics["query_accuracy"],
                "session_seconds": seconds,
                "cost_status": "MEASURED",
                "workload_sha256": workload,
                "hardware_sha256": receipt["hardware_sha256"],
                "boundary_sha256": receipt["boundary_sha256"],
            }
            _require(
                assessment["quality"] == metrics["query_accuracy"]
                and _bytes({**assessment["point"], "id": "session"}) == _bytes(base_point),
                "saved query quality/cost disagrees with replay",
            )
            points = {
                k: {**base_point, "quality": metrics[k], "workload_sha256": contexts[k]}
                for k in METRICS
            }
        # Check again after parsing to reject ordinary concurrent file changes.
        _require(
            _file(root, "manifest.json") == manifest_sha256
            and all(_file(root, n) == p for n, p in pins.items()),
            "evidence changed during replay",
        )
        return {
            "schema": "trainlab.panel-session.v1",
            "manifest_sha256": manifest_sha256,
            "receipt_sha256": pins["session/run/receipt.json"],
            "complete": complete,
            "wall_seconds": seconds,
            "identities": identities,
            "metrics": metrics,
            "competence_status": competence["report"]["status"],
            "competence": competence,
            "contexts": {
                k: [contexts[k], receipt["hardware_sha256"], receipt["boundary_sha256"]]
                for k in METRICS
            },
            "points": points,
            "scientific_qualification": "NOT_QUALIFIED",
        }
    except (KeyError, TypeError, ValueError, OSError) as exc:
        raise LabError("malformed session evidence") from exc


def compare_at_reliability(records, *, required_arms, required_repeats, metric, quality_floor):
    """Descriptive median CPU cost, conditional on every declared repeat passing.

    Missing/duplicate executions are rejected; failed executions block ranking.
    Repeats measure execution variation, not independent training seeds or retries.
    """
    _bytes([records, required_arms, required_repeats, metric, quality_floor])
    _require(
        type(required_arms) is list
        and 2 <= len(required_arms) <= 16
        and all(_text(a) for a in required_arms)
        and len(set(required_arms)) == len(required_arms),
        "two to sixteen distinct arms required",
    )
    _require(
        type(required_repeats) is list
        and 1 <= len(required_repeats) <= 16
        and all(type(r) is int and 0 <= r <= 10**9 for r in required_repeats)
        and len(set(required_repeats)) == len(required_repeats),
        "distinct repeat IDs required",
    )
    _require(
        metric in METRICS and type(quality_floor) in (int, float) and 0 < quality_floor <= 1,
        "metric and positive reliability floor required",
    )
    _require(type(records) is list and 1 <= len(records) <= 256, "bounded records required")
    pairs, manifests, receipts, sessions = set(), set(), set(), {}
    for row in records:
        _require(
            type(row) is dict
            and set(row) == {"arm", "repeat", "root", "manifest_sha256"}
            and _text(row["arm"])
            and row["arm"] in required_arms
            and type(row["repeat"]) is int
            and row["repeat"] in required_repeats
            and _text(row["root"])
            and Path(row["root"]).is_absolute()
            and _hash(row["manifest_sha256"]),
            "invalid session reference",
        )
        pair = (row["arm"], row["repeat"])
        _require(
            pair not in pairs and row["manifest_sha256"] not in manifests,
            "duplicate repeat or reused session",
        )
        pairs.add(pair)
        manifests.add(row["manifest_sha256"])
    _require(
        pairs == {(a, r) for a in required_arms for r in required_repeats},
        "complete declared arm/repeat panel required",
    )
    for row in records:
        session = read_panel_session(row["root"], row["manifest_sha256"])
        _require(session["receipt_sha256"] not in receipts, "reused execution receipt")
        receipts.add(session["receipt_sha256"])
        sessions[(row["arm"], row["repeat"])] = session
    arm_reports = {}
    for arm in required_arms:
        runs = [sessions[(arm, r)] for r in required_repeats]
        _require(
            all(s["identities"] == runs[0]["identities"] for s in runs),
            "arm identities changed across repeats",
        )
        times = [s["wall_seconds"] for s in runs]
        complete = all(s["complete"] for s in runs)
        arm_reports[arm] = {
            "runs": [{"repeat": r, **s} for r, s in zip(required_repeats, runs)],
            "complete": complete,
            "observed_seconds_total": sum(times),
            "raw_seconds": times,
            "median_seconds": median(times) if complete else None,
            "min_seconds": min(times) if complete else None,
            "max_seconds": max(times) if complete else None,
            "meets_reliability": all(
                s["competence_status"] == "TESTED" and s["metrics"][metric] >= quality_floor
                for s in runs
            )
            if complete
            else None,
        }
    matched = len({_bytes(s["contexts"][metric]) for s in sessions.values()}) == 1
    complete = all(s["complete"] for s in sessions.values())
    eligible, lowest = None, None
    if matched and complete:
        eligible = [a for a in required_arms if arm_reports[a]["meets_reliability"]]
        minimum = min((arm_reports[a]["median_seconds"] for a in eligible), default=None)
        lowest = [a for a in eligible if arm_reports[a]["median_seconds"] == minimum]
    return {
        "schema": "trainlab.reliability-cost.v1",
        "status": "FAILED" if not matched else "TESTED" if complete else "INCONCLUSIVE",
        "metric": metric,
        "quality_floor": quality_floor,
        "matched_context": matched,
        "required_arms": required_arms,
        "required_repeats": required_repeats,
        "records_sha256": _sha(records),
        "arms": arm_reports,
        "eligible_arms": eligible,
        "lowest_median_cost_arms": lowest,
        "scientific_qualification": "NOT_QUALIFIED",
        "uncertainty": "NOT_ESTIMATED",
        "scope": "Declared panel and CPU session boundary only",
    }
