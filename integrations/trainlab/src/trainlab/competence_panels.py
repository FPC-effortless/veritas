"""Scoped competence predicates over a frozen, declared evaluation panel.

Correctness evidence is not proof of adequate tuning, independent data or model truth.
"""

from __future__ import annotations

import copy
import hashlib
from collections import defaultdict

from .experiment_diagnostics import _items, _seeds
from .prediction_artifacts import _bytes, _hash, _request, _require, _text, read_predictions


def _sha(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _validate(panel):
    _bytes(panel)
    _require(
        type(panel) is dict
        and set(panel)
        == {
            "schema",
            "request",
            "cases",
            "required_seeds",
            "required_templates",
            "query_mode",
            "thresholds",
        }
        and panel["schema"] == "trainlab.competence-panel.v1",
        "invalid panel schema",
    )
    request, cases = panel["request"], panel["cases"]
    _request(request)
    _items(cases)
    _seeds(panel["required_seeds"])
    templates = panel["required_templates"]
    _require(
        type(templates) is list
        and 1 <= len(templates) <= 100
        and all(_text(t) for t in templates)
        and len(set(templates)) == len(templates),
        "distinct required templates required",
    )
    thresholds = panel["thresholds"]
    _require(
        type(thresholds) is dict
        and set(thresholds) == {"query_accuracy", "map_accuracy"}
        and all(type(v) in (int, float) and 0 < v <= 1 for v in thresholds.values()),
        "explicit positive query/map thresholds required",
    )
    _require(panel["query_mode"] in ("fresh_replay", "continuous"), "invalid query mode")
    mode = "stateless" if panel["query_mode"] == "fresh_replay" else "sequential"
    _require(request["state"]["mode"] == mode, "query mode disagrees with request state mode")
    _require(
        [r["id"] for r in cases] == [r["id"] for r in request["rows"]],
        "panel must cover exact request IDs/order",
    )
    maps, cells, metadata = defaultdict(set), set(), {}
    for case in cases:
        _require(
            set(case)
            == {"id", "seed", "map_id", "group", "template", "payload", "query_id", "expected"}
            and all(_text(case[k]) for k in ("map_id", "group", "template", "payload", "query_id"))
            and type(case["seed"]) is int
            and case["seed"] in panel["required_seeds"]
            and case["template"] in templates,
            "invalid panel case",
        )
        key = (case["seed"], case["map_id"])
        _require(case["query_id"] not in maps[key], "duplicate map query")
        maps[key].add(case["query_id"])
        meta = [case[k] for k in ("group", "template", "payload")]
        _require(
            metadata.setdefault(case["map_id"], meta) == meta,
            "map metadata must agree within and across seeds",
        )
        cells.add((case["seed"], case["template"]))
    _require(
        cells == {(s, t) for s in panel["required_seeds"] for t in templates},
        "required seed/template cell absent from panel",
    )
    reference = panel["required_seeds"][0]
    map_ids = {m for s, m in maps if s == reference}
    for seed in panel["required_seeds"]:
        _require(
            {m for s, m in maps if s == seed} == map_ids,
            "each seed must cover the same declared map set",
        )
        _require(
            all(maps[(seed, m)] == maps[(reference, m)] for m in map_ids),
            "each seed must cover the same map members",
        )


def freeze_panel(request, cases, *, required_seeds, required_templates, query_mode, thresholds):
    """Create a content-bound plan; chronological preregistration is not attested."""
    panel = {
        "schema": "trainlab.competence-panel.v1",
        "request": request,
        "cases": cases,
        "required_seeds": required_seeds,
        "required_templates": required_templates,
        "query_mode": query_mode,
        "thresholds": thresholds,
    }
    _validate(panel)
    return {"panel": copy.deepcopy(panel), "panel_sha256": _sha(panel)}


def _bound(panel, panel_sha256):
    _require(_hash(panel_sha256) and _sha(panel) == panel_sha256, "panel hash mismatch")
    _validate(panel)


def _score(panel, observations, panel_sha256, source):
    _require(
        type(observations) is list and len(observations) <= 10000, "bounded observations required"
    )
    _bytes(observations)
    expected_ids = {r["id"] for r in panel["cases"]}
    lookup = {}
    for row in observations:
        _require(
            type(row) is dict
            and set(row) == {"id", "status", "value"}
            and _text(row["id"])
            and row["id"] in expected_ids
            and row["id"] not in lookup
            and row["status"] in ("observed", "missing", "failed")
            and (row["status"] == "observed" or row["value"] is None),
            "invalid, duplicate or unexpected observation",
        )
        lookup[row["id"]] = row
    outcomes, missing, failed = {}, [], []
    by_cell = defaultdict(list)
    for case in panel["cases"]:
        by_cell[(case["seed"], case["template"])].append(case)
        observation = lookup.get(case["id"], {"status": "missing", "value": None})
        if observation["status"] == "observed":
            outcomes[case["id"]] = _bytes(observation["value"]) == _bytes(case["expected"])
        else:
            outcomes[case["id"]] = None
            (failed if observation["status"] == "failed" else missing).append(case["id"])

    def summary(cases):
        values = [outcomes[r["id"]] for r in cases]
        correct, unknown = values.count(True), values.count(None)
        maps = defaultdict(list)
        for case in cases:
            maps[(case["seed"], case["map_id"])].append(outcomes[case["id"]])
        good_maps = sum(all(v is True for v in vals) for vals in maps.values())
        bad_maps = sum(any(v is False for v in vals) for vals in maps.values())
        total, total_maps = len(values), len(maps)
        return {
            "queries": total,
            "observed": total - unknown,
            "correct": correct,
            "wrong": total - unknown - correct,
            "unobserved": unknown,
            "query_accuracy": correct / total if not unknown else None,
            "query_lower_bound": correct / total,
            "query_upper_bound": (correct + unknown) / total,
            "maps": total_maps,
            "correct_maps": good_maps,
            "failed_maps": bad_maps,
            "unresolved_maps": total_maps - good_maps - bad_maps,
            "map_accuracy": good_maps / total_maps if good_maps + bad_maps == total_maps else None,
            "map_lower_bound": good_maps / total_maps,
            "map_upper_bound": (total_maps - bad_maps) / total_maps,
        }

    cells = []
    for seed in panel["required_seeds"]:
        for template in panel["required_templates"]:
            metrics = summary(by_cell[(seed, template)])
            impossible = (
                metrics["query_upper_bound"] < panel["thresholds"]["query_accuracy"]
                or metrics["map_upper_bound"] < panel["thresholds"]["map_accuracy"]
            )
            status = (
                "FAILED" if impossible else "INCONCLUSIVE" if metrics["unobserved"] else "TESTED"
            )
            cells.append({"seed": seed, "template": template, "status": status, **metrics})
    statuses = {c["status"] for c in cells}
    status = (
        "FAILED"
        if "FAILED" in statuses
        else "INCONCLUSIVE"
        if "INCONCLUSIVE" in statuses
        else "TESTED"
    )
    report = {
        "schema": "trainlab.competence-report.v1",
        "status": status,
        "panel_sha256": panel_sha256,
        "request_sha256": _sha(panel["request"]),
        "observations_sha256": _sha(observations),
        "source": source,
        "identities": panel["request"]["identities"],
        "query_mode": panel["query_mode"],
        "thresholds": panel["thresholds"],
        "overall": summary(panel["cases"]),
        "cells": cells,
        "wrong_ids": [rid for rid, value in outcomes.items() if value is False],
        "missing_ids": missing,
        "failed_ids": failed,
        "scientific_qualification": "NOT_QUALIFIED",
        "independence": "DECLARED_NOT_VERIFIED",
        "preregistration": "NOT_ATTESTED",
        "uncertainty": "NOT_ESTIMATED",
        "scope": "Declared panel and thresholds only; not adequate tuning or general competence.",
    }
    pin = _sha(report)
    return copy.deepcopy(
        {
            "report": report,
            "report_sha256": pin,
            "competence_reference": {
                "status": {"TESTED": "supported", "FAILED": "failed", "INCONCLUSIVE": "unknown"}[
                    status
                ],
                "evidence_sha256": pin,
            },
        }
    )


def score_panel(panel, observations, *, panel_sha256):
    """Score trusted supplied observations, retaining missing/failed queries explicitly."""
    _bound(panel, panel_sha256)
    return _score(panel, observations, panel_sha256, {"kind": "SUPPLIED_OBSERVATIONS"})


def score_artifact(path, artifact_sha256, panel, *, panel_sha256):
    """Reuse a complete saved prediction artifact through existing exact-binding checks."""
    _bound(panel, panel_sha256)
    predictions = read_predictions(path, artifact_sha256, panel["request"])
    observations = [
        {"id": r["id"], "status": "observed", "value": r["output"]} for r in predictions
    ]
    return _score(
        panel,
        observations,
        panel_sha256,
        {
            "kind": "VERIFIED_ARTIFACT_BINDING",
            "artifact_sha256": artifact_sha256,
            "execution": "NOT_ATTESTED",
        },
    )
