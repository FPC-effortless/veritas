"""Frozen native-readout interventions and calibration-only selection.

Readouts are caller-supplied trusted callbacks with the signature
``readout(hidden, row_indices=..., **readout_kwargs)``. Their output semantics
must be declared as logits or normalized log probabilities. Biases, softcaps,
lookup IDs and nonlinear mixture gates stay inside that callback.
"""

from __future__ import annotations

import numpy as np

from ..runner import LabError
from .geometry import _indices, _integer, _labels, _matrix, _require


def log_softmax(logits):
    x = _matrix(logits, "logits")
    centered = x - x.max(axis=1, keepdims=True)
    _require(bool(np.isfinite(centered).all()), "logit range overflow")
    result = centered - np.log(np.exp(centered).sum(axis=1, keepdims=True))
    _require(bool(np.isfinite(result).all()), "log-softmax produced nonfinite values")
    return result


def _log_probabilities(value, *, rows=None):
    x = _matrix(value, "log probabilities", rows=rows)
    _require(x.shape[1] >= 2, "at least two output categories required")
    _require(
        bool(np.all(x <= 1e-6))
        and bool(np.allclose(np.exp(x).sum(axis=1), 1.0, atol=1e-6, rtol=1e-6)),
        "readout must return normalized log probabilities",
    )
    return x


def _scores_to_logp(scores, kind, *, rows=None):
    _require(
        kind in ("logits", "log_probabilities"),
        "declare readout_kind as logits or log_probabilities",
    )
    scores = _matrix(scores, "native readout", rows=rows)
    return _log_probabilities(log_softmax(scores) if kind == "logits" else scores, rows=rows)


def _decode(readout, hidden, row_indices, kind, kwargs=None):
    _require(callable(readout), "a caller-supplied native readout is required")
    kwargs = {} if kwargs is None else dict(kwargs)
    _require("row_indices" not in kwargs, "row_indices are owned by the diagnostic")
    try:
        output = readout(
            np.array(hidden, copy=True), row_indices=np.array(row_indices, copy=True), **kwargs
        )
    except LabError:
        raise
    except Exception as exc:
        raise LabError("native readout callback failed") from exc
    return _scores_to_logp(output, kind, rows=len(hidden))


def _targets(targets, n, vocabulary):
    y = np.asarray(targets)
    _require(
        y.shape == (n,) and y.dtype.kind in "iu" and bool(np.all((y >= 0) & (y < vocabulary))),
        "targets must be aligned integer category IDs",
    )
    return y.astype(np.int64)


def _weights(weights, n):
    if weights is None:
        return np.full(n, 1 / n)
    w = np.asarray(weights, dtype=float)
    _require(
        w.shape == (n,)
        and bool(np.isfinite(w).all())
        and bool(np.all(w >= 0))
        and np.isfinite(w.sum())
        and w.sum() > 0,
        "weights must be aligned finite nonnegative values with positive total",
    )
    return w / w.sum()


def record_domain_weights(clusters, domains=None, *, windows=None):
    """Equal records within domain, equal domains; optional equal windows/record."""
    n = len(clusters)
    _require(n > 0, "record weighting requires observations")
    c = _labels(clusters, n, "clusters")
    d = _labels(domains if domains is not None else ["all"] * n, n, "domains")
    window = _labels(windows, n, "windows") if windows is not None else None
    result = np.zeros(n)
    domain_keys = sorted(set(d))
    for domain in domain_keys:
        records = sorted(set(c[d == domain]))
        for record in records:
            mask = (d == domain) & (c == record)
            mass = 1 / (len(domain_keys) * len(records))
            if window is None:
                result[mask] = mass / mask.sum()
            else:
                wins = sorted(set(window[mask]))
                for win in wins:
                    eligible = mask & (window == win)
                    result[eligible] = mass / (len(wins) * eligible.sum())
    return result


def temperature_scale(log_probabilities, temperature):
    """Apply positive temperature AFTER the native mixture distribution."""
    lp = _log_probabilities(log_probabilities)
    _require(
        isinstance(temperature, (int, float, np.number))
        and not isinstance(temperature, (bool, np.bool_))
        and np.isfinite(temperature)
        and temperature > 0,
        "temperature must be finite and positive",
    )
    result = log_softmax(lp / float(temperature))
    _require(
        bool(np.array_equal(lp.argmax(axis=1), result.argmax(axis=1))),
        "temperature changed argmax; numerical range is unsupported",
    )
    return result


def probability_metrics(log_probabilities, targets, *, reference_logp=None, weights=None, bins=10):
    """Finite per-row outcomes plus weighted NLL/Brier/reliability summaries."""
    lp = _log_probabilities(log_probabilities)
    n, vocabulary = lp.shape
    y = _targets(targets, n, vocabulary)
    w = _weights(weights, n)
    bins = _integer(bins, "bins", minimum=1, maximum=1000)
    p = np.exp(lp)
    prediction = lp.argmax(axis=1)
    confidence = p[np.arange(n), prediction]
    arrays = {
        "nll": -lp[np.arange(n), y],
        "prediction": prediction,
        "correct": prediction == y,
        "confidence": confidence,
        "entropy": -np.sum(p * lp, axis=1),
        "brier": np.square(p).sum(axis=1) - 2 * p[np.arange(n), y] + 1,
    }
    if reference_logp is not None:
        reference = _log_probabilities(reference_logp, rows=n)
        _require(reference.shape == lp.shape, "reference vocabulary mismatch")
        ref = np.exp(reference)
        kl = np.sum(ref * (reference - lp), axis=1)
        _require(bool(np.all(kl >= -1e-6)), "negative KL beyond numerical tolerance")
        arrays.update(
            {
                "kl": np.maximum(kl, 0.0),
                "total_variation": 0.5 * np.abs(ref - p).sum(axis=1),
                "prediction_changed": prediction != reference.argmax(axis=1),
            }
        )
    report = {
        "rows": n,
        "vocabulary": vocabulary,
        "weighting": "supplied normalized row weights" if weights is not None else "equal rows",
        "nll": float(w @ arrays["nll"]),
        "accuracy": float(w @ arrays["correct"]),
        "brier": float(w @ arrays["brier"]),
        "entropy": float(w @ arrays["entropy"]),
        "confidence": float(w @ confidence),
    }
    if reference_logp is not None:
        report.update(
            {key: float(w @ arrays[key]) for key in ("kl", "total_variation", "prediction_changed")}
        )
    bin_indices = np.minimum((confidence * bins).astype(int), bins - 1)
    reliability, ece = [], 0.0
    for i in range(bins):
        selected = bin_indices == i
        mass = float(w[selected].sum())
        conf = float(w[selected] @ confidence[selected] / mass) if mass else None
        acc = float(w[selected] @ arrays["correct"][selected] / mass) if mass else None
        if mass:
            ece += mass * abs(conf - acc)
        reliability.append(
            {
                "bin": [i / bins, (i + 1) / bins],
                "rows": int(selected.sum()),
                "weight": mass,
                "confidence": conf,
                "accuracy": acc,
            }
        )
    report.update(
        {
            "ece": float(ece),
            "reliability": reliability,
            "calibration_scope": "fixed equal-width bins; NLL, Brier and ECE are separate criteria",
        }
    )
    return report, arrays


def _movement(hidden, native):
    delta = hidden - native
    norm, base = np.linalg.norm(hidden, axis=1), np.linalg.norm(native, axis=1)
    product = norm * base
    cosine = np.divide(
        np.sum(hidden * native, axis=1), product, out=np.zeros(len(hidden)), where=product > 0
    )
    cosine[(norm == 0) & (base == 0)] = 1.0
    result = {
        "hidden_mse": np.square(delta).mean(axis=1),
        "head_absolute_change": np.linalg.norm(delta, axis=1),
        "relative_hidden_change": np.linalg.norm(delta, axis=1) / np.maximum(base, 1e-12),
        "hidden_cosine_distance": 1 - np.clip(cosine, -1, 1),
    }
    _require(
        all(np.isfinite(value).all() for value in result.values()), "head-vector metric overflow"
    )
    return result


def _replay_check(native_lp, observed_native_scores, kind, tolerance):
    _require(
        np.isfinite(tolerance) and tolerance >= 0, "finite nonnegative replay tolerance required"
    )
    if observed_native_scores is None:
        return {
            "status": "NOT_VERIFIED",
            "passed": None,
            "reason": "independent native outputs were not supplied",
        }
    observed = _scores_to_logp(observed_native_scores, kind, rows=len(native_lp))
    _require(observed.shape == native_lp.shape, "native replay vocabulary mismatch")
    maximum = float(np.max(np.abs(observed - native_lp)))
    mismatches = int(np.sum(observed.argmax(axis=1) != native_lp.argmax(axis=1)))
    _require(maximum <= tolerance and mismatches == 0, "native readout replay failed")
    return {
        "status": "VERIFIED",
        "passed": True,
        "max_abs_log_probability_error": maximum,
        "argmax_mismatches": mismatches,
        "tolerance": float(tolerance),
    }


def native_readout_contrast(
    native_hidden,
    conditions,
    targets,
    readout,
    *,
    readout_kind="logits",
    readout_kwargs=None,
    condition_kwargs=None,
    observed_native_scores=None,
    replay_atol=1e-5,
    weights=None,
    retain_log_probabilities=False,
):
    """Evaluate changed head inputs through the exact caller's native decoder."""
    h = _matrix(native_hidden, "native_hidden")
    _require(
        isinstance(conditions, dict) and "native" not in conditions,
        "conditions must be named and exclude reserved native",
    )
    variants = {"native": h}
    for name, value in conditions.items():
        _require(isinstance(name, str) and 0 < len(name) <= 120, "bounded condition name required")
        changed = _matrix(value, name, rows=len(h))
        _require(changed.shape == h.shape, "intervened head shape mismatch")
        variants[name] = changed
    supplied = {} if condition_kwargs is None else dict(condition_kwargs)
    _require(set(supplied) <= set(variants), "condition kwargs reference unknown conditions")
    names, reports, saved = list(variants), [], {}
    native_lp = None
    for name, changed in variants.items():
        kwargs = {**(readout_kwargs or {}), **supplied.get(name, {})}
        lp = _decode(readout, changed, np.arange(len(h)), readout_kind, kwargs)
        if native_lp is None:
            native_lp = lp
        summary, metrics = probability_metrics(
            lp, targets, reference_logp=native_lp, weights=weights
        )
        metrics.update(_movement(changed, h))
        for key, value in metrics.items():
            saved.setdefault(key, []).append(value)
        if retain_log_probabilities:
            saved.setdefault("log_probabilities", []).append(lp)
        reports.append({"name": name, **summary})
    arrays = {key: np.stack(value) for key, value in saved.items()}
    arrays.update(
        {
            "condition_names": np.asarray(names),
            "target": _targets(targets, len(h), native_lp.shape[1]),
            "native_log_probabilities": native_lp,
            "delta_nll": arrays["nll"] - arrays["nll"][[0]],
            "delta_accuracy": arrays["correct"].astype(float)
            - arrays["correct"][[0]].astype(float),
        }
    )
    w = _weights(weights, len(h))
    for i, report in enumerate(reports):
        report.update(
            {
                "delta_nll": float(arrays["delta_nll"][i] @ w),
                "delta_accuracy": float(arrays["delta_accuracy"][i] @ w),
            }
        )
    return {
        "conditions": reports,
        "native_replay": _replay_check(
            native_lp, observed_native_scores, readout_kind, replay_atol
        ),
        "scope": (
            "frozen prediction_path_only; native trajectory and writer are caller responsibilities"
        ),
        "readout_kind": readout_kind,
        "scientific_qualification": "NOT_QUALIFIED",
    }, arrays


def component_readout_diagnostics(
    prebank,
    bank_read,
    targets,
    readout,
    *,
    donor_indices=None,
    clusters=None,
    domains=None,
    positions=None,
    successor_ids=None,
    readout_kind="logits",
    readout_kwargs=None,
    observed_native_scores=None,
    replay_atol=1e-5,
):
    """Bank, successor, head-only and gate-only lesions on cached native inputs.

    The callback must honor gate_hidden, gate_mode and no_mixture. This function
    never approximates the gate or successor mixture as an affine head.
    """
    base = _matrix(prebank, "prebank")
    bank = _matrix(bank_read, "bank_read", rows=len(base))
    _require(bank.shape == base.shape, "bank and prebank shapes must match")
    native = base + bank
    variants = {
        "bank_read_removed": base,
        "successor_removed": native,
        "both_removed": base,
        "head_only_bank_removed": base,
        "gate_only_bank_removed": native,
    }
    kw = {
        "native": {"gate_hidden": native, "gate_mode": "adaptive", "no_mixture": False},
        "bank_read_removed": {"gate_hidden": base, "gate_mode": "adaptive", "no_mixture": False},
        "successor_removed": {"gate_hidden": native, "gate_mode": "adaptive", "no_mixture": True},
        "both_removed": {"gate_hidden": base, "gate_mode": "adaptive", "no_mixture": True},
        "head_only_bank_removed": {
            "gate_hidden": native,
            "gate_mode": "adaptive",
            "no_mixture": False,
        },
        "gate_only_bank_removed": {
            "gate_hidden": base,
            "gate_mode": "adaptive",
            "no_mixture": False,
        },
    }
    if donor_indices is not None:
        donor = np.asarray(donor_indices)
        _require(
            donor.shape == (len(base),)
            and donor.dtype.kind in "iu"
            and bool(np.all((donor >= 0) & (donor < len(base)))),
            "aligned donor row indices required",
        )
        _require(clusters is not None, "donor controls require source-cluster identities")
        c = _labels(clusters, len(base), "clusters")
        d = _labels(domains if domains is not None else ["all"] * len(base), len(base), "domains")
        _require(
            bool(np.all(c[donor] != c)) and bool(np.all(d[donor] == d)),
            "bank donors must come from distinct records in the same domain",
        )
        if positions is not None:
            position = np.asarray(positions)
            _require(
                position.shape == (len(base),)
                and position.dtype.kind in "iu"
                and bool(np.all(position >= 0))
                and bool(np.array_equal(position[donor], position)),
                "bank donors must preserve relative positions",
            )
        swapped = base + bank[donor]
        variants["swapped_bank_read"] = swapped
        kw["swapped_bank_read"] = {
            "gate_hidden": swapped,
            "gate_mode": "adaptive",
            "no_mixture": False,
        }
    weight = record_domain_weights(clusters, domains) if clusters is not None else None
    report, arrays = native_readout_contrast(
        native,
        variants,
        targets,
        readout,
        readout_kind=readout_kind,
        readout_kwargs=readout_kwargs,
        condition_kwargs=kw,
        observed_native_scores=observed_native_scores,
        replay_atol=replay_atol,
        weights=weight,
    )
    indices = {name: i for i, name in enumerate(arrays["condition_names"])}
    loss = arrays["nll"]
    arrays["factorial_nll_interaction"] = (
        loss[indices["both_removed"]]
        - loss[indices["bank_read_removed"]]
        - loss[indices["successor_removed"]]
        + loss[0]
    )
    arrays["head_gate_nll_nonadditivity"] = (
        loss[indices["bank_read_removed"]]
        - loss[indices["head_only_bank_removed"]]
        - loss[indices["gate_only_bank_removed"]]
        + loss[0]
    )
    if donor_indices is not None:
        arrays["donor_indices"] = np.asarray(donor_indices)
        report["donor_position_match"] = (
            "VERIFIED" if positions is not None else "NOT_VERIFIED_WITHOUT_POSITIONS"
        )
    report["contrast_definitions"] = {
        "factorial_nll_interaction": (
            "both_removed - bank_read_removed - successor_removed + native"
        ),
        "head_gate_nll_nonadditivity": (
            "bank_read_removed - head_only_bank_removed - gate_only_bank_removed + native"
        ),
    }
    n = len(base)
    domain = _labels(domains if domains is not None else ["all"] * n, n, "domains")
    masks = {"domain_" + name: domain == name for name in sorted(set(domain))}
    if successor_ids is not None:
        successor = np.asarray(successor_ids)
        _require(
            successor.shape == (n,) and successor.dtype.kind in "iu",
            "aligned successor IDs required",
        )
        available = successor >= 0
        masks.update(
            {
                "successor_unavailable": ~available,
                "successor_available": available,
                "successor_correct": available & (successor == arrays["target"]),
                "successor_wrong": available & (successor != arrays["target"]),
            }
        )
    report["strata"] = []
    for name, mask in masks.items():
        weight = (
            record_domain_weights(np.asarray(clusters)[mask], domain[mask])
            if clusters is not None and mask.any()
            else None
        )
        report["strata"].append(
            {
                "name": name,
                "rows": int(mask.sum()),
                "conditional_on_target_correctness": name
                in ("successor_correct", "successor_wrong"),
                "conditions": [
                    {
                        "name": str(condition),
                        "delta_nll": float(
                            arrays["delta_nll"][i, mask] @ _weights(weight, int(mask.sum()))
                        ),
                        "delta_accuracy": float(
                            arrays["delta_accuracy"][i, mask] @ _weights(weight, int(mask.sum()))
                        ),
                    }
                    for i, condition in enumerate(arrays["condition_names"])
                ]
                if mask.any()
                else [],
            }
        )
    return report, arrays


def select_calibration_settings(losses, conditions, clusters, domains=None, *, draws=0, seed=0):
    """Select from CALIBRATION losses only; evaluation arrays are not accepted."""
    loss = _matrix(losses, "calibration condition losses")
    _require(bool(np.all(loss >= -1e-8)), "calibration NLL losses must be nonnegative")
    _require(
        isinstance(conditions, (list, tuple)) and len(conditions) == len(loss),
        "condition metadata mismatch",
    )
    names = []
    for condition in conditions:
        _require(
            isinstance(condition, dict)
            and {"name", "gain", "temperature", "gate_mode", "vector_mode"} <= set(condition),
            "gain, temperature and control-mode metadata required",
        )
        _require(
            isinstance(condition["name"], str) and condition["name"] not in names,
            "distinct condition names required",
        )
        _require(
            np.isfinite(condition["gain"])
            and np.isfinite(condition["temperature"])
            and condition["temperature"] > 0,
            "invalid gain/temperature condition",
        )
        names.append(condition["name"])
    n = loss.shape[1]
    c = _labels(clusters, n, "calibration clusters")
    d = _labels(domains if domains is not None else ["all"] * n, n, "calibration domains")
    objective = loss @ record_domain_weights(c, d)
    adaptive = [
        i
        for i, spec in enumerate(conditions)
        if spec["gate_mode"] == "adaptive" and spec["vector_mode"] == "gain"
    ]
    options = {
        "nonnegative_gain": [
            i for i in adaptive if conditions[i]["gain"] >= 0 and conditions[i]["temperature"] == 1
        ],
        "signed_gain": [i for i in adaptive if conditions[i]["temperature"] == 1],
        "temperature_only": [i for i in adaptive if conditions[i]["gain"] == 1],
        "joint": [i for i in adaptive if conditions[i]["gain"] >= 0],
    }
    _require(all(options.values()), "calibration grid must include native gain and temperature")

    def pick(values, choices):
        return min(
            choices,
            key=lambda i: (
                float(values[i]),
                abs(conditions[i]["gain"] - 1) + abs(np.log(conditions[i]["temperature"])),
                conditions[i]["gain"],
                conditions[i]["temperature"],
            ),
        )

    selected = {}
    for name, choices in options.items():
        i = pick(objective, choices)
        selected[name] = {
            "index": int(i),
            "name": conditions[i]["name"],
            "condition": dict(conditions[i]),
            "calibration_nll": float(objective[i]),
            "gain_boundary": conditions[i]["gain"]
            in (
                min(conditions[j]["gain"] for j in choices),
                max(conditions[j]["gain"] for j in choices),
            ),
            "temperature_boundary": conditions[i]["temperature"]
            in (
                min(conditions[j]["temperature"] for j in choices),
                max(conditions[j]["temperature"] for j in choices),
            ),
        }
    draws = _integer(draws, "draws")
    seed = _integer(seed, "seed")
    bootstrap_manifests = []
    if draws:
        from .statistics import make_bootstrap

        boot = np.zeros((draws, len(conditions)))
        domain_keys = sorted(set(d))
        for j, domain in enumerate(domain_keys):
            records = sorted(set(c[d == domain]))
            means = np.stack(
                [loss[:, (d == domain) & (c == record)].mean(axis=1) for record in records]
            )
            plan = make_bootstrap(records, draws=draws, seed=seed + j)
            boot += plan.replicates(means) / len(domain_keys)
            bootstrap_manifests.append(plan.manifest())
        for name, choices in options.items():
            picks = [pick(row, choices) for row in boot]
            selected[name]["bootstrap_selection_counts"] = {
                conditions[i]["name"]: picks.count(i) for i in choices
            }
    return {
        "selections": selected,
        "calibration_objectives": objective.tolist(),
        "uses_evaluation_rows": False,
        "bootstrap_draws": draws,
        "bootstrap_plans": bootstrap_manifests,
        "tie_rule": "minimum objective; minimum abs(gain-1)+abs(log(T)); smaller gain; smaller T",
        "weighting": "equal records within domain, equal domains",
        "scope": "selection stability does not refit evaluation intervals",
    }


def bank_gain_diagnostics(
    prebank,
    bank_read,
    targets,
    readout,
    *,
    gains=(-2.0, -1.0, -0.5, 0.0, 0.125, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0),
    temperatures=(0.5, 0.75, 1.0, 1.25, 1.5, 2.0),
    calibration_indices=None,
    evaluation_indices=None,
    clusters=None,
    domains=None,
    successor_ids=None,
    include_fixed_gate=True,
    include_mean_controls=True,
    selection_draws=0,
    seed=0,
    readout_kind="logits",
    readout_kwargs=None,
    observed_native_scores=None,
    replay_atol=1e-5,
):
    """Gain/temperature grid with optional disjoint-record calibration selection.

    Gain modifies the head and adaptive gate. Temperature follows the native
    successor mixture. The callback's native gate uses its supplied native context.
    Mean-bank controls are unavailable unless a calibration split is declared.
    """
    base = _matrix(prebank, "prebank")
    bank = _matrix(bank_read, "bank_read", rows=len(base))
    _require(base.shape == bank.shape, "bank and prebank shapes must match")
    n = len(base)
    gain_values = np.asarray(gains, dtype=float)
    temp_values = np.asarray(temperatures, dtype=float)
    _require(
        gain_values.ndim == temp_values.ndim == 1
        and len(gain_values)
        and len(temp_values)
        and bool(np.isfinite(gain_values).all())
        and bool(np.isfinite(temp_values).all())
        and bool(np.all(temp_values > 0)),
        "finite gain and positive temperature grids required",
    )
    gains = list(dict.fromkeys([1.0, *gain_values.tolist()]))
    temperatures = list(dict.fromkeys([1.0, *temp_values.tolist()]))
    c = _labels(clusters, n, "clusters") if clusters is not None else None
    d = _labels(domains if domains is not None else ["all"] * n, n, "domains")
    _require(
        (calibration_indices is None) == (evaluation_indices is None),
        "declare both calibration and evaluation indices",
    )
    calibration = evaluation = None
    mean_bank = None
    if calibration_indices is not None:
        _require(c is not None, "calibration selection requires source-cluster identities")
        calibration = _indices(calibration_indices, n, "calibration_indices")
        evaluation = _indices(evaluation_indices, n, "evaluation_indices")
        _require(not set(calibration) & set(evaluation), "calibration and evaluation rows overlap")
        _require(
            not set(zip(d[calibration], c[calibration])) & set(zip(d[evaluation], c[evaluation])),
            "calibration and evaluation source clusters overlap",
        )
        mean_bank = record_domain_weights(c[calibration], d[calibration]) @ bank[calibration]
    conditions = [
        {
            "name": "native",
            "gain": 1.0,
            "temperature": 1.0,
            "gate_mode": "adaptive",
            "vector_mode": "gain",
        }
    ]
    for gain in gains:
        for temperature in temperatures:
            if gain == temperature == 1:
                continue
            conditions.append(
                {
                    "name": f"gain_{gain:g}_temperature_{temperature:g}",
                    "gain": gain,
                    "temperature": temperature,
                    "gate_mode": "adaptive",
                    "vector_mode": "gain",
                }
            )
    if include_fixed_gate:
        conditions.extend(
            {
                "name": f"gain_{gain:g}_fixed_native_gate",
                "gain": gain,
                "temperature": 1.0,
                "gate_mode": "native",
                "vector_mode": "gain",
            }
            for gain in gains
        )
    if include_mean_controls and mean_bank is not None:
        conditions.extend(
            {
                "name": name,
                "gain": 1.0,
                "temperature": 1.0,
                "gate_mode": "adaptive",
                "vector_mode": mode,
            }
            for name, mode in [
                ("calibration_mean_bank_only", "mean"),
                ("centered_bank", "centered"),
            ]
        )
    cache, saved, summaries = {}, {}, []
    native_lp = None
    weights = record_domain_weights(c, d) if c is not None else None
    for condition in conditions:
        gain, mode, vector = condition["gain"], condition["gate_mode"], condition["vector_mode"]
        key = (gain, mode, vector)
        if key not in cache:
            changed = base + (
                gain * bank
                if vector == "gain"
                else mean_bank
                if vector == "mean"
                else bank - mean_bank
            )
            kwargs = {
                **(readout_kwargs or {}),
                "gate_mode": mode,
                "gate_hidden": changed,
                "no_mixture": False,
            }
            cache[key] = _decode(readout, changed, np.arange(n), readout_kind, kwargs)
        unscaled = cache[key]
        lp = (
            unscaled
            if condition["temperature"] == 1
            else temperature_scale(unscaled, condition["temperature"])
        )
        if native_lp is None:
            native_lp = lp
        summary, metrics = probability_metrics(
            lp, targets, reference_logp=native_lp, weights=weights
        )
        for name, value in metrics.items():
            saved.setdefault(name, []).append(value)
        summaries.append({"condition": condition, **summary})
    arrays = {name: np.stack(value) for name, value in saved.items()}
    y = _targets(targets, n, native_lp.shape[1])
    arrays.update(
        {
            "condition_names": np.asarray([spec["name"] for spec in conditions]),
            "target": y,
            "delta_nll": arrays["nll"] - arrays["nll"][[0]],
            "delta_accuracy": arrays["correct"].astype(float)
            - arrays["correct"][[0]].astype(float),
            "native_log_probabilities": native_lp,
        }
    )
    fixed_gate_check = None
    if include_fixed_gate:
        error = float(np.max(np.abs(cache[(1.0, "native", "gain")] - native_lp)))
        _require(
            error <= replay_atol
            and bool(
                np.array_equal(
                    cache[(1.0, "native", "gain")].argmax(axis=1), native_lp.argmax(axis=1)
                )
            ),
            "gain-one fixed-native-gate control differs from native",
        )
        fixed_gate_check = {"passed": True, "max_abs_log_probability_error": error}
    report = {
        "conditions": summaries,
        "native_replay": _replay_check(
            native_lp, observed_native_scores, readout_kind, replay_atol
        ),
        "fixed_native_gate_control": fixed_gate_check,
        "positive_temperature_argmax_invariant": True,
        "grid_summary_scope": (
            "all supplied rows; calibration selection and held-out evaluation are separate sections"
        ),
        "temperature_semantics": "softmax(log native_mixed_probability / temperature)",
        "mean_controls": "calibration equal-record/domain mean"
        if mean_bank is not None
        else "UNAVAILABLE_WITHOUT_CALIBRATION",
        "scope": "frozen prediction_path_only; no writer/backbone intervention",
        "scientific_qualification": "NOT_QUALIFIED",
    }
    if calibration is not None:
        chosen = select_calibration_settings(
            arrays["nll"][:, calibration],
            conditions,
            c[calibration],
            d[calibration],
            draws=selection_draws,
            seed=seed,
        )
        report["selection"] = chosen
        arrays.update(
            {
                "calibration_indices": calibration,
                "evaluation_indices": evaluation,
                "calibration_mean_bank": mean_bank,
            }
        )
        ew = record_domain_weights(c[evaluation], d[evaluation])
        report["evaluation"] = [
            {
                "name": condition["name"],
                **{
                    metric: float(arrays[metric][i, evaluation] @ ew)
                    for metric in (
                        "nll",
                        "confidence",
                        "entropy",
                        "brier",
                        "kl",
                        "total_variation",
                        "delta_nll",
                        "delta_accuracy",
                    )
                },
                "accuracy": float(arrays["correct"][i, evaluation] @ ew),
            }
            for i, condition in enumerate(conditions)
        ]
        indices = {spec["name"]: i for i, spec in enumerate(conditions)}
        selected = chosen["selections"]
        contrasts = [
            ("selected_nonnegative_gain_minus_native", selected["nonnegative_gain"]["index"], 0),
            (
                "selected_joint_minus_temperature_only",
                selected["joint"]["index"],
                selected["temperature_only"]["index"],
            ),
        ]
        if "gain_0_temperature_1" in indices:
            contrasts.append(
                (
                    "selected_nonnegative_gain_minus_bank_zero",
                    selected["nonnegative_gain"]["index"],
                    indices["gain_0_temperature_1"],
                )
            )
        report["primary_contrasts"] = []
        for name, left, right in contrasts:
            delta = arrays["nll"][left, evaluation] - arrays["nll"][right, evaluation]
            arrays[name] = delta
            report["primary_contrasts"].append(
                {
                    "name": name,
                    "left": conditions[left]["name"],
                    "right": conditions[right]["name"],
                    "delta_nll": float(delta @ ew),
                    "delta_brier": float(
                        (arrays["brier"][left, evaluation] - arrays["brier"][right, evaluation])
                        @ ew
                    ),
                    "uncertainty": "row-level effects retained; selected settings held fixed",
                }
            )
        edges = np.quantile(arrays["confidence"][0, calibration], [0.25, 0.5, 0.75])
        report["calibration_native_confidence_quartile_edges"] = edges.tolist()
        quartiles = np.digitize(arrays["confidence"][0], edges)
        masks = {f"calibration_confidence_quartile_{i + 1}": quartiles == i for i in range(4)}
        if successor_ids is not None:
            successor = np.asarray(successor_ids)
            _require(
                successor.shape == (n,) and successor.dtype.kind in "iu",
                "aligned successor IDs required",
            )
            available = successor >= 0
            masks.update(
                {
                    "successor_unavailable": ~available,
                    "successor_available": available,
                    "successor_correct": available & (successor == y),
                    "successor_wrong": available & (successor != y),
                }
            )
            if include_fixed_gate and bool((~available).any()):
                errors = [
                    float(
                        np.max(
                            np.abs(
                                cache[(gain, "native", "gain")][~available]
                                - cache[(gain, "adaptive", "gain")][~available]
                            )
                        )
                    )
                    for gain in gains
                ]
                _require(max(errors) <= replay_atol, "unavailable successor still depends on gate")
                report["unavailable_successor_gate_invariance"] = {
                    "passed": True,
                    "max_error": max(errors),
                }
        masks.update({"domain_" + domain: d == domain for domain in sorted(set(d[evaluation]))})
        report["strata"] = []
        selected_indices = sorted(
            {
                0,
                *(spec["index"] for spec in selected.values()),
                *[i for i, spec in enumerate(conditions) if spec["vector_mode"] != "gain"],
            }
        )
        for name, mask in masks.items():
            rows = evaluation[mask[evaluation]]
            sw = record_domain_weights(c[rows], d[rows]) if len(rows) else None
            report["strata"].append(
                {
                    "name": name,
                    "rows": len(rows),
                    "conditional_on_target_correctness": name
                    in ("successor_correct", "successor_wrong"),
                    "conditions": [
                        {
                            "name": conditions[i]["name"],
                            "delta_nll": float(arrays["delta_nll"][i, rows] @ sw),
                        }
                        for i in selected_indices
                    ]
                    if len(rows)
                    else [],
                }
            )
    return report, arrays
