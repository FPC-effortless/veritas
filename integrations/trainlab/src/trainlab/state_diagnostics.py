"""Trusted state probes, deterministic failure reduction and scoped repair evidence."""

from __future__ import annotations

import copy
import hashlib
import math
from time import monotonic

from .prediction_artifacts import _bytes, _hash, _require, _rows, _text
from .research_diagnostics import BudgetExceeded
from .runner import LabError, _finite


def _sha(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _same(left, right):
    return _bytes(left) == _bytes(right)


def _report(kind, inputs, status, **observations):
    result = {
        "schema": "trainlab.state-diagnostics.v1",
        "version": "1",
        "kind": kind,
        "input_sha256": _sha(inputs),
        "status": status,
        "observations": observations,
        "scientific_qualification": "NOT_QUALIFIED",
    }
    _bytes(result)
    return copy.deepcopy(result)


def _events(events):
    _require(type(events) is list and len(events) <= 128, "at most 128 events required")
    _require(all(type(e) is dict and _text(e.get("op")) for e in events), "event op required")
    _bytes(events)


_UNSET = object()


def _panel(queries, expected=_UNSET):
    ids = _rows(queries, "input", limit=64)
    if expected is not _UNSET:
        _require(
            type(expected) is dict and set(expected) == set(ids), "complete answer map required"
        )
        _bytes(expected)
    return ids


def _available(ctx, names):
    missing = sorted(set(names) - set(ctx.adapter.operations))
    if ctx.adapter.state_semantics["query_mutates"]:
        missing.append("nonmutating_queries")
    return missing


def _query(ctx, queries, prefix="", answers=None):
    answers = {} if answers is None else answers
    for q in queries:
        answer = ctx.invoke(prefix + "query", copy.deepcopy(q["input"]), phase="answer")
        _bytes(answer)
        answers[q["id"]] = copy.deepcopy(answer)
    return answers


def _replay(ctx, initial, prefix=""):
    ctx.invoke(prefix + "reset", phase="setup")
    for event in initial:
        ctx.invoke(prefix + "update", copy.deepcopy(event), phase="update")


def lifecycle(ctx, *, initial, initial_expected, queries, steps, supported_ops):
    """Run inside a Workbench check. Query semantics must be observational.

    Step expected maps describe the entire panel; touched IDs declare where an
    update may legitimately change answers. Returned rows retain actual answers.
    Known failures survive later budget interruption. Opaque state is not exported.
    """
    _events(initial)
    ids = _panel(queries, initial_expected)
    _require(type(steps) is list and 1 <= len(steps) <= 128, "bounded lifecycle steps required")
    _require(
        type(supported_ops) is list
        and supported_ops
        and all(_text(x) for x in supported_ops)
        and len(set(supported_ops)) == len(supported_ops),
        "supported operations required",
    )
    previous = initial_expected
    step_ids = []
    for step in steps:
        _require(
            type(step) is dict
            and set(step) == {"id", "event", "expected", "touched"}
            and _text(step["id"]),
            "invalid lifecycle step",
        )
        _events([step["event"]])
        _panel(queries, step["expected"])
        touched = step["touched"]
        _require(
            type(touched) is list
            and all(type(x) is str and x in ids for x in touched)
            and len(set(touched)) == len(touched),
            "invalid touched query IDs",
        )
        _require(
            all(q in touched or _same(previous[q], step["expected"][q]) for q in ids),
            "answer changes must be declared touched",
        )
        previous = step["expected"]
        step_ids.append(step["id"])
    _require(len(set(step_ids)) == len(step_ids), "duplicate lifecycle step")
    inputs = [initial, initial_expected, queries, steps, supported_ops, ctx.report["identities"]]
    _bytes(inputs)
    missing = _available(ctx, ["reset", "update", "query"])
    unsupported = sorted(
        {e["op"] for e in initial + [s["event"] for s in steps]} - set(supported_ops)
    )
    if missing or unsupported:
        return _report("lifecycle", inputs, "UNSUPPORTED", missing=missing, operations=unsupported)
    records, errors, baseline, interruption = [], [], {}, None
    previous = initial_expected
    try:
        _replay(ctx, initial)
        _query(ctx, queries, answers=baseline)
        before = baseline
        for step in steps:
            eligible = [
                q for q in ids if q not in step["touched"] and _same(before[q], previous[q])
            ]
            after = {}
            record = {
                "id": step["id"],
                "before": before,
                "after": after,
                "previously_correct_untouched": eligible,
                "completed": False,
            }
            records.append(record)
            ctx.invoke("update", copy.deepcopy(step["event"]), phase="update")
            _query(ctx, queries, answers=after)
            record["completed"] = True
            before, previous = after, step["expected"]
    except Exception as exc:
        interruption = type(exc).__name__
    interruption = interruption or ctx.exhausted
    errors.extend(
        {"step": "initial", "query": q}
        for q in baseline
        if not _same(baseline[q], initial_expected[q])
    )
    for record, step in zip(records, steps):
        after = record["after"]
        wrong = [q for q in after if not _same(after[q], step["expected"][q])]
        eligible = record["previously_correct_untouched"]
        damaged = [q for q in eligible if q in wrong]
        record.update(
            wrong=wrong,
            newly_damaged=damaged,
            conditional_damage_rate=len(damaged) / len(eligible)
            if eligible and all(q in after for q in eligible)
            else None,
        )
        errors.extend({"step": step["id"], "query": q} for q in wrong)
    return _report(
        "lifecycle",
        inputs,
        "FAILED" if errors else "INCONCLUSIVE" if interruption else "TESTED",
        records=records,
        baseline=baseline,
        errors=errors,
        completed_steps=sum(r["completed"] for r in records),
        expected_steps=len(steps),
        interruption=interruption,
        expected_answers="CALLER_DECLARED",
    )


def write_intervention(ctx, *, initial, event, queries):
    """Replay the same initial history and omit one write; frozen weights are assumed."""
    _events(initial)
    _events([event])
    _panel(queries)
    inputs = [initial, event, queries, ctx.report["identities"]]
    _bytes(inputs)
    missing = _available(ctx, ["reset", "update", "query"])
    if missing:
        return _report("write_intervention", inputs, "UNSUPPORTED", missing=missing)
    outputs, interruption = {}, None
    try:
        for arm in ("normal", "write_omitted"):
            _replay(ctx, initial)
            if arm == "normal":
                ctx.invoke("update", copy.deepcopy(event), phase="update")
            outputs[arm] = {}
            _query(ctx, queries, answers=outputs[arm])
    except Exception as exc:
        interruption = type(exc).__name__
    interruption = interruption or ctx.exhausted
    changed = (
        [
            q["id"]
            for q in queries
            if not _same(outputs["normal"][q["id"]], outputs["write_omitted"][q["id"]])
        ]
        if not interruption
        else None
    )
    return _report(
        "write_intervention",
        inputs,
        "INCONCLUSIVE" if interruption else "TESTED",
        outputs=outputs,
        changed_query_ids=changed,
        interruption=interruption,
        inference="Paired observed effect; determinism and frozen weights assumed.",
        reconstruction_cost="Both resets and all replayed updates are in the workbench ledger.",
    )


def restore_isolation(
    ctx,
    *,
    initial,
    queries,
    expected,
    mutation,
    mutated_expected,
    peer_mutation,
    peer_mutated_expected,
):
    """Probe source and peer operations through one ledger; both may be same model type.

    peer_reset/update/query/restore operate on an independently constructed recipient.
    snapshot is deliberately not deep-copied: adapter ownership defects must remain observable.
    """
    _events(initial)
    _events([mutation])
    _events([peer_mutation])
    _panel(queries, expected)
    _panel(queries, mutated_expected)
    _panel(queries, peer_mutated_expected)
    _require(
        not _same(expected, mutated_expected)
        and not _same(peer_mutated_expected, expected)
        and not _same(peer_mutated_expected, mutated_expected),
        "distinct observable source and peer mutations required",
    )
    inputs = [
        initial,
        queries,
        expected,
        mutation,
        mutated_expected,
        peer_mutation,
        peer_mutated_expected,
        ctx.report["identities"],
    ]
    _bytes(inputs)
    names = [
        "reset",
        "update",
        "query",
        "snapshot",
        "peer_reset",
        "peer_update",
        "peer_query",
        "peer_restore",
    ]
    missing = _available(ctx, names)
    if missing:
        return _report("restore_isolation", inputs, "UNSUPPORTED", missing=missing)
    observations, failures, interruption = {}, [], None

    def observe(name, prefix, wanted):
        actual = {}
        observations[name] = actual
        try:
            _query(ctx, queries, prefix, answers=actual)
        finally:
            if any(not _same(value, wanted[key]) for key, value in actual.items()):
                failures.append(name)

    try:
        _replay(ctx, initial)
        observe("source_initial", "", expected)
        snapshot = ctx.invoke("snapshot", phase="persist")
        ctx.invoke("peer_reset", phase="setup")
        ctx.invoke("peer_restore", snapshot, phase="load")
        # Complete restore before checking either arm; the restore may corrupt source.
        observe("source_after_restore", "", expected)
        observe("peer_after_restore", "peer_", expected)
        ctx.invoke("update", copy.deepcopy(mutation), phase="update")
        observe("source_after_mutation", "", mutated_expected)
        observe("peer_after_source_mutation", "peer_", expected)
        ctx.invoke("peer_update", copy.deepcopy(peer_mutation), phase="update")
        observe("peer_after_own_mutation", "peer_", peer_mutated_expected)
        observe("source_after_peer_mutation", "", mutated_expected)
        # Restore peer to original snapshot after source mutation: snapshot aliasing also surfaces.
        ctx.invoke("peer_restore", snapshot, phase="load")
        observe("peer_restored_again", "peer_", expected)
        observe("source_after_peer_restore", "", mutated_expected)
    except Exception as exc:
        interruption = type(exc).__name__
    interruption = interruption or ctx.exhausted
    return _report(
        "restore_isolation",
        inputs,
        "FAILED" if failures else "INCONCLUSIVE" if interruption else "TESTED",
        answers=observations,
        failures=failures,
        interruption=interruption,
        scope="Behavioral probes; not proof of no shared backing.",
    )


def minimize_failure(events, predicate, *, max_calls=100, max_seconds=10):
    """Deterministic deletion reducer. Predicate True=failure, False=clean, None=unknown.

    Trusted predicate must reset its state per call. Time is cooperative, not
    preemption. Returned candidate was observed failing; no global minimum claim.
    """
    _events(events)
    _require(
        callable(predicate)
        and type(max_calls) is int
        and 1 <= max_calls <= 10000
        and _finite(max_seconds)
        and 0 < max_seconds <= 3600,
        "bounded reducer budget required",
    )
    inputs = [events, max_calls, max_seconds]
    started = monotonic()
    trials, candidate, stopped = [], None, None

    def probe(value):
        nonlocal stopped
        if len(trials) >= max_calls or monotonic() - started >= max_seconds:
            stopped = "BUDGET_EXHAUSTED"
            raise BudgetExceeded(stopped)
        outcome, error = None, None
        try:
            outcome = predicate(copy.deepcopy(value))
            if outcome is not None and type(outcome) is not bool:
                raise LabError("predicate must return boolean or unknown")
        except Exception as exc:
            error = type(exc).__name__
            outcome = None
        trials.append(
            {
                "candidate_sha256": _sha(value),
                "events": len(value),
                "outcome": outcome,
                "error_type": error,
            }
        )
        if outcome is None:
            stopped = "UNKNOWN_PREDICATE"
            raise LabError(stopped)
        return outcome

    minimal = False
    try:
        if probe(events):
            candidate = copy.deepcopy(events)
            chunk = max(1, math.ceil(len(candidate) / 2))
            while candidate:
                reduced = False
                for start in range(0, len(candidate), chunk):
                    trial = candidate[:start] + candidate[start + chunk :]
                    if probe(trial):
                        candidate = trial
                        reduced = True
                        break
                if reduced:
                    chunk = max(1, min(chunk, math.ceil(len(candidate) / 2)))
                elif chunk == 1:
                    minimal = True
                    break
                else:
                    chunk = max(1, chunk // 2)
            if candidate == []:
                minimal = True
    except (BudgetExceeded, LabError):
        pass
    elapsed = monotonic() - started
    if elapsed >= max_seconds:
        stopped, minimal = "BUDGET_EXHAUSTED", False
    return _report(
        "minimize_failure",
        inputs,
        "INCONCLUSIVE" if stopped else "TESTED" if candidate is not None else "FAILED",
        candidate=candidate,
        confirmed_failure=candidate is not None,
        one_deletion_minimal=minimal,
        trials=trials,
        calls=len(trials),
        elapsed_seconds=elapsed,
        stopped=stopped,
        assumptions="Deterministic reset-per-call predicate; no global-minimum guarantee.",
    )


def verify_repair(
    panels,
    *,
    required_ids,
    freshness,
    selection_groups,
    hypotheses,
    interventions,
    min_fresh_gain=1e-12,
    max_regression_damage=0,
):
    """Inspect supplied before/after predictions; freshness and causes are not attested."""
    _bytes([panels, required_ids, freshness, selection_groups, hypotheses, interventions])
    _require(
        type(panels) is dict
        and set(panels) == {"fresh", "regression"}
        and type(required_ids) is dict
        and set(required_ids) == set(panels),
        "two panels required",
    )
    _require(
        type(freshness) is dict
        and set(freshness)
        == {"evaluation_sha256", "frozen_before_evaluation", "used_for_selection"}
        and _hash(freshness["evaluation_sha256"])
        and all(
            freshness[k] is None or type(freshness[k]) is bool
            for k in ("frozen_before_evaluation", "used_for_selection")
        ),
        "freshness required",
    )
    _require(
        type(selection_groups) is list
        and len(selection_groups) <= 10000
        and all(_text(g) for g in selection_groups),
        "selection groups required",
    )
    _require(
        _finite(min_fresh_gain)
        and 0 <= min_fresh_gain <= 1
        and _finite(max_regression_damage)
        and 0 <= max_regression_damage <= 1,
        "bounded repair thresholds required",
    )
    _rows(hypotheses, "description", limit=32)
    _require(all(_text(h["description"]) for h in hypotheses), "hypothesis descriptions required")
    _require(
        type(interventions) is list and len(interventions) <= 64, "bounded interventions required"
    )
    hypothesis_ids = {h["id"] for h in hypotheses}
    for i in interventions:
        _require(
            type(i) is dict
            and set(i) == {"hypothesis_id", "observation", "evidence_sha256"}
            and i["hypothesis_id"] in hypothesis_ids
            and _text(i["observation"])
            and _hash(i["evidence_sha256"]),
            "linked intervention evidence required",
        )
    result, groups = {}, {}
    for name, rows in panels.items():
        ids = required_ids[name]
        _require(
            type(ids) is list
            and 1 <= len(ids) <= 10000
            and all(_text(i) for i in ids)
            and len(set(ids)) == len(ids),
            "declared panel identities required",
        )
        _require(type(rows) is list and len(rows) <= 10000, "bounded panel required")
        seen, complete, before_correct, after_correct, damaged = set(), [], [], [], []
        groups[name] = set()
        for row in rows:
            _require(
                type(row) is dict
                and set(row) == {"id", "group", "expected", "before", "after"}
                and _text(row["id"])
                and row["id"] in ids
                and row["id"] not in seen
                and _text(row["group"]),
                "invalid paired repair row",
            )
            seen.add(row["id"])
            groups[name].add(row["group"])
            for arm in ("before", "after"):
                observation = row[arm]
                _require(
                    type(observation) is dict
                    and set(observation) == {"status", "value"}
                    and observation["status"] in ("observed", "missing", "failed"),
                    "explicit paired observation status required",
                )
            if any(row[arm]["status"] != "observed" for arm in ("before", "after")):
                continue
            complete.append(row["id"])
            old = _same(row["before"]["value"], row["expected"])
            new = _same(row["after"]["value"], row["expected"])
            if old:
                before_correct.append(row["id"])
            if new:
                after_correct.append(row["id"])
            if old and not new:
                damaged.append(row["id"])
        result[name] = {
            "expected": len(ids),
            "complete": len(complete),
            "missing_ids": sorted(set(ids) - seen),
            "gain": (len(after_correct) - len(before_correct)) / len(ids)
            if len(complete) == len(ids)
            else None,
            "previously_correct": len(before_correct),
            "damaged_ids": damaged,
            "conditional_damage": len(damaged) / len(before_correct) if before_correct else None,
        }
    overlap = groups["fresh"] & (set(selection_groups) | groups["regression"])
    overlapping_ids = set(required_ids["fresh"]) & set(required_ids["regression"])
    fresh_known = (
        freshness["frozen_before_evaluation"] is True and freshness["used_for_selection"] is False
    )
    bad_fresh = (
        freshness["frozen_before_evaluation"] is False or freshness["used_for_selection"] is True
    )
    all_complete = all(v["expected"] == v["complete"] for v in result.values())
    gain, damage = result["fresh"]["gain"], result["regression"]["conditional_damage"]
    violated = (
        bool(overlap)
        or bool(overlapping_ids)
        or bad_fresh
        or (gain is not None and gain < min_fresh_gain)
        or (damage is not None and damage > max_regression_damage)
    )
    status = (
        "FAILED"
        if violated
        else "TESTED"
        if all_complete and fresh_known and damage is not None
        else "INCONCLUSIVE"
    )
    return _report(
        "verify_repair",
        [
            panels,
            required_ids,
            freshness,
            selection_groups,
            hypotheses,
            interventions,
            min_fresh_gain,
            max_regression_damage,
        ],
        status,
        panels=result,
        paired_predictions=panels,
        freshness=freshness,
        overlapping_fresh_groups=sorted(overlap),
        overlapping_panel_ids=sorted(overlapping_ids),
        hypotheses=hypotheses,
        intervention_observations=interventions,
        conclusion="Declared panel criteria only; no causal attribution or scientific admission.",
    )
