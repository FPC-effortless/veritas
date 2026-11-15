"""Fail-closed projection of pinned benchmark-execution evidence.

Recomputes declared outcomes, not callback execution or reviewer authenticity.
TESTED is scoped diagnostic coverage, never scientific qualification.
"""

from __future__ import annotations

from .benchmark_execution import _ARMS, _SIDES, _digest, _score, freeze_panel
from .prediction_artifacts import _bytes, _hash, _require, _text
from .runner import _finite


def project_benchmark(panel_frozen, benchmark_report, workbench_report):
    """Return finite scalar conditions without discarding known failures.

    Consumers must pin all three original documents and require admissible == 1;
    individual group/count thresholds alone do not constitute admission.
    """
    for document in (panel_frozen, benchmark_report, workbench_report):
        _bytes(document)
    _require(
        type(panel_frozen) is dict and set(panel_frozen) == {"panel", "panel_sha256"},
        "frozen benchmark panel required",
    )
    panel, pin = panel_frozen["panel"], panel_frozen["panel_sha256"]
    _require(
        type(panel) is dict
        and set(panel)
        == {
            "rows",
            "source_sha256",
            "minimum_changed_groups",
            "minimum_invariant_groups",
            "maximum_shortcut_accuracy",
        },
        "invalid benchmark panel fields",
    )
    _require(
        _hash(pin) and _digest(panel) == pin and freeze_panel(**panel) == panel_frozen,
        "benchmark panel identity changed",
    )
    report, work = benchmark_report, workbench_report
    _require(
        type(report) is dict
        and set(report)
        == {
            "schema",
            "status",
            "panel_sha256",
            "source_sha256",
            "source_verification",
            "findings",
            "summary",
            "observations",
            "workbench_reason",
            "scientific_qualification",
        }
        and report["schema"] == "trainlab.benchmark-execution.v1"
        and report["panel_sha256"] == pin
        and report["source_sha256"] == panel["source_sha256"]
        and report["source_verification"] == "DECLARED_DISTINCT_DIGESTS"
        and report["scientific_qualification"] == "NOT_QUALIFIED",
        "invalid or mismatched benchmark report",
    )
    _require(
        type(work) is dict
        and work.get("schema") == "trainlab.research_diagnostics.v1"
        and work.get("scientific_qualification") == "NOT_QUALIFIED"
        and work.get("identity_scope") == "DECLARED_RECIPE_OR_ARTIFACT_HASHES"
        and work.get("state") in ("COMPLETE", "PARTIAL"),
        "invalid workbench report",
    )
    expected_identities = {
        "configuration": pin,
        "dataset": _digest(panel["rows"]),
        "code": _digest(panel["source_sha256"]),
        "model": _digest(panel["source_sha256"]),
    }
    _require(work.get("identities") == expected_identities, "workbench identity mismatch")
    adapter = work.get("adapter")
    _require(
        type(adapter) is dict
        and adapter.get("name") == "benchmark-references"
        and adapter.get("capabilities") == sorted(_ARMS)
        and adapter.get("asynchronous") is False
        and adapter.get("state_semantics")
        == {
            "persists": "Declared stateless for each call",
            "query_mutates": False,
            "reset": "each input",
        },
        "benchmark adapter mismatch",
    )
    coverage = work.get("coverage")
    _require(
        type(coverage) is list and len(coverage) == 1 and type(coverage[0]) is dict,
        "one benchmark coverage entry required",
    )
    coverage = coverage[0]
    _require(
        coverage.get("name") == "benchmark_execution"
        and coverage.get("version") == "v1"
        and coverage.get("requires") == list(_ARMS)
        and coverage.get("missing_capabilities") == []
        and _text(coverage.get("reason"))
        and coverage["reason"] == report["workbench_reason"],
        "coverage identity mismatch",
    )
    expected = [(row["id"], side, arm) for row in panel["rows"] for side in _SIDES for arm in _ARMS]
    observations = report["observations"]
    _require(
        type(observations) is list and len(observations) <= len(expected),
        "bounded observation sequence required",
    )
    for index, row in enumerate(observations):
        _require(
            type(row) is dict
            and set(row) == {"case", "side", "arm", "state", "output_sha256"}
            and (row["case"], row["side"], row["arm"]) == expected[index]
            and row["state"]
            in ("OBSERVED", "NOT_RUN", "CALL_FAILED", "INVALID_OUTPUT_OR_MUTATION"),
            "observation keys, order or state changed",
        )
        _require(
            _hash(row["output_sha256"])
            if row["state"] == "OBSERVED"
            else row["output_sha256"] is None,
            "observation hash/state mismatch",
        )
    findings, summary = _score(panel, observations)
    _require(
        report["findings"] == findings and _bytes(report["summary"]) == _bytes(summary),
        "benchmark findings or summary contradict observations",
    )
    expected_status = (
        "FAILED"
        if findings
        else (
            "TESTED" if summary["complete"] and coverage["reason"] == "OBSERVED" else "INCONCLUSIVE"
        )
    )
    _require(report["status"] == expected_status, "benchmark status contradicts evidence")
    outcome_status = "FAILED" if findings else "TESTED" if summary["complete"] else "INCONCLUSIVE"
    observation = coverage.get("observation")
    if observation is not None:
        _require(
            type(observation) is dict
            and observation.get("status") == outcome_status
            and observation.get("metrics") == {"observed": summary["observed_invocations"]},
            "retained coverage observation contradicts benchmark",
        )
    session, budget = work.get("session"), work.get("budget")
    _require(
        type(session) is dict
        and session.get("budget_exhausted") in (None, "CALLS", "WALL_TIME")
        and type(budget) is dict
        and type(budget.get("max_calls")) is int
        and budget["max_calls"] > 0,
        "invalid workbench budget state",
    )
    if coverage["reason"] == "OBSERVED":
        _require(session["budget_exhausted"] is None, "observed coverage conflicts with budget")
        _require(
            coverage.get("status") == outcome_status
            and type(observation) is dict
            and observation.get("status") == outcome_status
            and observation.get("metrics") == {"observed": summary["observed_invocations"]}
            and len(observations) == len(expected),
            "coverage contradicts scored outcome",
        )
    else:
        _require(
            coverage.get("status") in ("NOT_RUN", "INCONCLUSIVE"),
            "unobserved coverage cannot claim success",
        )
    attempts = work.get("attempts")
    _require(
        type(attempts) is list and len(attempts) <= min(len(expected), budget["max_calls"]),
        "bounded attempt sequence required",
    )
    for index, attempt in enumerate(attempts):
        _require(
            type(attempt) is dict
            and type(attempt.get("id")) is int
            and attempt["id"] == index
            and attempt.get("diagnostic") == "benchmark_execution"
            and attempt.get("phase") == "answer"
            and attempt.get("retry_of") is None
            and attempt.get("condition") == "unspecified"
            and attempt.get("status") in ("SUCCEEDED", "FAILED", "BUDGET_CANCELLED")
            and attempt.get("sync_error") is False,
            "invalid benchmark attempt",
        )
        _require(
            attempt.get("error_type") is None
            if attempt["status"] == "SUCCEEDED"
            else _text(attempt.get("error_type")),
            "attempt error/status mismatch",
        )
        times = [attempt.get(k) for k in ("start_seconds", "end_seconds", "elapsed_seconds")]
        _require(
            all(_finite(t) and t >= 0 for t in times)
            and times[1] >= times[0]
            and abs(times[2] - (times[1] - times[0])) <= 1e-9,
            "invalid attempt duration",
        )
    cursor = 0
    stopped = False
    for row in observations:
        if row["state"] == "NOT_RUN":
            stopped = True
            if cursor < len(attempts) and attempts[cursor]["status"] == "BUDGET_CANCELLED":
                _require(
                    attempts[cursor].get("capability") == row["arm"],
                    "cancelled attempt arm mismatch",
                )
                cursor += 1
            continue
        _require(not stopped, "executed observations follow stopped execution")
        _require(cursor < len(attempts), "observed outcome lacks an attempt")
        attempt = attempts[cursor]
        _require(
            attempt.get("capability") == row["arm"]
            and attempt["status"] == ("FAILED" if row["state"] == "CALL_FAILED" else "SUCCEEDED"),
            "attempt contradicts observation",
        )
        cursor += 1
    _require(cursor == len(attempts), "unmatched attempts")
    complete = summary["complete"] and work["state"] == "COMPLETE"
    admissible = complete and expected_status == "TESTED" and coverage["status"] == "TESTED"
    return {
        "admissible": int(admissible),
        "findings_count": len(findings),
        "complete": int(complete),
        "expected_rows": len(panel["rows"]),
        "expected_invocations": len(expected),
        "observed_invocations": summary["observed_invocations"],
        "unobserved_invocations": len(expected) - summary["observed_invocations"],
        "attempts_count": len(attempts),
        "verified_changed_groups": summary["verified_changed_groups"],
        "verified_invariant_groups": summary["verified_invariant_groups"],
        "shortcut_correct": summary["observed_shortcut_correct"],
        "shortcut_scored": summary["observed_shortcut_total"],
        "failed": int(expected_status == "FAILED"),
        "inconclusive": int(expected_status == "INCONCLUSIVE"),
    }
