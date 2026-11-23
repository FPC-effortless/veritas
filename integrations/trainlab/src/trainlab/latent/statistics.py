"""Paired, fixed-model cluster statistics for saved latent research outputs.

Intervals resample observational units, not fitted models or training seeds.
The caller must retain cluster order and declare the scientific sampling scope.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import numpy as np

from ..runner import LabError


def _finite(values, name="values"):
    try:
        a = np.asarray(values)
        if a.dtype.kind not in "biuf" or not np.isfinite(a).all():
            raise LabError(f"{name} must be finite real numbers")
        return a.astype(np.float64, copy=False)
    except (TypeError, ValueError, OverflowError) as error:
        raise LabError(f"{name} must be finite real numbers") from error


def _ids(values, *, unique=False, name="unit IDs"):
    try:
        a = np.asarray(values)
    except (ValueError, TypeError) as error:
        raise LabError(f"{name} must be a vector of scalar identities") from error
    if (
        isinstance(values, (list, tuple))
        and any(isinstance(v, (str, np.str_)) for v in values)
        and any(not isinstance(v, (str, np.str_)) for v in values)
    ):
        raise LabError(f"{name} cannot silently coerce mixed integer and string identities")
    if a.ndim != 1 or not len(a) or a.dtype.kind not in "iuUS":
        raise LabError(f"{name} must be a nonempty vector of integers or strings")
    if a.dtype.kind in "US" and any(not str(v) for v in a):
        raise LabError(f"{name} cannot be empty strings")
    if unique and len(np.unique(a)) != len(a):
        raise LabError(f"{name} must be unique")
    return a.copy()


def cluster_means(values, unit_ids):
    """Equal row means within each sorted unit; return IDs and aligned means."""
    v, ids = _finite(values), _ids(unit_ids)
    if v.ndim not in (1, 2) or len(v) != len(ids) or not v.size:
        raise LabError("values must be rows or rows by metrics aligned to unit IDs")
    units, inverse = np.unique(ids, return_inverse=True)
    counts = np.bincount(inverse)
    matrix = v.reshape(len(v), -1)
    means = np.stack(
        [np.bincount(inverse, weights=matrix[:, j]) / counts for j in range(matrix.shape[1])],
        axis=1,
    )
    if not np.isfinite(means).all():
        raise LabError("cluster mean arithmetic overflowed")
    return units, means[:, 0] if v.ndim == 1 else means


def record_means(values, record_ids):
    """Equal positions/window, then equal windows/record (no length weighting)."""
    v = _finite(values)
    if v.ndim not in (2, 3) or not v.size:
        raise LabError("record values must be windows by positions [by metrics]")
    return cluster_means(v.mean(axis=1), record_ids)


def fixed_seed_mean(values, seed_ids, required_seeds):
    """Average a complete fixed seed panel before observational resampling."""
    v = _finite(values)
    actual = _ids(seed_ids, unique=True, name="seed IDs")
    expected = _ids(required_seeds, unique=True, name="required seed IDs")
    if (
        v.ndim < 2
        or not v.size
        or len(v) != len(actual)
        or set(actual.tolist()) != set(expected.tolist())
    ):
        raise LabError("fixed seed panel is missing, duplicated, or misaligned")
    # Use the prescribed order, including when supplied observations were shuffled.
    lookup = {value: i for i, value in enumerate(actual.tolist())}
    return _finite(
        v[[lookup[value] for value in expected.tolist()]].mean(axis=0), "fixed seed mean"
    )


def _plain(value):
    a = np.asarray(value)
    return float(a) if a.ndim == 0 else a.tolist()


@dataclass(frozen=True)
class BootstrapPlan:
    """Frozen indices reused for paired effects, conditions and fixed seed means."""

    unit_ids: np.ndarray
    indices: np.ndarray
    strata: np.ndarray | None
    seed: int

    def _values(self, values, unit_ids=None):
        v = _finite(values)
        if v.ndim not in (1, 2) or not v.size or len(v) != len(self.unit_ids):
            raise LabError("bootstrap values must align to every planned unit")
        if unit_ids is not None and not np.array_equal(_ids(unit_ids), self.unit_ids):
            raise LabError("bootstrap unit identities or order differ")
        return v

    def replicates(self, values, unit_ids=None):
        v = self._values(values, unit_ids)
        result = np.empty((len(self.indices),) + v.shape[1:], dtype=np.float64)
        # Bound temporary arrays for archived panels with thousands of units.
        width = max(1, len(v) * (v.shape[1] if v.ndim == 2 else 1))
        chunk = max(1, min(256, 2_000_000 // width))
        for first in range(0, len(result), chunk):
            ix = self.indices[first : first + chunk]
            result[first : first + chunk] = v[ix].mean(axis=1)
        if not np.isfinite(result).all():
            raise LabError("bootstrap mean arithmetic overflowed")
        return result

    def estimate(self, values, unit_ids=None):
        v = self._values(values, unit_ids)
        bounds = np.quantile(self.replicates(v), [0.025, 0.975], axis=0, method="linear")
        point = _finite(v.mean(axis=0), "bootstrap point mean")
        return {
            "mean": _plain(point),
            "ci95": bounds.tolist(),
            "units": len(v),
            "draws": len(self.indices),
            "uncertainty": "fixed-model paired cluster bootstrap; training seeds are fixed",
        }

    def paired(self, left, right, *, left_ids=None, right_ids=None):
        a, b = self._values(left, left_ids), self._values(right, right_ids)
        if a.shape != b.shape:
            raise LabError("paired values must have identical metric shape")
        return self.estimate(a - b)

    def contrast(self, values_by_condition, coefficients):
        if not isinstance(coefficients, dict) or not coefficients:
            raise LabError("contrast requires named finite coefficients")
        total = None
        for name, coefficient in coefficients.items():
            if name not in values_by_condition:
                raise LabError(f"missing contrast condition: {name}")
            c = _finite(coefficient, "coefficient")
            if c.ndim:
                raise LabError("contrast coefficients must be scalars")
            value = self._values(values_by_condition[name])
            if total is not None and total.shape != value.shape:
                raise LabError("contrast metric shapes differ")
            total = c * value if total is None else total + c * value
        return self.estimate(total)

    def difference_in_differences(self, a, b, c, d):
        values = [self._values(v) for v in (a, b, c, d)]
        if any(v.shape != values[0].shape for v in values):
            raise LabError("interaction metric shapes differ")
        # Pair subtractions first: identity aliases yield exact zero interactions.
        return self.estimate((values[0] - values[1]) - (values[2] - values[3]))

    def manifest(self):
        identity = {
            "unit_ids": self.unit_ids.tolist(),
            "strata": None if self.strata is None else self.strata.tolist(),
            "seed": self.seed,
            "draws": len(self.indices),
            "scheme": "fixed_stratum_quotas" if self.strata is not None else "ordinary_clusters",
            "quantiles": [0.025, 0.975],
            "quantile_method": "linear",
        }
        identity["indices_sha256"] = hashlib.sha256(
            np.asarray(self.indices, dtype="<i8").tobytes()
        ).hexdigest()
        identity["plan_sha256"] = hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return identity


def make_bootstrap(unit_ids, *, strata=None, draws=5000, seed=0, indices=None):
    """Create or validate reusable indices, preserving original stratum quotas.

    ``indices`` imports archived draws exactly; indices refer to the supplied
    unit order. Mixed strata in one unit or missing units must be resolved first.
    """
    ids = _ids(unit_ids, unique=True)
    if type(draws) is not int or not 2 <= draws <= 100_000:
        raise LabError("bootstrap draws must be an integer in [2, 100000]")
    if type(seed) is not int or not 0 <= seed < 2**64:
        raise LabError("bootstrap seed must be a nonnegative 64-bit integer")
    if draws * len(ids) > 30_000_000:
        raise LabError("bootstrap indices exceed the 30000000-cell memory limit")
    labels = None if strata is None else _ids(strata, name="strata")
    if labels is not None and len(labels) != len(ids):
        raise LabError("strata must align to every unit")
    if indices is None:
        rng = np.random.default_rng(seed)
        if labels is None:
            ix = rng.integers(0, len(ids), size=(draws, len(ids)))
        else:
            pools = [np.flatnonzero(labels == s) for s in np.unique(labels)]
            ix = np.concatenate(
                [pool[rng.integers(0, len(pool), size=(draws, len(pool)))] for pool in pools],
                axis=1,
            )
    else:
        ix = np.asarray(indices)
        if ix.dtype.kind not in "iu" or ix.shape != (draws, len(ids)):
            raise LabError("archived bootstrap indices have wrong integer shape")
        if np.any(ix < 0) or np.any(ix >= len(ids)):
            raise LabError("bootstrap index is outside the planned unit set")
        ix = ix.astype(np.int64, copy=True)
        if labels is not None:
            for s in np.unique(labels):
                if not np.all(
                    np.count_nonzero(labels[ix] == s, axis=1) == np.count_nonzero(labels == s)
                ):
                    raise LabError("archived bootstrap changed the declared stratum quotas")
    for a in (ids, ix, labels):
        if a is not None:
            a.flags.writeable = False
    return BootstrapPlan(ids, ix, labels, seed)
