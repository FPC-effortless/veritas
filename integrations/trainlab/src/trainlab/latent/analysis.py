"""JSON/array entrypoints for reusable statistics, inventory and timing."""

from __future__ import annotations

import numpy as np

from .artifacts import HASH, require


def bootstrap_estimate(values, unit_ids, *, strata=None, draws=5000, seed=0, indices=None):
    from .statistics import make_bootstrap

    plan = make_bootstrap(unit_ids, strata=strata, draws=draws, seed=seed, indices=indices)
    return {
        "estimate": plan.estimate(values),
        "bootstrap": plan.manifest(),
        "indices": plan.indices,
    }


def paired_estimate(left, right, unit_ids, *, strata=None, draws=5000, seed=0, indices=None):
    from .statistics import make_bootstrap

    plan = make_bootstrap(unit_ids, strata=strata, draws=draws, seed=seed, indices=indices)
    return {
        "estimate": plan.paired(left, right),
        "bootstrap": plan.manifest(),
        "indices": plan.indices,
    }


def linear_contrast(
    values_by_condition, coefficients, unit_ids, *, strata=None, draws=5000, seed=0, indices=None
):
    from .statistics import make_bootstrap

    plan = make_bootstrap(unit_ids, strata=strata, draws=draws, seed=seed, indices=indices)
    return {
        "estimate": plan.contrast(values_by_condition, coefficients),
        "bootstrap": plan.manifest(),
        "indices": plan.indices,
    }


def factorial_contrast(a, b, c, d, unit_ids, *, strata=None, draws=5000, seed=0, indices=None):
    from .statistics import make_bootstrap

    plan = make_bootstrap(unit_ids, strata=strata, draws=draws, seed=seed, indices=indices)
    return {
        "estimate": plan.difference_in_differences(a, b, c, d),
        "bootstrap": plan.manifest(),
        "indices": plan.indices,
    }


def sign_flip(differences, *, draws=10000, seed=0):
    """Two-sided sensitivity under independent symmetric cluster differences."""
    values = np.asarray(differences, dtype=np.float64)
    require(
        values.ndim == 1 and 2 <= len(values) <= 100000 and np.isfinite(values).all(),
        "finite cluster-level differences required",
    )
    require(
        type(draws) is int and 1 <= draws <= 100000 and type(seed) is int and seed >= 0,
        "bounded sign-flip draws and seed required",
    )
    rng, observed, extreme = np.random.default_rng(seed), abs(values.mean()), 0
    for start in range(0, draws, 128):
        count = min(128, draws - start)
        signs = 2 * rng.integers(0, 2, size=(count, len(values))) - 1
        sampled = np.abs((signs * values).mean(axis=1))
        extreme += int(np.count_nonzero(sampled >= observed))
    return {
        "effect": float(values.mean()),
        "p_sensitivity": (extreme + 1) / (draws + 1),
        "draws": draws,
        "seed": seed,
        "units": len(values),
        "assumption": "independent cluster differences symmetric under the null",
        "scope": "sign-flip sensitivity; not randomization-based causal identification",
    }


def holm(p_values):
    p = np.asarray(p_values, dtype=np.float64)
    require(
        p.ndim == 1
        and 1 <= len(p) <= 10000
        and np.isfinite(p).all()
        and np.all((0 <= p) & (p <= 1)),
        "valid p-values required",
    )
    order = np.argsort(p, kind="stable")
    adjusted = np.minimum(1, np.maximum.accumulate((len(p) - np.arange(len(p))) * p[order]))
    result = np.empty_like(p)
    result[order] = adjusted
    return {"method": "Holm", "family_size": len(p), "adjusted": result}


def inventory_models(models):
    """Validate declared provenance and identify meaningful comparison groups."""
    require(type(models) is list and 1 <= len(models) <= 10000, "bounded model inventory required")
    seen, groups, rows = set(), {}, []
    for model in models:
        required = {
            "id",
            "checkpoint_sha256",
            "source_sha256",
            "tokenizer_sha256",
            "panel_sha256",
            "representation",
            "parameters",
            "seed",
            "training_context",
        }
        require(type(model) is dict and required <= set(model), "incomplete model identity")
        require(
            isinstance(model["id"], str) and model["id"] and model["id"] not in seen,
            "duplicate/empty model ID",
        )
        require(
            all(
                isinstance(model[k], str) and HASH.fullmatch(model[k])
                for k in ("checkpoint_sha256", "source_sha256", "tokenizer_sha256", "panel_sha256")
            ),
            "checkpoint/source/tokenizer/panel hashes required",
        )
        require(
            type(model["parameters"]) is int
            and model["parameters"] > 0
            and type(model["seed"]) is int
            and type(model["training_context"]) is int
            and model["training_context"] > 0
            and isinstance(model["representation"], str),
            "invalid model dimensions or representation",
        )
        seen.add(model["id"])
        group = (model["tokenizer_sha256"], model["panel_sha256"], model["representation"])
        groups.setdefault(group, []).append(model["id"])
        rows.append(dict(model))
    return {
        "models": rows,
        "comparison_groups": [
            {
                "tokenizer_sha256": key[0],
                "panel_sha256": key[1],
                "representation": key[2],
                "models": ids,
            }
            for key, ids in groups.items()
        ],
        "scope": "declared identity and alignment; source honesty and rights are not attested",
    }


def timing_summary(
    durations,
    *,
    warmups=0,
    queries_per_call=1,
    boundary,
    hardware_sha256,
    checkpoint_before,
    checkpoint_after,
    quality_passed=False,
):
    values = np.asarray(durations, dtype=np.float64)
    require(
        values.ndim == 1
        and 1 <= len(values) <= 100000
        and np.isfinite(values).all()
        and np.all(values > 0),
        "positive raw durations required",
    )
    require(
        type(warmups) is int
        and 0 <= warmups < len(values)
        and type(queries_per_call) is int
        and queries_per_call > 0,
        "valid warmup and query counts required",
    )
    require(
        isinstance(boundary, str)
        and 0 < len(boundary) <= 2000
        and all(
            isinstance(v, str) and HASH.fullmatch(v)
            for v in (hardware_sha256, checkpoint_before, checkpoint_after)
        )
        and type(quality_passed) is bool,
        "timing identity/boundary required",
    )
    kept = values[warmups:]
    q25, median, q75 = np.quantile(kept, [0.25, 0.5, 0.75], method="linear")
    return {
        "status": "TESTED" if checkpoint_before == checkpoint_after else "FAILED",
        "median_seconds": float(median),
        "iqr_seconds": float(q75 - q25),
        "median_seconds_per_query": float(median / queries_per_call),
        "warmups": warmups,
        "measured_repeats": len(kept),
        "raw_seconds": values,
        "boundary": boundary,
        "hardware_sha256": hardware_sha256,
        "quality_qualified_comparison": quality_passed,
        "scope": "observed implementation and workload; not universal architecture speed",
    }
