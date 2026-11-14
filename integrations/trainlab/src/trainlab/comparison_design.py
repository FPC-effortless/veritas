"""Analyze fixed, crossed unit-by-training-seed paired comparisons."""

from __future__ import annotations

import hashlib
import math
import random
from collections import Counter

from .experiment_diagnostics import _number, _seeds
from .prediction_artifacts import _bytes, _hash, _require, _text


def _sha(value):
    return hashlib.sha256(_bytes(value)).hexdigest()


def freeze_design(
    *,
    units,
    seeds,
    comparisons,
    context_sha256,
    analysis_window,
    selection,
    alpha=0.05,
    draws=2000,
    rng_seed=0,
):
    """Return a frozen plan and its canonical SHA256 for independent retention."""
    design = {
        "schema": "trainlab.comparison-design.v1",
        "units": units,
        "seeds": seeds,
        "comparisons": comparisons,
        "context_sha256": context_sha256,
        "analysis_window": analysis_window,
        "selection": selection,
        "alpha": alpha,
        "draws": draws,
        "rng_seed": rng_seed,
    }
    _validate(design)
    # Return an independent snapshot, even if the caller mutates its inputs.
    return {
        "design": {
            **design,
            "units": list(units),
            "seeds": list(seeds),
            "comparisons": list(comparisons),
        },
        "design_sha256": _sha(design),
    }


def _labels(values, limit):
    return (
        type(values) is list
        and 1 <= len(values) <= limit
        and all(_text(v) for v in values)
        and len(set(values)) == len(values)
    )


def _validate(design):
    _require(
        type(design) is dict
        and set(design)
        == {
            "schema",
            "units",
            "seeds",
            "comparisons",
            "context_sha256",
            "analysis_window",
            "selection",
            "alpha",
            "draws",
            "rng_seed",
        }
        and design["schema"] == "trainlab.comparison-design.v1"
        and _labels(design["units"], 1000)
        and _labels(design["comparisons"], 32)
        and _hash(design["context_sha256"])
        and _hash(design["analysis_window"])
        and design["selection"] in ("FIXED", "ADAPTIVE", "UNKNOWN")
        and _number(design["alpha"], 0.001, 0.5)
        and type(design["draws"]) is int
        and 100 <= design["draws"] <= 10000
        and type(design["rng_seed"]) is int
        and 0 <= design["rng_seed"] <= 2**32 - 1,
        "invalid fixed comparison design",
    )
    _seeds(design["seeds"])
    n = math.prod(len(design[key]) for key in ("units", "seeds", "comparisons"))
    _require(
        n <= 20000 and n * design["draws"] <= 5000000,
        "crossed comparison exceeds the operation limit",
    )


def _panel(rows, design):
    _require(type(rows) is list and len(rows) <= 20000, "bounded comparison observations required")
    _bytes(rows)
    panels = {name: {} for name in design["comparisons"]}
    units, seeds = set(design["units"]), set(design["seeds"])
    for row in rows:
        _require(
            type(row) is dict
            and set(row) == {"comparison", "unit", "seed", "status", "candidate", "baseline"}
            and _text(row["comparison"])
            and row["comparison"] in panels
            and _text(row["unit"])
            and row["unit"] in units
            and type(row["seed"]) is int
            and row["seed"] in seeds
            and row["status"] in ("OBSERVED", "FAILED", "MISSING"),
            "unexpected comparison, unit, seed or status",
        )
        key = row["unit"], row["seed"]
        panel = panels[row["comparison"]]
        _require(key not in panel, "duplicate comparison cell")
        if row["status"] == "OBSERVED":
            _require(
                _number(row["candidate"]) and _number(row["baseline"]),
                "observed comparison cell requires two finite scores",
            )
        else:
            _require(
                row["candidate"] is None and row["baseline"] is None,
                "failed or missing cell cannot supply scores",
            )
        panel[key] = dict(row)
    return panels


def _scaled_deltas(rows):
    """Represent the input JSON numbers on one exact binary denominator."""
    pairs = [
        (a, b)
        for row in rows
        if row["status"] == "OBSERVED"
        for a, b in [(row["candidate"].as_integer_ratio(), row["baseline"].as_integer_ratio())]
    ]
    denominator = max((d for pair in pairs for _, d in pair), default=1)
    return [
        a * (denominator // ad) - b * (denominator // bd) for (a, ad), (b, bd) in pairs
    ], denominator


def _bootstrap(matrices, denominators, draws, seed):
    """Share unit and seed resamples across every comparison in the family."""
    rng = random.Random(seed)
    sizes = next(iter(matrices.values()))
    units, seeds = len(sizes), len(sizes[0])
    combinations = {name: {"crossed": [], "unit_only": [], "seed_only": []} for name in matrices}
    unit_sums = {name: [sum(row) for row in values] for name, values in matrices.items()}
    seed_sums = {
        name: [sum(row[j] for row in values) for j in range(seeds)]
        for name, values in matrices.items()
    }
    for _ in range(draws):
        u = [rng.randrange(units) for _ in range(units)]
        s = [rng.randrange(seeds) for _ in range(seeds)]
        uc, sc = Counter(u), Counter(s)
        for name, matrix in matrices.items():
            normalizer = units * seeds * denominators[name]
            pools = combinations[name]
            pools["crossed"].append(
                sum(matrix[i][j] * ui * sj for i, ui in uc.items() for j, sj in sc.items())
                / normalizer
            )
            pools["unit_only"].append(sum(unit_sums[name][i] for i in u) / normalizer)
            pools["seed_only"].append(sum(seed_sums[name][j] for j in s) / normalizer)
    return combinations


def _bounds(samples, tail):
    ranked = sorted(samples)
    last = len(ranked) - 1
    return [ranked[math.floor(last * tail)], ranked[math.ceil(last * (1 - tail))]]


def analyze(design, rows, *, design_sha256, context_sha256):
    """Compute descriptive paired effects and fixed-design percentile intervals."""
    _validate(design)
    _require(
        type(design_sha256) is str
        and _hash(design_sha256)
        and _sha(design) == design_sha256
        and type(context_sha256) is str
        and _hash(context_sha256)
        and context_sha256 == design["context_sha256"],
        "comparison context or design changed",
    )
    panels = _panel(rows, design)
    units, seeds = sorted(design["units"]), sorted(design["seeds"])
    count = len(units) * len(seeds)
    summary, matrices, denominators = {}, {}, {}
    for name, observed in panels.items():
        joined = [
            observed.get(
                (u, s),
                {
                    "comparison": name,
                    "unit": u,
                    "seed": s,
                    "status": "MISSING",
                    "candidate": None,
                    "baseline": None,
                },
            )
            for u in units
            for s in seeds
        ]
        errors = Counter(row["status"] for row in joined)
        deltas, denominator = _scaled_deltas(joined)
        denominators[name] = denominator
        table = [
            {
                "seed": s,
                "observed_units": sum(
                    (u, s) in observed and observed[u, s]["status"] == "OBSERVED" for u in units
                ),
            }
            for s in seeds
        ]
        complete = len(deltas) == count
        if complete:
            matrices[name] = [deltas[i : i + len(seeds)] for i in range(0, len(deltas), len(seeds))]
        summary[name] = {
            "cells": joined,
            "observed": len(deltas),
            "missing": errors["MISSING"],
            "failed": errors["FAILED"],
            "required": count,
            "coverage_by_seed": table,
            "observed_cell_mean": sum(deltas) / (len(deltas) * denominator) if deltas else None,
            "effect": sum(deltas) / (count * denominator) if complete else None,
            "intervals": None,
        }
    tail = design["alpha"] / (2 * len(summary))
    inferred = (
        design["selection"] == "FIXED"
        and len(matrices) == len(summary)
        and len(units) >= 2
        and len(seeds) >= 2
        and tail * design["draws"] >= 1
    )
    if inferred:
        samples = _bootstrap(matrices, denominators, design["draws"], design["rng_seed"])
        for name, pools in samples.items():
            summary[name]["intervals"] = {k: _bounds(values, tail) for k, values in pools.items()}
    return {
        "schema": "trainlab.crossed-paired-statistics.v1",
        "status": "TESTED" if inferred else "INCONCLUSIVE",
        "design_sha256": design_sha256,
        "context_sha256": context_sha256,
        "selection": design["selection"],
        "expected_tail_draws": tail * design["draws"],
        "tail_probability": tail,
        "comparisons": summary,
        "method": "Paired crossed unit-and-seed percentile bootstrap with Bonferroni tails.",
        "scope": "Independent exchangeable axes and fixed selection are caller declarations.",
        "scientific_qualification": "NOT_QUALIFIED",
    }
