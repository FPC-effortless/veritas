"""Latent geometry on measured arrays; fitted transforms never receive targets.

Analysis functions return ``(JSON-safe report, named NumPy arrays)``. Transform
functions return arrays. These operations verify implementation invariants; they
do not qualify a model, a scientific claim, or an inference optimization.
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..runner import LabError

try:
    import numpy as np
except ImportError as exc:  # The base TrainLab installation remains dependency-free.
    raise LabError("latent geometry requires the TrainLab latent NumPy extra") from exc


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _matrix(value, name="matrix", *, rows=None, min_rows=1):
    _require(not np.iscomplexobj(value), f"{name} must contain real numeric values")
    try:
        result = np.asarray(value, dtype=np.float64)
    except (ValueError, TypeError, OverflowError) as exc:
        raise LabError(f"{name} must be a finite numeric matrix") from exc
    _require(
        result.ndim == 2 and result.shape[0] >= min_rows and result.shape[1] > 0,
        f"{name} must be a nonempty two-dimensional matrix",
    )
    _require(rows is None or result.shape[0] == rows, f"{name} rows are not aligned")
    _require(bool(np.isfinite(result).all()), f"{name} must contain only finite values")
    return result


def _labels(value, n, name):
    array = np.asarray(value)
    _require(
        array.ndim == 1 and len(array) == n and array.dtype.kind in "USiu",
        f"{name} must contain one string or integer identifier per row",
    )
    array = array.astype(str)
    _require(all(array.tolist()), f"{name} identifiers must not be empty")
    return array


def _integer(value, name, *, minimum=0, maximum=None):
    _require(
        isinstance(value, (int, np.integer))
        and not isinstance(value, (bool, np.bool_))
        and value >= minimum
        and (maximum is None or value <= maximum),
        f"{name} must be an integer in the supported range",
    )
    return int(value)


def _indices(value, n, name):
    a = np.asarray(value)
    _require(
        a.ndim == 1
        and len(a) > 0
        and a.dtype.kind in "iu"
        and bool(np.all((a >= 0) & (a < n)))
        and len(np.unique(a)) == len(a),
        f"{name} must be distinct valid row indices",
    )
    return a.astype(np.int64)


def _representations(representations):
    _require(
        isinstance(representations, dict) and bool(representations),
        "named representation matrices required",
    )
    for name in representations:
        _require(
            isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name),
            "bounded representation identifiers required",
        )
    values = {name: _matrix(x, name) for name, x in representations.items()}
    _require(len({len(x) for x in values.values()}) == 1, "representation rows must align")
    return values


def _partition(folds, clusters, domains, n):
    f = _labels(folds, n, "folds")
    c = _labels(clusters, n, "clusters")
    d = _labels(domains if domains is not None else ["all"] * n, n, "domains")
    _require(len(np.unique(f)) >= 2, "cross-fitting requires at least two folds")
    assignments = {}
    for fold, cluster, domain in zip(f, c, d):
        key = (domain, cluster)
        _require(
            key not in assignments or assignments[key] == fold,
            "source clusters must not cross calibration/evaluation folds",
        )
        assignments[key] = fold
    return f, c, d


def pca_fit(calibration, *, variance_fraction=0.9):
    """Fit a centered, unscaled, unwhitened full basis using calibration rows."""
    x = _matrix(calibration, "calibration", min_rows=2)
    _require(
        np.isfinite(variance_fraction) and 0 < variance_fraction <= 1,
        "variance_fraction must lie in (0, 1]",
    )
    mean = x.mean(axis=0)
    centered = x - mean
    if bool(np.all(x == x[0])):
        centered.fill(0.0)
    _require(bool(np.isfinite(centered).all()), "centering overflow")
    try:
        _, singular, components = np.linalg.svd(centered, full_matrices=len(x) < x.shape[1])
    except np.linalg.LinAlgError as exc:
        raise LabError("PCA decomposition did not converge") from exc
    eigen = np.pad(singular**2 / (len(x) - 1), (0, x.shape[1] - len(singular)))
    _require(bool(np.isfinite(eigen).all()), "PCA variance overflow")
    total = float(eigen.sum())
    _require(np.isfinite(total), "total PCA variance overflow")
    ratios = eigen / total if total > 0 else np.zeros_like(eigen)
    rank = (
        min(x.shape[1], int(np.searchsorted(np.cumsum(ratios), variance_fraction) + 1))
        if total
        else 0
    )
    report = {
        "rows": len(x),
        "dimensions": x.shape[1],
        "centered": True,
        "scaled": False,
        "whitened": False,
        "variance_fraction": float(variance_fraction),
        "retained_rank": rank,
        "explained_variance_ratio": ratios.tolist(),
        "centered_rank": int(np.linalg.matrix_rank(centered)),
        "effective_dimension": float(1 / np.square(ratios).sum()) if total else 0.0,
        "degenerate": total == 0,
        "orthogonality_max_error": float(
            np.max(np.abs(components @ components.T - np.eye(x.shape[1])))
        ),
    }
    return report, {
        "mean": mean,
        "components": components,
        "singular_values": singular,
        "eigenvalues": eigen,
        "explained_variance_ratio": ratios,
    }


def _basis(x, fit, rank):
    _require(
        isinstance(fit, dict) and "mean" in fit and "components" in fit, "PCA fit arrays required"
    )
    mean = np.asarray(fit["mean"], dtype=np.float64)
    components = _matrix(fit["components"], "components")
    _require(
        mean.shape == (x.shape[1],)
        and bool(np.isfinite(mean).all())
        and components.shape == (x.shape[1], x.shape[1]),
        "PCA fit dimensions mismatch",
    )
    k = _integer(rank, "rank", maximum=x.shape[1])
    return mean, components[:k], k


def pca_transform(values, fit, rank=3):
    x = _matrix(values)
    mean, basis, _ = _basis(x, fit, rank)
    return (x - mean) @ basis.T


def pca_reconstruct(values, fit, rank, *, norm_match=False):
    """Norm matching uses an extra per-row scalar, not a pure rank-k code."""
    x = _matrix(values)
    mean, basis, _ = _basis(x, fit, rank)
    centered = x - mean
    projected = (centered @ basis.T) @ basis
    if norm_match:
        magnitude = np.linalg.norm(projected, axis=1)
        scale = np.divide(
            np.linalg.norm(centered, axis=1),
            magnitude,
            out=np.zeros(len(x)),
            where=magnitude > 1e-12,
        )
        projected *= scale[:, None]
    result = mean + projected
    _require(bool(np.isfinite(result).all()), "PCA reconstruction produced nonfinite values")
    return result


def random_subspace(dimensions, *, seed=0):
    """Deterministic Gaussian-QR orthonormal columns, including full width."""
    d = _integer(dimensions, "dimensions", minimum=1)
    seed = _integer(seed, "seed")
    q, r = np.linalg.qr(np.random.default_rng(seed).normal(size=(d, d)))
    return q * np.where(np.diag(r) < 0, -1.0, 1.0)[None, :]


def neighborhood_quality(original, embedded, *, ks=(5, 15), max_pairs=25_000_000):
    """Exact Euclidean trustworthiness and neighbor overlap with stable ties.

    Whole distance matrices are bounded explicitly; invalid k values are reported
    as unavailable, never converted to a perfect fidelity score.
    """
    x = _matrix(original)
    y = _matrix(embedded, "embedded", rows=len(x))
    n = len(x)
    _require(
        n * n <= _integer(max_pairs, "max_pairs", minimum=1), "neighborhood pair budget exceeded"
    )
    _require(isinstance(ks, (list, tuple)) and len(ks) > 0, "neighbor counts required")
    orders = []
    try:
        from scipy.spatial.distance import cdist
    except ImportError:
        cdist = None
    for a in (x, y):
        if cdist is not None:
            distances = cdist(a, a, metric="sqeuclidean")
        else:
            distances = np.empty((n, n), dtype=np.float64)
            # Subtraction avoids cancellation in squared-norm/dot-product distances.
            for i in range(n):
                distances[i] = np.square(a - a[i]).sum(axis=1)
        _require(bool(np.isfinite(distances).all()), "distance calculation overflow")
        np.fill_diagonal(distances, np.inf)
        orders.append(np.argsort(distances, axis=1, kind="stable"))
    ox, oy = orders
    ranks = np.empty_like(ox)
    ranks[np.arange(n)[:, None], ox] = np.arange(1, n + 1)[None, :]
    report = {
        "rows": n,
        "metric": "euclidean_original_dimensions",
        "tie_breaking": "stable row-index order; self excluded",
    }
    for value in ks:
        k = _integer(value, "neighbors", minimum=1)
        if k >= n / 2:
            report[f"k{k}"] = {"status": "UNAVAILABLE", "reason": "insufficient rows for k"}
            continue
        selected = np.take_along_axis(ranks, oy[:, :k], axis=1)
        penalty = np.maximum(selected - k, 0).sum()
        overlap = np.mean([len(set(a[:k]) & set(b[:k])) / k for a, b in zip(ox, oy)])
        report[f"k{k}"] = {
            "status": "COMPUTED",
            "trustworthiness": float(1 - 2 * penalty / (n * k * (2 * n - 3 * k - 1))),
            "neighbor_overlap": float(overlap),
        }
    return report


def latent_geometry(values, *, dimensions=3, neighbors=(5, 15), max_pairs=25_000_000):
    x = _matrix(values, min_rows=2)
    report, fit = pca_fit(x)
    k = min(_integer(dimensions, "projection dimensions", minimum=1), x.shape[1])
    coordinates = pca_transform(x, fit, k)
    norms = np.linalg.norm(x, axis=1)
    _require(bool(np.isfinite(norms).all()), "vector norm overflow")
    report.update(
        {
            "projection_dimensions": k,
            "projection_variance": float(fit["explained_variance_ratio"][:k].sum()),
            "unique_rows": int(len(np.unique(x, axis=0))),
            "norm_min": float(norms.min()),
            "norm_median": float(np.median(norms)),
            "norm_max": float(norms.max()),
            "scope": "observed vectors only",
            "quality": neighborhood_quality(x, coordinates, ks=neighbors, max_pairs=max_pairs),
        }
    )
    return report, {**fit, "coordinates": coordinates}


def tsne_projection(
    values, *, perplexity=30.0, seed=42, iterations=1000, neighbors=(5, 15), max_pairs=25_000_000
):
    """Optional sklearn t-SNE; fidelity is evaluated against the original space."""
    x = _matrix(values, min_rows=3)
    _require(
        np.isfinite(perplexity) and 0 < perplexity < len(x), "perplexity must be below row count"
    )
    seed = _integer(seed, "seed", maximum=2**32 - 1)
    iterations = _integer(iterations, "iterations", minimum=250)
    try:
        from sklearn.manifold import TSNE
    except ImportError as exc:
        raise LabError("t-SNE requires the optional scikit-learn projection dependency") from exc
    _, fit = pca_fit(x)
    k = min(50, x.shape[1], len(x))
    _require(k >= 2, "PCA-initialized t-SNE requires at least two dimensions")
    model = TSNE(
        n_components=2,
        perplexity=float(perplexity),
        learning_rate="auto",
        init="pca",
        max_iter=iterations,
        random_state=seed,
        method="barnes_hut",
        angle=0.5,
        n_jobs=1,
    )
    coordinates = model.fit_transform(pca_transform(x, fit, k))
    _matrix(coordinates, "t-SNE coordinates", rows=len(x))
    report = {
        "method": "t-SNE",
        "perplexity": float(perplexity),
        "seed": seed,
        "iterations_requested": iterations,
        "iterations_completed": int(model.n_iter_),
        "kl_divergence": float(model.kl_divergence_),
        "pre_pca_dimensions": k,
        "pre_pca_variance": float(fit["explained_variance_ratio"][:k].sum()),
        "quality": neighborhood_quality(x, coordinates, ks=neighbors, max_pairs=max_pairs),
        "scope": "local neighborhood map; island distances and sizes are not semantic scales",
    }
    _require(np.isfinite(report["kl_divergence"]), "t-SNE objective is not finite")
    return report, {"coordinates": coordinates}


def linear_cka(left, right):
    """Centered linear CKA, or None when either centered representation is zero."""
    x = _matrix(left)
    y = _matrix(right, "right", rows=len(x))
    if bool(np.all(x == x[0])) or bool(np.all(y == y[0])):
        return None
    # CKA is scale invariant; scaling first prevents avoidable squared overflow.
    a = x / max(float(np.abs(x).max()), 1e-300)
    b = y / max(float(np.abs(y).max()), 1e-300)
    a = a - a.mean(axis=0)
    b = b - b.mean(axis=0)
    denom = float(np.linalg.norm(a.T @ a) * np.linalg.norm(b.T @ b))
    if denom == 0:
        return None
    value = float(np.square(a.T @ b).sum() / denom)
    _require(np.isfinite(value) and -1e-10 <= value <= 1 + 1e-10, "invalid CKA calculation")
    return float(np.clip(value, 0, 1))


def cka_matrix(representations):
    values = _representations(representations)
    names = list(values)
    return {
        "models": names,
        "linear_cka": [[linear_cka(values[a], values[b]) for b in names] for a in names],
        "rows": len(next(iter(values.values()))),
        "scope": "matched observed vectors; similarity is not accuracy or training fairness",
    }


def conditional_permutations(
    tokens, domains, clusters=None, *, positions=None, position_bin=None, draws=100, seed=0
):
    tokens = _labels(tokens, len(tokens), "tokens")
    n = len(tokens)
    domains = _labels(domains, n, "domains")
    clusters = _labels(clusters, n, "clusters") if clusters is not None else None
    draws = _integer(draws, "draws", minimum=1)
    seed = _integer(seed, "seed")
    if position_bin is not None:
        position_bin = _integer(position_bin, "position_bin", minimum=1)
        p = np.asarray(positions)
        _require(
            p.shape == (n,) and p.dtype.kind in "iu" and bool(np.all(p >= 0)), "positions required"
        )
    elif positions is not None:
        p = np.asarray(positions)
        _require(
            p.shape == (n,) and p.dtype.kind in "iu" and bool(np.all(p >= 0)), "invalid positions"
        )
    cells = defaultdict(list)
    for i in range(n):
        key = (domains[i], tokens[i])
        if position_bin is not None:
            key += (int(p[i]) // position_bin,)
        cells[key].append(i)
    rng = np.random.default_rng(seed)
    permutations = np.tile(np.arange(n), (draws, 1))
    for permutation in permutations:
        for key in sorted(cells):
            indices = cells[key]
            if len(indices) > 1:
                order = rng.permutation(indices)
                permutation[order] = np.roll(order, 1)
    report = {
        "draws": draws,
        "seed": seed,
        "cells": len(cells),
        "position_bin": position_bin,
        "provides_p_value": False,
        "fraction_fixed_rows": float(np.mean(permutations == np.arange(n))),
        "fraction_cross_record_moves": float(np.mean(clusters[permutations] != clusters))
        if clusters is not None
        else None,
        "fraction_exact_positions_preserved": float(np.mean(p[permutations] == p))
        if positions is not None
        else None,
        "scope": "descriptive within-cell derangements; record dependence is not preserved",
    }
    return report, {"permutations": permutations}


def window_derangement(sequence_ids, domains, positions, *, seed=0):
    """Swap entire matching-layout windows within domain, preserving positions."""
    n = len(sequence_ids)
    sequence = _labels(sequence_ids, n, "sequence_ids")
    domain = _labels(domains, n, "domains")
    position = np.asarray(positions)
    _require(
        position.shape == (n,) and position.dtype.kind in "iu" and bool(np.all(position >= 0)),
        "integer positions required",
    )
    groups = defaultdict(list)
    for key in sorted(set(zip(domain.tolist(), sequence.tolist()))):
        rows = np.flatnonzero((domain == key[0]) & (sequence == key[1]))
        rows = rows[np.argsort(position[rows], kind="stable")]
        _require(len(np.unique(position[rows])) == len(rows), "window positions must be unique")
        groups[(key[0], tuple(position[rows].tolist()))].append(rows)
    permutation = np.arange(n)
    rng = np.random.default_rng(_integer(seed, "seed"))
    for windows in groups.values():
        if len(windows) > 1:
            order = rng.permutation(len(windows))
            for src, dst in zip(order, np.roll(order, 1)):
                permutation[windows[src]] = windows[dst]
    return {
        "seed": int(seed),
        "fraction_fixed_rows": float(np.mean(permutation == np.arange(n))),
        "provides_p_value": False,
        "scope": "within-domain whole-window descriptive reference",
    }, {"permutation": permutation}


def matched_context_pairs(tokens, domains, clusters, positions, *, position_bin=16, seed=0):
    n = len(tokens)
    t, d, c = (
        _labels(v, n, name)
        for v, name in [(tokens, "tokens"), (domains, "domains"), (clusters, "clusters")]
    )
    p = np.asarray(positions)
    _require(
        p.shape == (n,) and p.dtype.kind in "iu" and bool(np.all(p >= 0)),
        "integer positions required",
    )
    width = _integer(position_bin, "position_bin", minimum=1)
    cells = defaultdict(lambda: defaultdict(list))
    for i in range(n):
        cells[(d[i], t[i], int(p[i]) // width)][c[i]].append(i)
    rng = np.random.default_rng(_integer(seed, "seed"))
    pairs = []
    for key in sorted(cells):
        stacks = {record: list(rng.permutation(rows)) for record, rows in cells[key].items()}
        while True:
            available = sorted((r for r in stacks if stacks[r]), key=lambda r: (-len(stacks[r]), r))
            if len(available) < 2:
                break
            a, b = stacks[available[0]].pop(), stacks[available[1]].pop()
            pairs.append((int(a), int(b)) if c[a] < c[b] else (int(b), int(a)))
    return {
        "pairs": len(pairs),
        "used_rows": len(pairs) * 2,
        "coverage": 2 * len(pairs) / n if n else 0.0,
        "position_bin": width,
        "scope": "same-token/domain cross-record differences; not semantic isolation",
    }, {"pairs": np.asarray(pairs, dtype=np.int64).reshape(-1, 2)}


def token_conditioned_geometry(
    representations,
    tokens,
    domains,
    clusters,
    folds,
    *,
    min_calibration_clusters=2,
    positions=None,
    permutation_draws=0,
    bootstrap_draws=0,
    seed=0,
):
    """Cross-fit token/domain nuisance means with common support across models."""
    values = _representations(representations)
    n = len(next(iter(values.values())))
    tokens = _labels(tokens, n, "tokens")
    f, c, d = _partition(folds, clusters, domains, n)
    minimum = _integer(min_calibration_clusters, "min_calibration_clusters", minimum=1)
    permutation_draws = _integer(permutation_draws, "permutation_draws")
    bootstrap_draws = _integer(bootstrap_draws, "bootstrap_draws")
    report = {
        "models": list(values),
        "folds": [],
        "fit_targets_used": False,
        "scope": "current-token controlled geometry; residuals need not be semantic",
    }
    arrays = {}
    for fi, fold in enumerate(sorted(set(f))):
        calibration, evaluation = np.flatnonzero(f != fold), np.flatnonzero(f == fold)
        members, support = defaultdict(list), defaultdict(set)
        for i in calibration:
            key = (d[i], tokens[i])
            members[key].append(int(i))
            support[key].add(c[i])
        eligible = np.array(
            [i for i in evaluation if len(support[(d[i], tokens[i])]) >= minimum], dtype=int
        )
        coverage = {
            "evaluation_rows": len(evaluation),
            "eligible_rows": len(eligible),
            "coverage_fraction": len(eligible) / len(evaluation),
            "unseen_rows": sum(len(support[(d[i], tokens[i])]) == 0 for i in evaluation),
            "insufficient_support_rows": sum(
                0 < len(support[(d[i], tokens[i])]) < minimum for i in evaluation
            ),
        }
        prefix = f"fold_{fi}"
        arrays[prefix + "_calibration_indices"] = calibration
        arrays[prefix + "_evaluation_indices"] = evaluation
        arrays[prefix + "_eligible_indices"] = eligible
        row = {
            "fold": str(fold),
            "coverage": coverage,
            "status": "COMPUTED" if len(eligible) else "NO_ELIGIBLE_ROWS",
        }
        if not len(eligible):
            report["folds"].append(row)
            continue
        keys = sorted(members)
        key_index = {key: i for i, key in enumerate(keys)}
        domain_keys = sorted(set(d[calibration]))
        reps = {key: {} for key in ("raw", "domain_centered", "token_component", "residual")}
        r2 = {}
        for name, x in values.items():
            means = np.stack([x[members[key]].mean(axis=0) for key in keys])
            domain_means = np.stack(
                [x[calibration[d[calibration] == domain]].mean(axis=0) for domain in domain_keys]
            )
            predicted = means[[key_index[(d[i], tokens[i])] for i in eligible]]
            baseline = domain_means[[domain_keys.index(d[i]) for i in eligible]]
            actual = x[eligible]
            reps["raw"][name] = actual
            reps["domain_centered"][name] = actual - baseline
            reps["token_component"][name] = predicted - baseline
            reps["residual"][name] = actual - predicted
            sse = np.square(actual - predicted).sum(axis=1)
            sst = np.square(actual - baseline).sum(axis=1)
            _require(
                bool(np.isfinite(sse).all()) and bool(np.isfinite(sst).all()),
                "token reconstruction error overflow",
            )
            r2[name] = float(1 - sse.sum() / sst.sum()) if sst.sum() > 0 else None
            arrays[f"{prefix}_{name}_token_means"] = means
            arrays[f"{prefix}_{name}_domain_means"] = domain_means
            arrays[f"{prefix}_{name}_sse"] = sse
            arrays[f"{prefix}_{name}_baseline_sse"] = sst
            for kind in reps:
                arrays[f"{prefix}_{name}_{kind}"] = reps[kind][name]
        row.update(
            {
                "token_keys": [list(key) for key in keys],
                "domain_keys": domain_keys,
                "token_only_reconstruction_r2": r2,
                "cka": {kind: cka_matrix(xs) for kind, xs in reps.items()},
            }
        )
        raw = row["cka"]["domain_centered"]["linear_cka"]
        residual = row["cka"]["residual"]["linear_cka"]
        row["residual_minus_domain_centered_cka"] = [
            [None if a is None or b is None else a - b for a, b in zip(ar, br)]
            for ar, br in zip(residual, raw)
        ]
        if bootstrap_draws:
            row["bootstrap"] = {}
            for kind, xs in reps.items():
                summary, saved = cka_bootstrap(
                    xs, c[eligible], domains=d[eligible], draws=bootstrap_draws, seed=seed + fi
                )
                row["bootstrap"][kind] = summary
                arrays.update({f"{prefix}_{kind}_{key}": value for key, value in saved.items()})
            # Identical bootstrap cluster draws across representations make this a paired contrast.
            valid = arrays[prefix + "_residual_valid"] & arrays[prefix + "_domain_centered_valid"]
            difference = (
                arrays[prefix + "_residual_bootstrap"]
                - arrays[prefix + "_domain_centered_bootstrap"]
            )
            arrays[prefix + "_cka_difference_bootstrap"] = np.where(valid, difference, 0.0)
            arrays[prefix + "_cka_difference_valid"] = valid
            row["cka_difference_ci95"] = _interval_matrix(difference, valid)
            cluster_keys = list(dict.fromkeys(zip(d[eligible].tolist(), c[eligible].tolist())))
            memberships = [
                np.array(
                    [(domain, cluster) == key for domain, cluster in zip(d[eligible], c[eligible])]
                )
                for key in cluster_keys
            ]
            draws = arrays[prefix + "_raw_cluster_draws"]
            row["token_only_reconstruction_r2_ci95"] = {}
            for name in values:
                sse = arrays[f"{prefix}_{name}_sse"]
                sst = arrays[f"{prefix}_{name}_baseline_sse"]
                numerators = np.array([sse[mask].sum() for mask in memberships])[draws].sum(axis=1)
                denominators = np.array([sst[mask].sum() for mask in memberships])[draws].sum(
                    axis=1
                )
                valid_r2 = denominators > 0
                boot_r2 = np.divide(
                    numerators, denominators, out=np.zeros(len(draws)), where=valid_r2
                )
                boot_r2 = np.where(valid_r2, 1 - boot_r2, 0.0)
                arrays[f"{prefix}_{name}_r2_bootstrap"] = boot_r2
                arrays[f"{prefix}_{name}_r2_valid"] = valid_r2
                row["token_only_reconstruction_r2_ci95"][name] = (
                    np.quantile(boot_r2[valid_r2], [0.025, 0.975]).tolist()
                    if valid_r2.any()
                    else None
                )
        if permutation_draws:
            row["permutation_references"] = {}
            for width in [None, 16] if positions is not None else [None]:
                tag = "token_domain" if width is None else "token_domain_position16"
                summary, saved = conditional_permutations(
                    tokens[eligible],
                    d[eligible],
                    c[eligible],
                    positions=np.asarray(positions)[eligible] if positions is not None else None,
                    position_bin=width,
                    draws=permutation_draws,
                    seed=seed + 1000 + fi,
                )
                arrays[f"{prefix}_{tag}_permutations"] = saved["permutations"]
                row["permutation_references"][tag] = summary
                for kind in ("raw", "residual"):
                    names = list(values)
                    matrices = [
                        [
                            [linear_cka(reps[kind][a], reps[kind][b][permutation]) for b in names]
                            for a in names
                        ]
                        for permutation in saved["permutations"]
                    ]
                    row["permutation_references"][tag][kind + "_cka"] = matrices
        if positions is not None:
            row["matched_context_differences"] = {}
            for width in (1, 16):
                summary, saved = matched_context_pairs(
                    tokens[eligible],
                    d[eligible],
                    c[eligible],
                    np.asarray(positions)[eligible],
                    position_bin=width,
                    seed=seed + fi,
                )
                pairs = saved["pairs"]
                arrays[f"{prefix}_position{width}_pairs"] = eligible[pairs]
                if len(pairs):
                    deltas = {
                        name: x[pairs[:, 0]] - x[pairs[:, 1]] for name, x in reps["raw"].items()
                    }
                    summary["cka"] = cka_matrix(deltas)
                    summary["token_mean_cancels"] = all(
                        np.allclose(
                            deltas[name], x[pairs[:, 0]] - x[pairs[:, 1]], rtol=1e-12, atol=1e-12
                        )
                        for name, x in reps["residual"].items()
                    )
                row["matched_context_differences"][str(width)] = summary
        report["folds"].append(row)
    return report, arrays


def _interval_matrix(values, valid):
    return [
        [
            np.quantile(values[:, i, j][valid[:, i, j]], [0.025, 0.975]).tolist()
            if bool(valid[:, i, j].any())
            else None
            for j in range(values.shape[2])
        ]
        for i in range(values.shape[1])
    ]


def cka_bootstrap(
    representations, clusters, *, domains=None, draws=5000, seed=0, max_gram_entries=50_000_000
):
    """Whole-record stratified bootstrap CKA, re-centered on every draw.

    Fits stay fixed. Degenerate draws are masked explicitly, not scored as zero.
    Point estimates use matched rows; record resampling preserves whole records
    and within-domain record counts, rather than averaging separate domain CKAs.
    """
    from .statistics import make_bootstrap

    values = _representations(representations)
    n, m = len(next(iter(values.values()))), len(values)
    c = _labels(clusters, n, "clusters")
    d = _labels(domains if domains is not None else ["all"] * n, n, "domains")
    draws = _integer(draws, "draws", minimum=2)
    seed = _integer(seed, "seed")
    _require(
        n * n * m <= _integer(max_gram_entries, "max_gram_entries", minimum=1),
        "CKA Gram entry budget exceeded",
    )
    keys = list(dict.fromkeys(zip(d.tolist(), c.tolist())))
    lookup = {key: i for i, key in enumerate(keys)}
    labels = np.array([lookup[(domain, record)] for domain, record in zip(d, c)])
    h = np.eye(len(keys))[labels]
    plan = make_bootstrap(
        np.arange(len(keys)), strata=[key[0] for key in keys], draws=draws, seed=seed
    )
    indices = np.asarray(plan.indices)
    _require(indices.shape == (draws, len(keys)), "unexpected bootstrap-plan dimensions")
    multiplicities = np.zeros((len(keys), draws))
    np.add.at(multiplicities, (indices.ravel(), np.repeat(np.arange(draws), len(keys))), 1)
    grams, projections = [], []
    for x in values.values():
        a = x / max(float(np.abs(x).max()), 1e-300)
        a -= a.mean(axis=0)
        if bool(np.all(x == x[0])):
            a.fill(0.0)
        gram = a @ a.T
        grams.append(gram)
        projections.append(gram @ h)
    products = {(i, j): h.T @ (grams[i] * grams[j]) @ h for i in range(m) for j in range(i, m)}
    boot = np.zeros((draws, m, m))
    valid = np.zeros_like(boot, dtype=bool)
    for lo in range(0, draws, 128):
        v = multiplicities[:, lo : lo + 128]
        w = h @ v
        count = w.sum(axis=0)
        gp = [projection @ v for projection in projections]
        gq = [np.sum(w * p, axis=0) for p in gp]
        terms = [np.sum(v * (products[i, i] @ v), axis=0) for i in range(m)]
        centering = [2 * np.sum(w * gp[i] * gp[i], axis=0) / count for i in range(m)]
        self_values = [terms[i] - centering[i] + gq[i] ** 2 / count**2 for i in range(m)]
        tolerances = [
            64 * np.finfo(float).eps * np.maximum(np.abs(terms[i]) + np.abs(centering[i]), 1e-300)
            for i in range(m)
        ]
        for i in range(m):
            for j in range(i, m):
                denominator = np.sqrt(np.maximum(self_values[i], 0) * np.maximum(self_values[j], 0))
                good = (self_values[i] > tolerances[i]) & (self_values[j] > tolerances[j])
                numerator = (
                    np.sum(v * (products[i, j] @ v), axis=0)
                    - 2 * np.sum(w * gp[i] * gp[j], axis=0) / count
                    + gq[i] * gq[j] / count**2
                )
                score = np.divide(numerator, denominator, out=np.zeros_like(numerator), where=good)
                _require(bool(np.all(np.isfinite(score))), "nonfinite bootstrap CKA")
                _require(
                    bool(np.all((score[good] >= -1e-7) & (score[good] <= 1 + 1e-7))),
                    "unstable bootstrap CKA",
                )
                boot[lo : lo + len(count), i, j] = boot[lo : lo + len(count), j, i] = np.clip(
                    score, 0, 1
                )
                valid[lo : lo + len(count), i, j] = valid[lo : lo + len(count), j, i] = good
    report = {
        **cka_matrix(values),
        "ci95": _interval_matrix(boot, valid),
        "valid_draws": valid.sum(axis=0).tolist(),
        "draws": draws,
        "bootstrap": plan.manifest(),
        "uncertainty": (
            "whole-record stratified bootstrap; nuisance fits fixed; degenerate"
            " draws explicitly excluded"
        ),
    }
    return report, {"bootstrap": boot, "valid": valid, "cluster_draws": indices}


def decoder_metric_fit(calibration, output_weights, rank, *, ridge_ratio=1e-6, rotation_seed=None):
    """Fit same-rank PCA in a centered-base-logit metric, without targets.

    Nonlinear softcaps and mixtures are outside this objective; evaluate them
    through the native readout callback, never by substituting this affine proxy.
    """
    x = _matrix(calibration, "calibration", min_rows=2)
    weight = _matrix(output_weights, "output_weights")
    d = x.shape[1]
    _require(weight.shape[1] == d and len(weight) >= 2, "vocabulary output-weight shape mismatch")
    k = _integer(rank, "rank", maximum=d)
    _require(np.isfinite(ridge_ratio) and ridge_ratio > 0, "positive finite ridge ratio required")
    centered_weight = weight - weight.mean(axis=0)
    m0 = centered_weight.T @ centered_weight / len(weight)
    epsilon = float(ridge_ratio * np.trace(m0) / d)
    _require(
        np.isfinite(epsilon) and epsilon > 0, "decoder weights have no finite centered variation"
    )
    rotation = np.eye(d)
    if rotation_seed is not None:
        rotation = random_subspace(d, seed=rotation_seed)
    metric = rotation @ m0 @ rotation.T + epsilon * np.eye(d)
    eigen, vectors = np.linalg.eigh(metric)
    _require(bool(np.all(eigen > 0)), "decoder metric must be positive definite")
    root = (vectors * np.sqrt(eigen)) @ vectors.T
    inverse = (vectors * (1 / np.sqrt(eigen))) @ vectors.T
    _, plain = pca_fit(x)
    mean, centered = plain["mean"], x - plain["mean"]
    _, _, basis = np.linalg.svd(centered @ root, full_matrices=len(x) < d)
    q = basis[:k].T
    encoder, decoder = root @ q, q.T @ inverse
    projection = encoder @ decoder
    aware = (centered @ encoder) @ decoder
    ordinary = (centered @ plain["components"][:k].T) @ plain["components"][:k]
    objective = float(np.square((centered - aware) @ root).sum())
    objective_plain = float(np.square((centered - ordinary) @ root).sum())
    full_error = float(np.max(np.abs(root @ inverse - np.eye(d))))
    identity_error = float(np.max(np.abs(decoder @ encoder - np.eye(k)))) if k else 0.0
    idempotence = float(np.max(np.abs(projection @ projection - projection)))
    weighted_symmetry = float(np.max(np.abs(projection @ metric - (projection @ metric).T)))
    _require(
        full_error < 1e-7 and identity_error < 1e-7 and idempotence < 1e-7,
        "decoder reconstruction identity check failed",
    )
    _require(
        weighted_symmetry <= max(1e-8, float(np.max(np.abs(metric))) * 1e-9),
        "decoder weighted-symmetry check failed",
    )
    _require(
        objective <= objective_plain + max(1e-8, abs(objective_plain) * 1e-9),
        "decoder metric objective exceeds plain PCA objective",
    )
    pc_response = np.square(plain["components"] @ centered_weight.T).sum(axis=1) / len(weight)
    variances = np.pad(plain["singular_values"] ** 2, (0, d - len(plain["singular_values"])))
    contributions = variances * pc_response
    explicit_energy = float(np.square(centered @ centered_weight.T).sum() / len(weight))
    _require(
        bool(np.isclose(contributions.sum(), explicit_energy, rtol=1e-9, atol=1e-8)),
        "calibration logit-energy decomposition failed",
    )
    report = {
        "rank": k,
        "dimensions": d,
        "ridge_epsilon": epsilon,
        "metric_condition_number": float(eigen.max() / eigen.min()),
        "calibration_objective": objective,
        "plain_pca_objective": objective_plain,
        "full_rank_identity_max_error": full_error,
        "encoder_decoder_identity_max_error": identity_error,
        "projection_idempotence_max_error": idempotence,
        "weighted_symmetry_max_error": weighted_symmetry,
        "discarded_hidden_variance_fraction": float(plain["explained_variance_ratio"][k:].sum()),
        "discarded_centered_logit_variance_fraction": float(
            contributions[k:].sum() / explicit_energy
        )
        if explicit_energy > 0
        else None,
        "rotation_seed": rotation_seed,
        "objective": "calibration centered-base-logit squared error plus ridge hidden error",
        "fit_targets_used": False,
        "scope": "base-logit proxy; not native NLL or nonlinear-distribution optimization",
    }
    return report, {
        "mean": mean,
        "encoder": encoder,
        "decoder": decoder,
        "metric": metric,
        "root": root,
        "inverse_root": inverse,
        "metric_eigenvalues": eigen,
        "centered_weight": centered_weight,
        "rotation": rotation,
        "per_pc_decoder_response": pc_response,
        "per_pc_logit_energy": contributions,
    }


def decoder_metric_reconstruct(values, fit):
    x = _matrix(values)
    _require(
        isinstance(fit, dict) and {"mean", "encoder", "decoder"} <= set(fit),
        "decoder fit arrays required",
    )
    mean = np.asarray(fit["mean"], dtype=float)
    encoder, decoder = (
        np.asarray(fit["encoder"], dtype=float),
        np.asarray(fit["decoder"], dtype=float),
    )
    _require(
        mean.shape == (x.shape[1],)
        and encoder.ndim == decoder.ndim == 2
        and encoder.shape[0] == decoder.shape[1] == x.shape[1]
        and encoder.shape[1] == decoder.shape[0]
        and all(np.isfinite(a).all() for a in (mean, encoder, decoder)),
        "invalid decoder fit dimensions or values",
    )
    result = mean + ((x - mean) @ encoder) @ decoder
    _require(bool(np.isfinite(result).all()), "decoder reconstruction produced nonfinite values")
    return result


def compression_diagnostic(
    hidden,
    targets,
    readout,
    *,
    folds,
    clusters,
    domains=None,
    ranks=(0, 1, 2, 4, 8, 16, 32, 64, 128, 256, 512),
    variance_fraction=0.9,
    norm_matched=True,
    random_seeds=(11, 23, 37),
    decoder_weights=None,
    decoder_rotation_seed=None,
    readout_kind="logits",
    readout_kwargs=None,
    observed_native_scores=None,
    replay_atol=1e-5,
    full_rank_atol=1e-4,
    nll_margin=0.01,
    accuracy_margin=0.005,
):
    """Cross-fit head reconstruction and evaluate with the exact native readout.

    Ordinary PCA, norm-matched controls and Gaussian-QR subspaces share source
    folds. Optional decoder-aware fits use exactly the calibration PCA variance
    rank. Target labels are passed only to scoring, never to any fitting method.
    This changes head inputs; it does not compress a recurrent state or measure
    speed/memory savings. Retained row-level paired outcomes support later CIs.
    """
    from .calibration import (
        _decode,
        _movement,
        _replay_check,
        _targets,
        probability_metrics,
        record_domain_weights,
    )

    h = _matrix(hidden, "hidden", min_rows=4)
    n, d = h.shape
    f, c, domains = _partition(folds, clusters, domains, n)
    fold_keys = sorted(set(f))
    _require(isinstance(ranks, (list, tuple)) and bool(ranks), "fixed rank grid required")
    grid = sorted({_integer(rank, "rank") for rank in ranks})
    omitted = [rank for rank in grid if rank > d]
    grid = sorted({rank for rank in grid if rank <= d} | {0, d})
    _require(type(norm_matched) is bool, "norm_matched must be boolean")
    _require(isinstance(random_seeds, (list, tuple)), "fixed random seeds required")
    seeds = list(dict.fromkeys(_integer(seed, "random seed") for seed in random_seeds))
    for margin in (full_rank_atol, nll_margin, accuracy_margin):
        _require(
            np.isfinite(margin) and margin >= 0, "nonnegative finite diagnostic tolerances required"
        )
    conditions = [{"name": "native", "method": "native", "rank": d, "norm_matched": False}]
    for rank in [*grid, "variance"]:
        tag = f"k{rank}" if isinstance(rank, int) else "variance"
        conditions.append(
            {"name": "pca_" + tag, "method": "pca", "rank": rank, "norm_matched": False}
        )
        if norm_matched:
            conditions.append(
                {
                    "name": "pca_" + tag + "_norm_matched",
                    "method": "pca",
                    "rank": rank,
                    "norm_matched": True,
                }
            )
        for seed in seeds:
            conditions.append(
                {
                    "name": f"random_seed{seed}_" + tag,
                    "method": "random",
                    "rank": rank,
                    "random_seed": seed,
                    "norm_matched": False,
                }
            )
    if decoder_weights is not None:
        weight = _matrix(decoder_weights, "decoder_weights")
        _require(weight.shape[1] == d, "decoder weight width mismatch")
        conditions.extend(
            [
                {
                    "name": "decoder_aware_variance",
                    "method": "decoder",
                    "rank": "variance",
                    "norm_matched": False,
                },
                {"name": "decoder_full", "method": "decoder", "rank": d, "norm_matched": False},
            ]
        )
        if decoder_rotation_seed is not None:
            _integer(decoder_rotation_seed, "decoder_rotation_seed")
            conditions.append(
                {
                    "name": "decoder_rotated_variance",
                    "method": "decoder_rotated",
                    "rank": "variance",
                    "norm_matched": False,
                }
            )
    else:
        weight = None
        _require(decoder_rotation_seed is None, "rotated decoder control requires decoder weights")
    native_lp = _decode(readout, h, np.arange(n), readout_kind, readout_kwargs)
    target = _targets(targets, n, native_lp.shape[1])
    native_replay = _replay_check(native_lp, observed_native_scores, readout_kind, replay_atol)
    _, baseline = probability_metrics(native_lp, target, reference_logp=native_lp)
    baseline.update(_movement(h, h))
    baseline["centered_energy_ratio_before_norm_match"] = np.ones(n)
    if weight is not None:
        baseline["centered_base_logit_mse"] = np.zeros(n)
    count = len(conditions)
    arrays = {name: np.zeros((count, n), dtype=value.dtype) for name, value in baseline.items()}
    for name, value in baseline.items():
        arrays[name][0] = value
    rank_by_fold = np.zeros((count, len(fold_keys)), dtype=np.int64)
    rank_by_fold[0] = d
    random_bases = {seed: random_subspace(d, seed=seed) for seed in seeds}
    arrays.update({f"random_basis_seed{seed}": basis for seed, basis in random_bases.items()})
    fit_reports = []
    for fi, fold in enumerate(fold_keys):
        calibration, evaluation = np.flatnonzero(f != fold), np.flatnonzero(f == fold)
        report, fit = pca_fit(h[calibration], variance_fraction=variance_fraction)
        k_variance = report["retained_rank"]
        prefix = f"fold_{fi}"
        arrays[prefix + "_calibration_indices"] = calibration
        arrays[prefix + "_evaluation_indices"] = evaluation
        arrays.update({prefix + "_pca_" + name: value for name, value in fit.items()})
        report.update(
            {
                "fold": str(fold),
                "calibration_clusters": len(set(zip(domains[calibration], c[calibration]))),
                "evaluation_clusters": len(set(zip(domains[evaluation], c[evaluation]))),
                "evaluation_rows": len(evaluation),
                "decoder_fits": {},
            }
        )
        centered = h[evaluation] - fit["mean"]
        energy = np.maximum(np.square(centered).sum(axis=1), 1e-30)
        decoder_fits = {}
        for i, condition in enumerate(conditions[1:], 1):
            rank = k_variance if condition["rank"] == "variance" else condition["rank"]
            rank_by_fold[i, fi] = rank
            method = condition["method"]
            if method in ("pca", "random"):
                basis = (
                    fit["components"]
                    if method == "pca"
                    else random_bases[condition["random_seed"]].T
                )
                projected = (centered @ basis[:rank].T) @ basis[:rank]
                energy_ratio = np.square(projected).sum(axis=1) / energy
                if condition["norm_matched"]:
                    norms = np.linalg.norm(projected, axis=1)
                    scales = np.divide(
                        np.linalg.norm(centered, axis=1),
                        norms,
                        out=np.zeros(len(evaluation)),
                        where=norms > 1e-12,
                    )
                    projected = projected * scales[:, None]
                reconstructed = fit["mean"] + projected
            else:
                cache_key = (method, rank)
                if cache_key not in decoder_fits:
                    fit_report, decoder_fit = decoder_metric_fit(
                        h[calibration],
                        weight,
                        rank,
                        rotation_seed=decoder_rotation_seed
                        if method == "decoder_rotated"
                        else None,
                    )
                    decoder_fits[cache_key] = decoder_fit
                    report["decoder_fits"][condition["name"]] = fit_report
                    arrays.update(
                        {
                            f"{prefix}_{condition['name']}_{name}": value
                            for name, value in decoder_fit.items()
                        }
                    )
                reconstructed = decoder_metric_reconstruct(h[evaluation], decoder_fits[cache_key])
                energy_ratio = np.square(reconstructed - fit["mean"]).sum(axis=1) / energy
            lp = _decode(readout, reconstructed, evaluation, readout_kind, readout_kwargs)
            _, metrics = probability_metrics(
                lp, target[evaluation], reference_logp=native_lp[evaluation]
            )
            metrics.update(_movement(reconstructed, h[evaluation]))
            metrics["centered_energy_ratio_before_norm_match"] = energy_ratio
            if weight is not None:
                centered_weight = weight - weight.mean(axis=0)
                metrics["centered_base_logit_mse"] = np.square(
                    (reconstructed - h[evaluation]) @ centered_weight.T
                ).mean(axis=1)
            for name, value in metrics.items():
                _require(
                    bool(np.isfinite(value).all()), "compression scoring produced nonfinite values"
                )
                arrays[name][i, evaluation] = value
        fit_reports.append(report)
    arrays.update(
        {
            "condition_names": np.asarray([spec["name"] for spec in conditions]),
            "target": target,
            "folds": f,
            "clusters": c,
            "domains": domains,
            "rank_by_fold": rank_by_fold,
            "delta_nll": arrays["nll"] - arrays["nll"][[0]],
            "delta_accuracy": arrays["correct"].astype(float)
            - arrays["correct"][[0]].astype(float),
        }
    )
    native_full = [
        i for i, spec in enumerate(conditions) if spec["name"] in (f"pca_k{d}", "decoder_full")
    ]
    full_checks = []
    for i in native_full:
        error = float(np.abs(arrays["nll"][i] - arrays["nll"][0]).max())
        max_kl = float(arrays["kl"][i].max())
        _require(
            error <= full_rank_atol and max_kl <= full_rank_atol,
            "full-rank native readout reconstruction failed",
        )
        full_checks.append(
            {
                "condition": conditions[i]["name"],
                "max_abs_nll_error": error,
                "max_kl": max_kl,
                "argmax_changes": int(np.sum(arrays["prediction"][i] != arrays["prediction"][0])),
                "max_hidden_mse": float(arrays["hidden_mse"][i].max()),
            }
        )
    weights = record_domain_weights(c, domains)
    summaries = []
    for i, spec in enumerate(conditions):
        delta_nll, delta_accuracy = (
            float(arrays["delta_nll"][i] @ weights),
            float(arrays["delta_accuracy"][i] @ weights),
        )
        summaries.append(
            {
                **spec,
                "ranks_by_fold": rank_by_fold[i].tolist(),
                "nll": float(arrays["nll"][i] @ weights),
                "accuracy": float(arrays["correct"][i] @ weights),
                "delta_nll": delta_nll,
                "delta_accuracy": delta_accuracy,
                "kl": float(arrays["kl"][i] @ weights),
                "prediction_change_fraction": float(arrays["prediction_changed"][i] @ weights),
                "hidden_mse": float(arrays["hidden_mse"][i] @ weights),
                "point_preserved": bool(
                    delta_nll <= nll_margin and delta_accuracy >= -accuracy_margin
                ),
                "interval_preserved": None,
            }
        )
    if weight is not None:
        plain_i = next(i for i, spec in enumerate(conditions) if spec["name"] == "pca_variance")
        aware_i = next(
            i for i, spec in enumerate(conditions) if spec["name"] == "decoder_aware_variance"
        )
        arrays["decoder_minus_pca_variance_delta_nll"] = (
            arrays["nll"][aware_i] - arrays["nll"][plain_i]
        )
        arrays["decoder_minus_pca_variance_delta_accuracy"] = arrays["correct"][aware_i].astype(
            float
        ) - arrays["correct"][plain_i].astype(float)
    return {
        "conditions": summaries,
        "folds": fit_reports,
        "omitted_ranks_above_width": omitted,
        "fit_targets_used": False,
        "native_replay": native_replay,
        "full_rank_replay": {
            "passed": True,
            "tolerance": float(full_rank_atol),
            "conditions": full_checks,
        },
        "preservation_margins": {
            "delta_nll_max": float(nll_margin),
            "accuracy_loss_max": float(accuracy_margin),
        },
        "uncertainty": (
            "row-level paired outcomes retained; interval preservation requires"
            " source-cluster analysis"
        ),
        "norm_matching": (
            "extra per-row scalar; undefined zero projection stays at calibration mean"
        ),
        "weighting": "equal records within domain, equal domains",
        "scope": (
            "cross-fitted frozen-head reconstruction; no recurrent-state "
            "compression or runtime-savings claim"
        ),
        "scientific_qualification": "NOT_QUALIFIED",
    }, arrays
