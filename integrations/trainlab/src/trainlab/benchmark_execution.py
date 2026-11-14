"""Execute scoped benchmark references and compare pinned paired outcomes."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path

from .experiment_diagnostics import _items, _number
from .prediction_artifacts import _bytes, _hash, _require, _text
from .research_diagnostics import Adapter, BudgetExceeded, Diagnostic, Workbench
from .runner import LabError, write_json

_ARMS = ("reference_a", "reference_b", "shortcut")
_SIDES = ("original", "intervened")
_ROW_FIELDS = {
    "id",
    "group",
    "original",
    "intervened",
    "expected_original",
    "expected_intervened",
    "expect_change",
}


def _canonical(value):
    _bytes(value)
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    except UnicodeError as exc:
        raise LabError("finite JSON Unicode scalar values required") from exc


def _digest(value):
    return hashlib.sha256(_canonical(value)).hexdigest()


def freeze_panel(
    rows,
    *,
    source_sha256,
    minimum_changed_groups,
    minimum_invariant_groups,
    maximum_shortcut_accuracy,
):
    """Bind cases, distinct declared implementations and observed-scope thresholds."""
    _items(rows, maximum=64)
    _require(
        type(source_sha256) is dict
        and set(source_sha256) == set(_ARMS)
        and all(_hash(value) for value in source_sha256.values())
        and len(set(source_sha256.values())) == len(_ARMS),
        "three distinct declared source digests required",
    )
    _require(
        all(
            type(count) is int and 1 <= count <= 64
            for count in (minimum_changed_groups, minimum_invariant_groups)
        )
        and _number(maximum_shortcut_accuracy, 0, 1)
        and maximum_shortcut_accuracy < 1,
        "bounded prespecified coverage and shortcut thresholds required",
    )
    for row in rows:
        _require(
            set(row) == _ROW_FIELDS
            and _text(row["group"])
            and type(row["expect_change"]) is bool
            and _canonical(row["original"]) != _canonical(row["intervened"])
            and (_canonical(row["expected_original"]) != _canonical(row["expected_intervened"]))
            == row["expect_change"],
            "invalid case, conflicting expected sensitivity, or unmodified input",
        )
    panel = {
        "rows": json.loads(_canonical(rows)),
        "source_sha256": dict(source_sha256),
        "minimum_changed_groups": minimum_changed_groups,
        "minimum_invariant_groups": minimum_invariant_groups,
        "maximum_shortcut_accuracy": maximum_shortcut_accuracy,
    }
    return {"panel": panel, "panel_sha256": _digest(panel)}


def _score(panel, observed):
    outcomes = {
        (row["case"], row["side"], row["arm"]): row["output_sha256"]
        for row in observed
        if row["state"] == "OBSERVED"
    }
    findings = []
    verified = {"changed": set(), "invariant": set()}
    possible = {"changed": set(), "invariant": set()}
    shortcut_scored = shortcut_correct = 0
    cases = panel["rows"]
    for row in cases:
        identity = row["id"]
        agrees = True
        contradicted = False
        for side in _SIDES:
            expected = _digest(row["expected_" + side])
            a, b, control = (outcomes.get((identity, side, arm)) for arm in _ARMS)
            if a is not None and b is not None and a != b:
                findings.append({"kind": "REFERENCE_PARITY", "case": identity, "side": side})
            for arm, result in zip(_ARMS[:2], (a, b), strict=True):
                if result is not None and result != expected:
                    contradicted = True
                    findings.append(
                        {
                            "kind": "REFERENCE_EXPECTATION",
                            "case": identity,
                            "side": side,
                            "arm": arm,
                        }
                    )
            agrees = agrees and a == b == expected
            if control is not None:
                shortcut_scored += 1
                shortcut_correct += control == expected
        kind = "changed" if row["expect_change"] else "invariant"
        if agrees:
            verified[kind].add(row["group"])
        if not contradicted:
            possible[kind].add(row["group"])
    expected_invocations = len(cases) * len(_ARMS) * len(_SIDES)
    shortcut_total = len(cases) * len(_SIDES)
    complete = len(outcomes) == expected_invocations
    accuracy = shortcut_correct / shortcut_total if shortcut_scored == shortcut_total else None
    if shortcut_correct / shortcut_total > panel["maximum_shortcut_accuracy"]:
        findings.append({"kind": "SHORTCUT_ABOVE_CEILING"})
    for kind, groups in possible.items():
        if len(groups) < panel[f"minimum_{kind}_groups"]:
            findings.append({"kind": f"INSUFFICIENT_{kind.upper()}_GROUPS"})
    return findings, {
        "observed_invocations": len(outcomes),
        "expected_invocations": expected_invocations,
        "verified_changed_groups": len(verified["changed"]),
        "verified_invariant_groups": len(verified["invariant"]),
        "possible_changed_groups": len(possible["changed"]),
        "possible_invariant_groups": len(possible["invariant"]),
        "observed_shortcut_correct": shortcut_correct,
        "observed_shortcut_total": shortcut_scored,
        "shortcut_accuracy": accuracy,
        "complete": complete,
    }


def execute(root, arms, *, panel, panel_sha256, max_calls=384, max_seconds=30):
    """Execute trusted, stateless callbacks on isolated inputs of a pinned panel."""
    keys = {
        "rows",
        "source_sha256",
        "minimum_changed_groups",
        "minimum_invariant_groups",
        "maximum_shortcut_accuracy",
    }
    _require(
        type(panel) is dict
        and set(panel) == keys
        and _hash(panel_sha256)
        and _digest(panel) == panel_sha256,
        "benchmark panel pin mismatch",
    )
    panel = freeze_panel(**panel)["panel"]
    _require(
        type(arms) is dict
        and set(arms) == set(_ARMS)
        and all(callable(arm) for arm in arms.values())
        and len({id(arm) for arm in arms.values()}) == len(_ARMS),
        "distinct trusted reference and control callbacks required",
    )
    observations = []
    root = Path(root).resolve()

    def run(ctx):
        exhausted = False
        for case in panel["rows"]:
            for side in _SIDES:
                for arm in _ARMS:
                    record = {
                        "case": case["id"],
                        "side": side,
                        "arm": arm,
                        "state": "NOT_RUN",
                        "output_sha256": None,
                    }
                    observations.append(record)
                    if exhausted:
                        continue
                    proposed = deepcopy(case[side])
                    attempts = ctx.report["attempts"]
                    previous_count = len(attempts)
                    try:
                        returned = ctx.invoke(arm, proposed, phase="answer")
                    except BudgetExceeded:
                        exhausted = ctx.exhausted is not None
                        if len(attempts) > previous_count and attempts[-1]["status"] == "FAILED":
                            record["state"] = "CALL_FAILED"
                        continue
                    except Exception:
                        record["state"] = "CALL_FAILED"
                        continue
                    try:
                        if _canonical(proposed) != _canonical(case[side]):
                            raise LabError("case input mutated")
                        record["output_sha256"] = _digest(returned)
                    except LabError:
                        record["state"] = "INVALID_OUTPUT_OR_MUTATION"
                    else:
                        record["state"] = "OBSERVED"
        findings, summary = _score(panel, observations)
        return {
            "status": "FAILED" if findings else "TESTED" if summary["complete"] else "INCONCLUSIVE",
            "summary": "Pinned expected values, executed reference parity, and shortcut accuracy.",
            "metrics": {"observed": summary["observed_invocations"]},
        }

    bench = Workbench(
        Adapter(
            "benchmark-references",
            arms,
            {
                "persists": "Declared stateless for each call",
                "query_mutates": False,
                "reset": "each input",
            },
        ),
        {
            "model": _digest(panel["source_sha256"]),
            "dataset": _digest(panel["rows"]),
            "code": _digest(panel["source_sha256"]),
            "configuration": panel_sha256,
        },
        root,
        max_calls=max_calls,
        max_seconds=max_seconds,
    )
    receipt = bench.run(
        [Diagnostic("benchmark_execution", "v1", _ARMS, run, "Declared paired cases")]
    )
    findings, summary = _score(panel, observations)
    reason = receipt["coverage"][0]["reason"]
    status = (
        "FAILED"
        if findings
        else "TESTED"
        if summary["complete"] and reason == "OBSERVED"
        else "INCONCLUSIVE"
    )
    result = {
        "schema": "trainlab.benchmark-execution.v1",
        "status": status,
        "panel_sha256": panel_sha256,
        "source_sha256": panel["source_sha256"],
        "source_verification": "DECLARED_DISTINCT_DIGESTS",
        "findings": findings,
        "summary": summary,
        "observations": observations,
        "workbench_reason": reason,
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(root / "benchmark.json", result)
    return result
