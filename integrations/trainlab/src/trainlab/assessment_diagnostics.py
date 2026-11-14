"""Assessment-driven evidence checks over authorized data and trusted CPU commands.

Declarations and hashes do not attest independence, competence, or causal novelty.
"""

from __future__ import annotations

import copy
import hashlib
from collections import Counter
from pathlib import Path

from .experiment_diagnostics import _items, _seeds
from .prediction_artifacts import MAX_BYTES, _bytes, _hash, _require, _rows, _text
from .resource_diagnostics import EXECUTION, run_command
from .runner import LabError, digest, read_json, write_json


def _sha(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def _report(kind, inputs, **fields):
    result = {
        "schema": "trainlab.assessment-diagnostics.v1",
        "kind": kind,
        "input_sha256": _sha(inputs),
        "scientific_qualification": "NOT_QUALIFIED",
        **fields,
    }
    _bytes(result)
    return copy.deepcopy(result)


def generalization_audit(training, evaluation):
    """Inventory declared categorical novelty and numeric extrapolation, not accuracy.

    Axes should name mechanisms/templates, individual identities and payload classes.
    A renamed group does not establish an independent causal generator.
    """
    for rows in (training, evaluation):
        _items(rows)
        for row in rows:
            _require(
                set(row) == {"id", "group", "axes", "scales"}
                and _text(row["group"])
                and type(row["axes"]) is dict
                and 1 <= len(row["axes"]) <= 32
                and type(row["scales"]) is dict
                and len(row["scales"]) <= 32,
                "explicit group, categorical axes and numeric scales required",
            )
            _require(
                all(_text(k) and _text(v) for k, v in row["axes"].items()),
                "categorical axis values must be nonempty strings",
            )
            _require(
                all(
                    _text(k) and type(v) is int and 0 <= v <= 10**9
                    for k, v in row["scales"].items()
                ),
                "invalid scale",
            )
    for row in training + evaluation:
        _require(
            set(row["axes"]) == set(training[0]["axes"])
            and set(row["scales"]) == set(training[0]["scales"]),
            "all rows must expose identical axes and scales",
        )
    axes, scales = {}, {}
    for key in training[0]["axes"]:
        seen = {r["axes"][key] for r in training}
        axes[key] = {
            "training_values": sorted(seen),
            "unseen_ids": [r["id"] for r in evaluation if r["axes"][key] not in seen],
            "seen_ids": [r["id"] for r in evaluation if r["axes"][key] in seen],
        }
    for key in training[0]["scales"]:
        low, high = min(r["scales"][key] for r in training), max(r["scales"][key] for r in training)
        scales[key] = {
            "training_min": low,
            "training_max": high,
            "above_training_max_ids": [r["id"] for r in evaluation if r["scales"][key] > high],
            "below_training_min_ids": [r["id"] for r in evaluation if r["scales"][key] < low],
        }
    return _report(
        "generalization",
        [training, evaluation],
        axes=axes,
        scales=scales,
        overlapping_ids=sorted({r["id"] for r in training} & {r["id"] for r in evaluation}),
        overlapping_groups=sorted(
            {r["group"] for r in training} & {r["group"] for r in evaluation}
        ),
        evaluation_rows=len(evaluation),
        independence="DECLARED_NOT_VERIFIED",
    )


def training_order_audit(arms):
    """Compare exact example/supervision exposure, updates and batch-size sequences.

    Optimizer hash must include loss weights, schedules, clipping, precision and
    freeze masks. Initial-state hash must include model/optimizer/RNG state.
    This audits a planned or recorded schedule, not proof that a trainer executed it.
    """
    _items(arms, maximum=16)
    _require(len(arms) >= 2, "at least two schedules required")
    exposures, batches = {}, {}
    for arm in arms:
        _require(
            set(arm) == {"id", "initialization_sha256", "optimizer_sha256", "updates"}
            and all(_hash(arm[k]) for k in ("initialization_sha256", "optimizer_sha256"))
            and type(arm["updates"]) is list
            and 1 <= len(arm["updates"]) <= 10000,
            "bounded updates and initialization/optimizer identities required",
        )
        counts = Counter()
        for batch in arm["updates"]:
            _require(type(batch) is list and 1 <= len(batch) <= 10000, "nonempty batch required")
            for item in batch:
                _require(
                    type(item) is dict
                    and set(item) == {"example_sha256", "supervision_sha256"}
                    and all(_hash(v) for v in item.values()),
                    "invalid exposure identity",
                )
                counts[_bytes(item)] += 1
        exposures[arm["id"]] = counts
        batches[arm["id"]] = [len(b) for b in arm["updates"]]
    reference = arms[0]
    differences = []
    for arm in arms[1:]:
        for field in ("initialization_sha256", "optimizer_sha256"):
            if arm[field] != reference[field]:
                differences.append({"arm": arm["id"], "dimension": field})
        for name, data in (
            ("example_supervision_exposures", exposures),
            ("update_batch_sizes", batches),
        ):
            if data[arm["id"]] != data[reference["id"]]:
                differences.append({"arm": arm["id"], "dimension": name})
    return _report(
        "training_order",
        arms,
        status="FAILED" if differences else "TESTED",
        differences=differences,
        total_updates={a["id"]: len(a["updates"]) for a in arms},
        total_examples={key: sum(c.values()) for key, c in exposures.items()},
        identical_order=all(_bytes(a["updates"]) == _bytes(reference["updates"]) for a in arms),
        execution="NOT_ATTESTED",
        equal_flops="NOT_ESTABLISHED",
    )


def paired_slices(rows, *, required_ids, required_seeds):
    """Complete paired correctness panel; descriptive query effects, no resampling.

    Never treats correlated queries as independent observations or invents missing
    seed scores. Primitive-value probes can be supplied as explicit template slices.
    """
    _items(rows, key=None)
    _seeds(required_seeds)
    _require(
        type(required_ids) is list
        and 1 <= len(required_ids) <= 10000
        and all(_text(i) for i in required_ids)
        and len(set(required_ids)) == len(required_ids),
        "explicit distinct IDs required",
    )
    pairs, metadata = set(), {}
    for row in rows:
        _require(
            set(row) == {"id", "seed", "group", "payload", "template", "candidate", "baseline"}
            and all(_text(row[k]) for k in ("id", "group", "payload", "template"))
            and type(row["seed"]) is int
            and row["seed"] in required_seeds
            and type(row["candidate"]) is bool
            and type(row["baseline"]) is bool,
            "invalid paired outcome",
        )
        pair = (row["seed"], row["id"])
        _require(pair not in pairs, "duplicate seed/row")
        pairs.add(pair)
        meta = [row[k] for k in ("group", "payload", "template")]
        _require(metadata.setdefault(row["id"], meta) == meta, "metadata changed across seeds")
    _require(
        pairs == {(s, i) for s in required_seeds for i in required_ids},
        "complete required seed-by-row panel required",
    )

    def summarize(subset):
        n = len(subset)
        c, b = sum(r["candidate"] for r in subset), sum(r["baseline"] for r in subset)
        return {
            "queries": n,
            "groups": len({r["group"] for r in subset}),
            "candidate_correct": c,
            "baseline_correct": b,
            "query_delta": (c - b) / n if n else None,
            "rescued": sum(r["candidate"] and not r["baseline"] for r in subset),
            "damaged": sum(r["baseline"] and not r["candidate"] for r in subset),
        }

    overall = summarize(rows)
    slices = {
        "by_" + key: {
            str(value): summarize([r for r in rows if r[key] == value])
            for value in sorted({r[key] for r in rows})
        }
        for key in ("seed", "payload", "template")
    }
    omitted = {}
    for payload in sorted({r["payload"] for r in rows}):
        result = summarize([r for r in rows if r["payload"] != payload])
        result["sign_reversal"] = (
            None
            if result["query_delta"] is None
            else result["query_delta"] * overall["query_delta"] < 0
        )
        result["by_seed"] = {}
        for seed in required_seeds:
            result["by_seed"][str(seed)] = summarize(
                [r for r in rows if r["payload"] != payload and r["seed"] == seed]
            )
        omitted[payload] = result
    return _report(
        "paired_slices",
        [rows, required_ids, required_seeds],
        overall=overall,
        **slices,
        leave_one_payload_out=omitted,
        uncertainty="NOT_ESTIMATED",
        complete_map_accuracy="NOT_COMPUTED",
        independence="DECLARED_NOT_VERIFIED",
    )


def measured_quality_session(
    command, root, *, cwd, identities, inputs, expected, semantics, limits
):
    """Execute and score one bounded CPU session; no imported accuracy/timing join.

    Exact argv placeholders {inputs}/{predictions} select supervisor-owned files.
    Scoring is outside inference timing. Failed attempts retain cost but no point.
    Trusted commands only; source/model identities and query semantics are declared.
    """
    ids = _rows(inputs, "input")
    _require(_rows(expected, "answer") == ids, "expected rows must match input order")
    _require(
        type(semantics) is dict
        and set(semantics) == {"query_mode", "operations"}
        and semantics["query_mode"] in ("fresh_replay", "continuous")
        and _text(semantics["operations"]),
        "explicit query/operation semantics required",
    )
    _require(
        type(command) is list
        and all(type(s) is str for s in command)
        and command.count("{inputs}") == 1
        and command.count("{predictions}") == 1,
        "exactly one inputs and predictions argv placeholder required",
    )
    _bytes([identities, limits, command, inputs, expected, semantics])
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=False)
    input_path, output_path = root / "inputs.json", root / "run" / "predictions.json"
    write_json(input_path, inputs)
    input_hash = digest(input_path)
    replacements = {"{inputs}": str(input_path), "{predictions}": str(output_path)}
    workload = _sha([inputs, expected, semantics, "canonical-json-exact-query-accuracy-v1"])
    receipt = run_command(
        [replacements.get(s, s) for s in command],
        root / "run",
        cwd=cwd,
        identities=identities,
        workload_sha256=workload,
        execution=EXECUTION,
        limits=limits,
    )
    quality, output_hash, error, point = None, None, None, None
    try:
        _require(receipt["cost_coverage"] == "MEASURED", "session incomplete")
        _require(
            not input_path.is_symlink() and digest(input_path) == input_hash, "input file changed"
        )
        _require(
            not output_path.is_symlink()
            and output_path.is_file()
            and output_path.stat().st_size <= MAX_BYTES,
            "missing or invalid output file",
        )
        output_hash = digest(output_path)
        predictions = read_json(output_path, limit=MAX_BYTES)
        _require(_rows(predictions, "answer") == ids, "prediction IDs/order mismatch")
        quality = sum(
            _bytes(p["answer"]) == _bytes(e["answer"]) for p, e in zip(predictions, expected)
        ) / len(ids)
        _require(digest(output_path) == output_hash, "output changed during scoring")
        point = {
            "id": root.name,
            "quality": quality,
            "session_seconds": receipt["wall_seconds"],
            "cost_status": "MEASURED",
            "workload_sha256": workload,
            "hardware_sha256": receipt["hardware_sha256"],
            "boundary_sha256": receipt["boundary_sha256"],
        }
    except (LabError, OSError, ValueError) as exc:
        error, quality = type(exc).__name__, None
    report = _report(
        "measured_quality",
        [inputs, expected, semantics, identities, limits, command],
        receipt=receipt,
        receipt_sha256=digest(root / "run" / "receipt.json"),
        expected_sha256=_sha(expected),
        predictions_sha256=output_hash,
        quality=quality,
        point=point,
        scoring_error=error,
        status="TESTED" if point is not None else "INCONCLUSIVE",
        cost_boundary="CPU session; independent scoring excluded",
        query_semantics=semantics,
        uncertainty="NOT_ESTIMATED",
    )
    write_json(root / "assessment.json", report)
    return report
