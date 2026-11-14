"""Bounded diagnostics over declared observations; no scientific admission authority."""

from __future__ import annotations

import copy
import hashlib
import math
import random
from collections import Counter

from .prediction_artifacts import _bytes, _hash, _text
from .runner import LabError, _finite

PACKS = {
    "training": {
        "version": "1",
        "requires": ["ordered training events", "frozen thresholds"],
        "limitations": "Observed channels only; thresholds are not universal defect rules.",
    },
    "benchmark": {
        "version": "1",
        "requires": ["paired answers", "references", "group IDs"],
        "limitations": "Interventions and oracle independence are caller declarations.",
    },
    "ledger": {
        "version": "1",
        "requires": ["arms", "required seeds", "matched dimensions"],
        "limitations": "Evidence hashes are references, not independent competence verification.",
    },
    "paired": {
        "version": "1",
        "requires": ["complete paired unit-by-seed panel"],
        "limitations": "Unit bootstrap conditional on observed seeds; independent units assumed.",
    },
    "classification": {
        "version": "1",
        "requires": ["class order", "row predictions"],
        "limitations": "Single-label classification; calibration depends on bins/sample.",
    },
    "quality_cost": {
        "version": "1",
        "requires": ["quality", "complete measured session costs"],
        "limitations": "Descriptive Pareto set only; context and quality meaning declared.",
    },
}


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _number(value, low=-1e100, high=1e100):
    return _finite(value) and low <= value <= high


def _items(rows, *, key="id", maximum=10000):
    _require(
        type(rows) is list and 1 <= len(rows) <= maximum and all(type(row) is dict for row in rows),
        "bounded nonempty object rows required",
    )
    _bytes(rows)
    if key:
        _require(all(_text(row.get(key)) for row in rows), "row identities required")
        _require(len({row[key] for row in rows}) == len(rows), "duplicate row identity")


def _seeds(seeds):
    _require(
        type(seeds) is list
        and 1 <= len(seeds) <= 100
        and all(type(seed) is int and 0 <= seed <= 2**32 - 1 for seed in seeds)
        and len(set(seeds)) == len(seeds),
        "distinct declared integer seeds required",
    )


def _check(name, status, **metrics):
    return {"name": name, "status": status, "metrics": metrics}


def _coverage(bad, known, total, complete=True):
    return (
        "FAILED"
        if bad
        else "UNSUPPORTED"
        if not known
        else "TESTED"
        if known == total and complete
        else "INCONCLUSIVE"
    )


def _report(pack, inputs, checks, observations=None, findings=None):
    report = {
        "schema": "trainlab.experiment-diagnostics.v1",
        "pack": pack,
        "manifest": copy.deepcopy(PACKS[pack]),
        "input_sha256": hashlib.sha256(_bytes(inputs)).hexdigest(),
        "coverage": checks,
        "observations": observations or {},
        "findings": findings or [],
        "scientific_qualification": "NOT_QUALIFIED",
    }
    _bytes(report)
    return copy.deepcopy(report)


def training_diagnostics(events, *, expected_steps, thresholds):
    """Inspect an explicitly active training window, preserving absent channels.

    Nonfinite observations must be encoded finite=False with unavailable numeric
    summaries null; JSON NaN/Infinity are never accepted. Score trajectories assume
    a fixed evaluation panel. A regression finding is not a causal forgetting claim.
    """
    _items(events, key=None)
    _require(
        type(expected_steps) is list
        and 1 <= len(expected_steps) <= 10000
        and all(type(s) is int and s >= 0 for s in expected_steps)
        and expected_steps == sorted(set(expected_steps)),
        "ordered expected steps required",
    )
    fields = {
        "step",
        "loss",
        "finite",
        "gradient_norm",
        "update_norm",
        "missing_gradients",
        "learning_rate",
        "predicted_classes",
        "validation_score",
    }
    _require(
        type(thresholds) is dict
        and set(thresholds)
        == {
            "min_loss_drop",
            "min_gradient_norm",
            "min_update_norm",
            "min_classes",
            "acquired_score",
            "max_regression",
        },
        "explicit training thresholds required",
    )
    for key in ("min_loss_drop", "acquired_score", "max_regression"):
        _require(_number(thresholds[key], 0, 1), "bounded score threshold required")
    for key in ("min_gradient_norm", "min_update_norm"):
        _require(_number(thresholds[key], 0), "nonnegative norm threshold required")
    _require(
        type(thresholds["min_classes"]) is int and 1 <= thresholds["min_classes"] <= 10000,
        "positive class-count threshold required",
    )
    for event in events:
        _require(
            set(event) <= fields
            and type(event.get("step")) is int
            and event["step"] in expected_steps,
            "invalid event fields or step",
        )
        for key in fields - {"step", "finite", "missing_gradients", "predicted_classes"}:
            if event.get(key) is not None:
                low, high = (
                    (0, 1) if key == "validation_score" else (-1e100 if key == "loss" else 0, 1e100)
                )
                _require(_number(event[key], low, high), "invalid numeric event channel")
        for key in ("missing_gradients", "predicted_classes"):
            if event.get(key) is not None:
                _require(type(event[key]) is int and event[key] >= 0, "invalid count channel")
        _require(
            event.get("finite") is None or type(event["finite"]) is bool,
            "finite flag must be boolean or unknown",
        )
    steps = [e["step"] for e in events]
    _require(steps == sorted(set(steps)), "events must be unique and ordered")
    complete = steps == expected_steps
    checks = [
        _check(
            "step_coverage",
            "TESTED" if complete else "INCONCLUSIVE",
            observed=len(steps),
            expected=len(expected_steps),
        )
    ]
    findings = []

    def channel(name, keys, violation):
        known = [e for e in events if all(e.get(key) is not None for key in keys)]
        bad = [e for e in events if violation(e)]
        if bad:
            findings.append(
                {
                    "kind": name.upper(),
                    "step": bad[0]["step"],
                    "interpretation": "First observed violation of the declared predicate.",
                }
            )
        checks.append(
            _check(
                name,
                _coverage(bad, len(known), len(events), complete),
                observed=len(known),
                violations=len(bad),
            )
        )

    channel("numerics", ["finite"], lambda e: e.get("finite") is False)
    channel(
        "gradients",
        ["gradient_norm", "missing_gradients"],
        lambda e: (
            (e.get("missing_gradients") is not None and e["missing_gradients"] > 0)
            or (
                e.get("gradient_norm") is not None
                and e["gradient_norm"] <= thresholds["min_gradient_norm"]
            )
        ),
    )
    channel(
        "updates",
        ["update_norm", "learning_rate"],
        lambda e: (
            (e.get("update_norm") is not None and e["update_norm"] <= thresholds["min_update_norm"])
            or e.get("learning_rate") == 0
        ),
    )
    channel(
        "prediction_diversity",
        ["predicted_classes"],
        lambda e: (
            e.get("predicted_classes") is not None
            and e["predicted_classes"] < thresholds["min_classes"]
        ),
    )
    losses = [e["loss"] for e in events if e.get("loss") is not None]
    drop = (losses[0] - losses[-1]) / max(abs(losses[0]), 1e-12) if len(losses) >= 2 else None
    checks.append(
        _check(
            "loss_progress",
            "INCONCLUSIVE"
            if drop is None or not complete or len(losses) != len(events)
            else _coverage(drop < thresholds["min_loss_drop"], len(losses), len(events), complete),
            relative_drop=drop,
        )
    )
    scores = [e for e in events if e.get("validation_score") is not None]
    acquired = [e for e in scores if e["validation_score"] >= thresholds["acquired_score"]]
    acquisition = _coverage(False, len(scores), len(events), complete)
    if acquisition == "TESTED" and not acquired:
        acquisition = "FAILED"
    checks.append(_check("acquisition", acquisition, observed=len(scores)))
    regressions = []
    best = None
    for event in scores:
        value = event["validation_score"]
        if best is not None and best - value > thresholds["max_regression"]:
            regressions.append(event["step"])
        if value >= thresholds["acquired_score"]:
            best = max(best if best is not None else value, value)
    retention = (
        "INCONCLUSIVE"
        if not acquired or acquired[0]["step"] == scores[-1]["step"]
        else _coverage(regressions, len(scores), len(events), complete)
    )
    checks.append(
        _check("retention", retention, first_regression=regressions[0] if regressions else None)
    )
    if regressions:
        findings.append(
            {
                "kind": "SCORE_REGRESSION",
                "step": regressions[0],
                "interpretation": "Reported score dropped after threshold acquisition.",
            }
        )
    return _report("training", [events, expected_steps, thresholds], checks, findings=findings)


def benchmark_diagnostics(rows, *, min_sensitive_groups=2, max_control_accuracy=0.9):
    """Check supplied paired references/controls; does not execute an intervention."""
    _items(rows)
    _require(
        type(min_sensitive_groups) is int
        and 1 <= min_sensitive_groups <= 10000
        and _number(max_control_accuracy, 0, 1)
        and max_control_accuracy < 1,
        "invalid benchmark thresholds",
    )
    required = {
        "id",
        "group",
        "original",
        "intervened",
        "reference_original",
        "reference_intervened",
        "expect_change",
        "deficient_original",
        "deficient_intervened",
    }
    for row in rows:
        _require(
            set(row) == required and _text(row["group"]) and type(row["expect_change"]) is bool,
            "invalid intervention record",
        )

    def unequal(a, b):
        return _bytes(a) != _bytes(b)

    disagreement, unexpected, sensitive, correct = [], [], set(), 0
    for row in rows:
        changed = unequal(row["original"], row["intervened"])
        if changed:
            sensitive.add(row["group"])
        if changed != row["expect_change"]:
            unexpected.append(row["id"])
        if any(unequal(row[k], row["reference_" + k]) for k in ("original", "intervened")):
            disagreement.append(row["id"])
        correct += sum(
            not unequal(row[k], row["deficient_" + k]) for k in ("original", "intervened")
        )
    accuracy = correct / (2 * len(rows))
    return _report(
        "benchmark",
        [rows, min_sensitive_groups, max_control_accuracy],
        [
            _check(
                "oracle_parity",
                "FAILED" if disagreement else "TESTED",
                disagreements=len(disagreement),
            ),
            _check(
                "intervention_expectations",
                "FAILED" if unexpected else "TESTED",
                violations=len(unexpected),
            ),
            _check(
                "sensitivity",
                "TESTED" if len(sensitive) >= min_sensitive_groups else "FAILED",
                sensitive_groups=len(sensitive),
                required=min_sensitive_groups,
            ),
            _check(
                "deficient_control",
                "FAILED" if accuracy > max_control_accuracy else "TESTED",
                accuracy=accuracy,
                ceiling=max_control_accuracy,
            ),
        ],
        {
            "oracle_disagreement_ids": disagreement[:100],
            "unexpected_ids": unexpected[:100],
            "example_id_limit": 100,
            "groups_are_declared_not_verified_independent": True,
        },
    )


def comparison_ledger(arms, *, required_seeds, matched_fields):
    """Inspect declared supervision, budgets and selection; hashes are evidence pointers."""
    _items(arms, maximum=64)
    _require(len(arms) >= 2, "at least two comparison arms required")
    _seeds(required_seeds)
    _require(
        type(matched_fields) is list
        and 1 <= len(matched_fields) <= 64
        and all(_text(k) for k in matched_fields)
        and len(set(matched_fields)) == len(matched_fields),
        "matched dimensions required",
    )
    for arm in arms:
        _require(
            set(arm) == {"id", "attributes", "seeds", "competence", "selection"}
            and type(arm["attributes"]) is dict,
            "invalid arm ledger",
        )
        _require(type(arm["seeds"]) is list, "seed records must be a list")
        if arm["seeds"]:
            _items(arm["seeds"], key=None, maximum=100)
            _seeds([s.get("seed") for s in arm["seeds"]])
        _require(
            all(
                set(s) == {"seed", "status"}
                and s["status"] in ("succeeded", "failed", "incomplete")
                for s in arm["seeds"]
            ),
            "invalid seed records",
        )
        competence, selection = arm["competence"], arm["selection"]
        _require(
            type(competence) is dict
            and set(competence) == {"status", "evidence_sha256"}
            and competence["status"] in ("supported", "failed", "unknown")
            and (competence["evidence_sha256"] is None or _hash(competence["evidence_sha256"])),
            "invalid competence reference",
        )
        _require(
            type(selection) is dict
            and set(selection) == {"split", "trials", "rule"}
            and selection["split"] in ("train", "validation", "test", "unknown")
            and type(selection["trials"]) is int
            and 1 <= selection["trials"] <= 1000000
            and _text(selection["rule"]),
            "explicit selection/tuning ledger required",
        )
    missing = [key for key in matched_fields if any(a["attributes"].get(key) is None for a in arms)]
    different = [
        key
        for key in matched_fields
        if key not in missing and len({_bytes(a["attributes"][key]) for a in arms}) > 1
    ]
    failed_seeds = [
        a["id"]
        for a in arms
        if {s["seed"] for s in a["seeds"]} != set(required_seeds)
        or any(s["status"] != "succeeded" for s in a["seeds"])
    ]
    competence = [a["competence"] for a in arms]
    comp_status = (
        "FAILED"
        if any(c["status"] == "failed" for c in competence)
        else "TESTED"
        if all(c["status"] == "supported" and c["evidence_sha256"] for c in competence)
        else "INCONCLUSIVE"
    )
    selection = [a["selection"]["split"] for a in arms]
    return _report(
        "ledger",
        [arms, required_seeds, matched_fields],
        [
            _check(
                "matched_information",
                "FAILED" if different else "INCONCLUSIVE" if missing else "TESTED",
                differences=len(different),
                missing=len(missing),
            ),
            _check(
                "seed_completion",
                "FAILED" if failed_seeds else "TESTED",
                incomplete_arms=len(failed_seeds),
            ),
            _check("competence_evidence", comp_status),
            _check(
                "selection",
                "FAILED"
                if "test" in selection
                else "INCONCLUSIVE"
                if "unknown" in selection
                else "TESTED",
            ),
        ],
        {
            "arms": arms,
            "different_dimensions": different,
            "missing_dimensions": missing,
            "incomplete_arm_ids": failed_seeds,
            "evidence_trust": "DECLARED_NOT_INDEPENDENTLY_VERIFIED",
        },
    )


def paired_statistics(
    rows, *, required_units, required_seeds, draws=1000, rng_seed=0, alpha=0.05, comparisons=1
):
    """Paired unit bootstrap of seed-averaged outcomes, conditional on observed seeds.

    Each unit is equally weighted. Caller must freeze units, seeds, stopping/selection
    and comparison family before confirmatory use. No sequential-test guarantee.
    """
    _items(rows, key=None)
    _seeds(required_seeds)
    _require(
        type(required_units) is list
        and 1 <= len(required_units) <= 10000
        and all(_text(u) for u in required_units)
        and len(set(required_units)) == len(required_units),
        "declared unit panel required",
    )
    _require(
        type(draws) is int
        and 100 <= draws <= 10000
        and type(rng_seed) is int
        and 0 <= rng_seed <= 2**32 - 1
        and _number(alpha, 0.001, 0.5)
        and type(comparisons) is int
        and 1 <= comparisons <= 100,
        "bounded resampling parameters required",
    )
    panel = {}
    for row in rows:
        _require(
            set(row) == {"unit", "seed", "candidate", "baseline"}
            and _text(row["unit"])
            and type(row["seed"]) is int
            and row["seed"] in required_seeds
            and _number(row["candidate"])
            and _number(row["baseline"]),
            "invalid paired row",
        )
        key = (row["unit"], row["seed"])
        _require(key not in panel, "duplicate paired unit/seed")
        panel[key] = row["candidate"] - row["baseline"]
    units = sorted({r["unit"] for r in rows})
    _require(set(units) == set(required_units), "missing or unexpected paired unit")
    _require(
        all((u, s) in panel for u in units for s in required_seeds), "incomplete paired seed panel"
    )
    _require(draws * len(units) <= 2000000, "bootstrap operation budget exceeded")
    effects = [
        math.fsum(panel[u, s] for s in sorted(required_seeds)) / len(required_seeds) for u in units
    ]
    mean = math.fsum(effects) / len(effects)
    interval = None
    adjusted = alpha / comparisons
    if len(units) >= 2:
        rng = random.Random(rng_seed)
        boot = sorted(
            math.fsum(rng.choice(effects) for _ in units) / len(units) for _ in range(draws)
        )
        interval = [
            boot[math.floor((draws - 1) * adjusted / 2)],
            boot[math.ceil((draws - 1) * (1 - adjusted / 2))],
        ]
    resolved = interval is not None and draws * adjusted / 2 >= 1
    return _report(
        "paired",
        [rows, required_units, required_seeds, draws, rng_seed, alpha, comparisons],
        [
            _check("paired_panel", "TESTED", units=len(units), seeds=len(required_seeds)),
            _check("uncertainty", "TESTED" if resolved else "INCONCLUSIVE"),
        ],
        {
            "effect": mean,
            "interval": interval,
            "interval_alpha": adjusted,
            "draws": draws,
            "per_seed_effect": {
                str(s): math.fsum(panel[u, s] for u in units) / len(units)
                for s in sorted(required_seeds)
            },
            "method": "UNIT_PERCENTILE_BOOTSTRAP_OF_SEED_MEANS_BONFERRONI_ALPHA",
            "expected_tail_draws": draws * adjusted / 2,
            "sampling_assumption": "Independent declared units; seed uncertainty not resampled.",
            "selection_and_stopping": "NOT_VERIFIED",
        },
    )


def classification_diagnostics(rows, *, classes, bins=10):
    """Single-label metrics on known labels; labels/probability order are caller supplied."""
    _items(rows)
    _require(
        type(classes) is list
        and 2 <= len(classes) <= 100
        and all(_text(c) for c in classes)
        and len(set(classes)) == len(classes)
        and type(bins) is int
        and 1 <= bins <= 100,
        "class order and bounded bins required",
    )
    for row in rows:
        _require(
            {"id", "prediction"} <= set(row)
            and set(row) <= {"id", "prediction", "label", "probabilities", "slice"}
            and row["prediction"] in classes
            and row.get("label") in classes + [None]
            and _text(row.get("slice", "all")),
            "invalid classification row",
        )
        probabilities = row.get("probabilities")
        if probabilities is not None:
            _require(
                type(probabilities) is list
                and len(probabilities) == len(classes)
                and all(_number(p, 0, 1) for p in probabilities)
                and abs(math.fsum(probabilities) - 1) <= 1e-8,
                "invalid normalized probabilities",
            )
    known = [r for r in rows if r.get("label") is not None]
    calibrated = [r for r in known if r.get("probabilities") is not None]
    confusion = [[0 for _ in classes] for _ in classes]
    slices = {}
    errors = []
    for row in known:
        correct = row["label"] == row["prediction"]
        if not correct:
            errors.append(row["id"])
        confusion[classes.index(row["label"])][classes.index(row["prediction"])] += 1
        count = slices.setdefault(row.get("slice", "all"), {"rows": 0, "correct": 0})
        count["rows"] += 1
        count["correct"] += int(correct)
    for count in slices.values():
        count["accuracy"] = count["correct"] / count["rows"]
    brier, nll, ece, zeros = None, None, None, 0
    if calibrated:
        brier_sum, nll_sum = 0.0, 0.0
        buckets = [[] for _ in range(bins)]
        for row in calibrated:
            ps = row["probabilities"]
            target = classes.index(row["label"])
            confidence = ps[classes.index(row["prediction"])]
            brier_sum += math.fsum((p - int(i == target)) ** 2 for i, p in enumerate(ps))
            if ps[target] == 0:
                zeros += 1
            else:
                nll_sum -= math.log(ps[target])
            buckets[min(int(confidence * bins), bins - 1)].append(
                (confidence, int(row["label"] == row["prediction"]))
            )
        brier = brier_sum / len(calibrated)
        nll = nll_sum / len(calibrated) if not zeros else None
        ece = math.fsum(abs(math.fsum(p - y for p, y in bucket)) for bucket in buckets) / len(
            calibrated
        )
    return _report(
        "classification",
        [rows, classes, bins],
        [
            _check("performance", _coverage(False, len(known), len(rows)), labeled_rows=len(known)),
            _check(
                "calibration", _coverage(False, len(calibrated), len(rows)), rows=len(calibrated)
            ),
        ],
        {
            "classes": classes,
            "accuracy": (len(known) - len(errors)) / len(known) if known else None,
            "confusion": confusion,
            "slices": slices,
            "error_ids": errors[:100],
            "error_count": len(errors),
            "prediction_counts": dict(Counter(r["prediction"] for r in rows)),
            "brier": brier,
            "nll": nll,
            "zero_true_probability": zeros,
            "ece": ece,
            "calibration_bins": bins,
            "nll_scope": "Natural log; zero true probability makes NLL infinite (encoded null).",
        },
    )


def quality_cost(rows):
    """Descriptive quality/session-time Pareto set under identical declared contexts."""
    _items(rows, maximum=1000)
    _require(len(rows) >= 2, "at least two quality-cost points required")
    context = ("workload_sha256", "hardware_sha256", "boundary_sha256")
    for row in rows:
        _require(
            set(row) == {"id", "quality", "session_seconds", "cost_status", *context}
            and all(_hash(row[k]) for k in context)
            and _number(row["quality"], 0, 1)
            and row["cost_status"] in ("MEASURED", "INCOMPLETE", "NOT_MEASURED")
            and (row["session_seconds"] is None or _number(row["session_seconds"], 1e-12)),
            "invalid quality-cost observation",
        )
    same = all(len({row[key] for row in rows}) == 1 for key in context)
    measured = all(
        r["cost_status"] == "MEASURED" and r["session_seconds"] is not None for r in rows
    )
    front = None
    if same and measured:
        front = sorted(
            r["id"]
            for r in rows
            if not any(
                q["quality"] >= r["quality"]
                and q["session_seconds"] <= r["session_seconds"]
                and (q["quality"] > r["quality"] or q["session_seconds"] < r["session_seconds"])
                for q in rows
            )
        )
    return _report(
        "quality_cost",
        rows,
        [
            _check("matched_context", "TESTED" if same else "FAILED"),
            _check("cost_coverage", "TESTED" if measured else "INCONCLUSIVE"),
        ],
        {
            "pareto_ids": front,
            "points": rows,
            "uncertainty": "NOT_ESTIMATED",
            "cost_boundary": "Boundary identity must cover complete work, failures and retries.",
        },
    )
