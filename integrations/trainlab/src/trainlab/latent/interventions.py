"""Frozen-model intervention construction, execution and conditional diagnostics.

All sequence comparisons use the same supplied continuation. These utilities do
not generate model-dependent continuations, train a model, or grant qualification.
"""

from __future__ import annotations

import numpy as np

from ..runner import LabError

READ_NAMES = ("cursor", "first", "second", "destination")


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _array(value, *, ndim=None, integer=False):
    a = np.asarray(value)
    _require(
        a.dtype.kind in ("biu" if integer else "biuf")
        and a.size > 0
        and (ndim is None or a.ndim == ndim)
        and np.isfinite(a).all(),
        "finite nonempty numeric array with expected dimensions required",
    )
    return a


def _indices(value, size, shape):
    a = _array(value, integer=True)
    _require(
        a.shape == shape and np.all(a >= 0) and np.all(a < size),
        "index shape or bounds differ from declared input",
    )
    return a.astype(np.int64, copy=False)


def suffix_intervention(
    input_ids,
    anchors,
    retained_prior,
    *,
    donor_indices=None,
    shuffle=False,
    seed=0,
    permutations=None,
):
    """Change only bytes strictly before anchor-retained_prior; retain positions.

    The caller freezes donor maps before inspecting outcomes. Supplied permutation
    matrices allow every model to receive the identical shuffle and identity sham.
    Donor/domain independence is a panel-design property, not inferred here.
    """
    x = _array(input_ids, ndim=2, integer=True)
    n, length = x.shape
    anchors = _indices(anchors, length, (n,))
    _require(
        type(retained_prior) is int and retained_prior >= 0 and type(shuffle) is bool,
        "nonnegative suffix length and explicit shuffle flag required",
    )
    _require(not (shuffle and donor_indices is not None), "choose transplant or shuffle")
    _require(permutations is None or shuffle, "permutations require shuffle mode")
    donor = np.arange(n) if donor_indices is None else _indices(donor_indices, n, (n,))
    cuts = np.maximum(anchors - retained_prior, 0)
    order = np.broadcast_to(np.arange(length), x.shape).copy()
    if permutations is not None:
        order = _indices(permutations, length, x.shape).copy()
    rng = np.random.default_rng(seed)
    edited = x.copy()
    for row, cut in enumerate(cuts):
        if shuffle:
            if permutations is None:
                order[row, :cut] = rng.permutation(cut)
            _require(
                np.array_equal(np.sort(order[row, :cut]), np.arange(cut))
                and np.array_equal(order[row, cut:], np.arange(cut, length)),
                "shuffle must permute only the eligible prefix",
            )
            edited[row, :cut] = x[row, order[row, :cut]]
        else:
            edited[row, :cut] = x[donor[row], :cut]
        _require(np.array_equal(edited[row, cut:], x[row, cut:]), "suffix changed")
    return {
        "input_ids": edited,
        "permutations": order,
        "donor_indices": donor.copy(),
        "cuts": cuts,
        "current_suffix_and_future_preserved": True,
        "position_order_preserved": True,
        "prefix_histogram_preserved": bool(shuffle),
        "scope": "FIXED_DONOR_OR_SHUFFLE_CONDITIONAL_OOD_POSSIBLE",
    }


def position_ids(
    length,
    *,
    offset=0,
    query_positions=(),
    query_reset=(),
    filler_range=None,
    filler_wrap=None,
    table_size=None,
):
    """Return lookup IDs only. Physical attention order and input bytes stay fixed."""
    _require(
        type(length) is int and 0 < length <= 65536 and type(offset) is int and offset >= 0,
        "bounded length and nonnegative integer offset required",
    )
    ids = np.arange(length, dtype=np.int64) + offset
    _require(
        (filler_range is None) == (filler_wrap is None), "filler range and wrap required together"
    )
    if filler_range is not None:
        _require(
            len(filler_range) == len(filler_wrap) == 2
            and all(type(i) is int for i in (*filler_range, *filler_wrap)),
            "integer filler interval and wrap pair required",
        )
        start, stop = filler_range
        base, period = filler_wrap
        _require(
            0 <= start <= stop <= length and base >= 0 and period > 0,
            "invalid filler lookup interval",
        )
        ids[start:stop] = base + np.arange(stop - start) % period
    _require(
        len(query_positions) == len(query_reset), "query positions and replacement lengths differ"
    )
    if len(query_positions):
        query = _indices(query_positions, length, (len(query_positions),))
        repl = _array(query_reset, ndim=1, integer=True)
        _require(
            len(set(query.tolist())) == len(query) and np.all(repl >= 0),
            "unique query positions and nonnegative replacements required",
        )
        ids[query] = repl
    if table_size is not None:
        _require(
            type(table_size) is int and table_size > 0 and int(ids.max()) < table_size,
            "position intervention exceeds learned table",
        )
    return ids


def read_footprint(trace, slots):
    """Union of all current value reads, including active cursor and destination."""
    _require(
        type(trace) is dict
        and all(k in trace for k in READ_NAMES)
        and type(slots) is int
        and slots > 0,
        "complete hard-address trace required",
    )
    arrays = [_array(trace[key], integer=True) for key in READ_NAMES]
    shape = arrays[0].shape
    _require(all(a.shape == shape for a in arrays), "address trace shape mismatch")
    result = np.zeros((*shape, slots), dtype=bool)
    for a in arrays:
        a = _indices(a, slots, shape)
        np.put_along_axis(result, a[..., None], True, axis=-1)
    return result


def _logp(logits):
    z = _array(logits).astype(np.float64)
    _require(z.ndim >= 2 and z.shape[-1] >= 2, "full-vocabulary logits required")
    z = z - z.max(-1, keepdims=True)
    return z - np.log(np.exp(z).sum(-1, keepdims=True))


def response_metrics(native, edited, *, targets=None, alternate_targets=None):
    """Per-observation distribution changes; no pseudoreplicated confidence interval."""
    native = _array(native)
    edited = _array(edited)
    _require(native.shape == edited.shape, "paired output shapes differ")
    a, b = _logp(native), _logp(edited)
    p, q = np.exp(a), np.exp(b)
    pred_a, pred_b = native.argmax(-1), edited.argmax(-1)
    changed = pred_a != pred_b
    result = {
        "kl": np.maximum((p * (a - b)).sum(-1), 0.0),
        "total_variation": 0.5 * np.abs(p - q).sum(-1),
        "exact_output_changed": np.any(native != edited, axis=-1),
        "max_abs_logit_delta": np.abs(edited.astype(float) - native).max(-1),
        "prediction_changed": changed,
        "prediction_change_rate": float(changed.mean()),
        "prediction_native": pred_a,
        "prediction_edited": pred_b,
    }
    if targets is not None:
        targets = _indices(targets, native.shape[-1], native.shape[:-1])
        result.update(
            native_nll=-np.take_along_axis(a, targets[..., None], -1)[..., 0],
            edited_nll=-np.take_along_axis(b, targets[..., None], -1)[..., 0],
            native_correct=pred_a == targets,
            edited_correct=pred_b == targets,
        )
        result["delta_nll"] = result["edited_nll"] - result["native_nll"]
        if alternate_targets is not None:
            other = _indices(alternate_targets, native.shape[-1], native.shape[:-1])
            _require(np.all(targets != other), "counterfactual answers must differ")
            result["alternate_answer_rate"] = float(np.mean(pred_b == other))
            result["correct_to_alternate_rate"] = float(
                np.mean((pred_a == targets) & (pred_b == other))
            )
    else:
        _require(alternate_targets is None, "alternate answers need true targets")
    return result


def state_distances(left, right):
    """Keep value/link/cursor/history retention separate from output sensitivity."""
    _require(
        type(left) is dict and type(right) is dict and left and set(left) == set(right),
        "matching named state fields required",
    )
    result = {"exact": True, "fields": {}}
    for name in sorted(left):
        a, b = _array(left[name]), _array(right[name])
        _require(a.shape == b.shape, "state field shapes differ")
        exact = bool(np.array_equal(a, b))
        result["exact"] &= exact
        if a.ndim:
            delta = (b.astype(float) - a).reshape(len(a), -1)
            scale = np.linalg.norm(a.astype(float).reshape(len(a), -1), axis=1)
            norm = np.linalg.norm(delta, axis=1)
        else:
            norm, scale = np.abs(b.astype(float) - a), np.abs(a.astype(float))
        result["fields"][name] = {
            "exact": exact,
            "l2": norm,
            "relative_l2": norm / np.maximum(scale, 1e-12),
        }
    return result


def _first_true(mask):
    return np.where(mask.any(-1), mask.argmax(-1), -1)


def analyze_future_access(
    native_logits,
    branch_logits,
    native_trace,
    branch_trace,
    initially_changed_rows,
    *,
    kl_threshold=1e-8,
    targets=None,
    trained_horizon=None,
    start_position=0,
):
    """Test the necessary no-output-effect-before-access invariant, not sufficiency.

    Initial changed rows are followed along BOTH trajectories; later overwritten
    rows remain included, a conservative trace of initial edit locations.
    """
    native = _array(native_logits, ndim=3)
    branch = _array(branch_logits, ndim=3)
    mask = _array(initially_changed_rows, ndim=2)
    _require(
        mask.dtype.kind == "b"
        and mask.shape[0] == native.shape[0]
        and native.shape == branch.shape
        and np.isfinite(kl_threshold)
        and kl_threshold >= 0,
        "invalid paired future-access observations",
    )
    shape = native.shape[:2]
    base_reads, edit_reads = (
        read_footprint(native_trace, mask.shape[-1]),
        read_footprint(branch_trace, mask.shape[-1]),
    )
    _require(
        base_reads.shape[:2] == edit_reads.shape[:2] == shape,
        "trajectory trace and logits do not align",
    )
    base_touch = np.any(base_reads & mask[:, None, :], -1)
    edit_touch = np.any(edit_reads & mask[:, None, :], -1)
    first_access = _first_true(base_touch | edit_touch)
    metrics = response_metrics(native, branch, targets=targets)
    first_change = _first_true(metrics["exact_output_changed"])
    violation = (first_change >= 0) & ((first_access < 0) | (first_change < first_access))
    _require(
        type(start_position) is int and start_position >= 0, "nonnegative start position required"
    )
    primary = np.ones(shape[1], dtype=bool)
    if trained_horizon is not None:
        _require(
            type(trained_horizon) is int and trained_horizon > 0,
            "positive trained horizon required",
        )
        primary = start_position + np.arange(shape[1]) < trained_horizon
    return {
        "status": "FAILED" if violation.any() else "TESTED",
        **metrics,
        "first_access": first_access,
        "first_native_access": _first_true(base_touch),
        "first_branch_access": _first_true(edit_touch),
        "first_output_change": first_change,
        "first_kl_exceedance": _first_true(metrics["kl"] > kl_threshold),
        "preaccess_violations": violation,
        "preaccess_violation_count": int(violation.sum()),
        "native_touches": base_touch,
        "branch_touches": edit_touch,
        "within_trained_horizon": primary,
        "shared_true_continuation": True,
        "interpretation": (
            "Access is necessary for this value-only edit; access alone does "
            "not establish useful recall."
        ),
    }


def _invoke(ctx, operation, *args, phase="answer", **kwargs):
    return ctx.invoke(operation, *args, phase=phase, **kwargs)


def native_parity(ctx, *, input_ids):
    """Compare actual native forward, instrumented extraction and decoder replay."""
    before = (
        _invoke(ctx, "weights_digest", phase="verify")
        if "weights_digest" in ctx.adapter.operations
        else None
    )
    raw = _invoke(ctx, "native_forward", input_ids)
    captured = _invoke(ctx, "forward", input_ids)
    restored = _invoke(ctx, "readout", captured["hidden"], context=captured.get("context", {}))
    exact = bool(np.array_equal(raw, captured["logits"]))
    decoder_exact = bool(np.array_equal(raw, restored))
    after = _invoke(ctx, "weights_digest", phase="verify") if before is not None else None
    stable = before == after if before is not None else None
    return {
        "status": "TESTED" if exact and decoder_exact and stable is not False else "FAILED",
        "instrumentation_exact": exact,
        "readout_exact": decoder_exact,
        "weights_unchanged": stable,
        "instrumentation_max_abs_delta": float(
            np.max(np.abs(np.asarray(raw) - captured["logits"]))
        ),
        "readout_max_abs_delta": float(np.max(np.abs(np.asarray(raw) - restored))),
    }


def history_sweep(ctx, *, input_ids, anchors, conditions, targets=None):
    """Measure frozen fixed-suffix conditions on identical rows and anchor positions."""
    x = _array(input_ids, ndim=2, integer=True)
    anchors = _indices(anchors, x.shape[1], (len(x),))
    _require(
        type(conditions) is dict and conditions and len(conditions) <= 64,
        "bounded named history conditions required",
    )
    baseline = _invoke(ctx, "forward", x)
    row = np.arange(len(x))
    logits = baseline["logits"][row, anchors]
    hidden = baseline["hidden"][row, anchors]
    outputs = {}
    for name, spec in conditions.items():
        edit = suffix_intervention(x, anchors, **spec)
        observed = _invoke(ctx, "forward", edit["input_ids"])
        head = observed["hidden"][row, anchors]
        metrics = response_metrics(logits, observed["logits"][row, anchors], targets=targets)
        metrics.update(
            hidden_difference=head - hidden,
            hidden_relative_l2=np.linalg.norm(head - hidden, axis=-1)
            / np.maximum(np.linalg.norm(hidden, axis=-1), 1e-12),
            donor_indices=edit["donor_indices"],
            permutations=edit["permutations"],
        )
        outputs[name] = metrics
    return {
        "native_logits": logits,
        "native_hidden": hidden,
        "conditions": outputs,
        "uncertainty_scope": "CONDITIONAL_ON_FROZEN_DONORS_AND_SHUFFLES",
    }


def position_sweep(ctx, *, input_ids, conditions, targets=None):
    """Same-byte position tests; absent learned tables produce identity aliases."""
    x = _array(input_ids, ndim=2, integer=True)
    _require(
        type(conditions) is dict and conditions and len(conditions) <= 64,
        "bounded position condition map required",
    )
    baseline = _invoke(ctx, "forward", x)
    info = _invoke(ctx, "position_info", phase="verify")
    outputs = {}
    for name, ids in conditions.items():
        observed = _invoke(ctx, "position_forward", x, ids, native=baseline)
        outputs[name] = {
            "alias_of": observed.get("alias_of"),
            "measurement_type": observed["measurement_type"],
            "metrics": response_metrics(
                baseline["logits"][:, -1], observed["logits"][:, -1], targets=targets
            ),
        }
    return {
        "native_logits": baseline["logits"][:, -1],
        "position_capability": info,
        "conditions": outputs,
        "physical_attention_order_unchanged": True,
    }


def component_lesions(ctx, *, input_ids, conditions, mode="one_step", targets=None):
    """Replay native cached prestates or propagate an edited state through sequence."""
    x = _array(input_ids, ndim=2, integer=True)
    _require(
        mode in ("one_step", "persistent")
        and type(conditions) is dict
        and conditions
        and len(conditions) <= 32,
        "bounded component conditions and explicit mode required",
    )
    state = _invoke(ctx, "initial_state", len(x), phase="setup")
    saved, logits = [], []
    for token in x.T:
        saved.append(_invoke(ctx, "clone_state", state, phase="encode"))
        result = _invoke(ctx, "step", token, state)
        logits.append(result["logits"])
        state = result["state"]
    native = np.stack(logits, 1)
    outputs = {}
    for name, components in conditions.items():
        edit = None
        donor_indices = None
        if type(components) is dict:
            _require(
                set(components) <= {"components", "state_operation", "donor_indices"},
                "unknown component condition field",
            )
            edit = components.get("state_operation")
            donor_indices = components.get("donor_indices")
            components = components.get("components", ())
        state = _invoke(ctx, "clone_state", saved[0], phase="encode")
        values = []
        for t, token in enumerate(x.T):
            if mode == "one_step":
                state = _invoke(ctx, "clone_state", saved[t], phase="encode")
            if edit is not None:
                donor = (
                    None
                    if donor_indices is None
                    else _invoke(ctx, "select_state", saved[t], donor_indices, phase="encode")
                )
                state = _invoke(ctx, "edit_state", state, edit, donor=donor, phase="update")
            result = _invoke(ctx, "step", token, state, components=components)
            values.append(result["logits"])
            state = result["state"]
        values = np.stack(values, 1)
        outputs[name] = {
            "logits": values,
            "metrics": response_metrics(native, values, targets=targets),
        }
    return {
        "native_logits": native,
        "conditions": outputs,
        "state_mode": mode,
        "model_mutation_scope": "NO_OPTIMIZER_OR_PARAMETER_EDIT_IN_THIS_HELPER",
        "training_updates": 0,
    }


def state_interventions(
    ctx,
    *,
    state,
    tokens,
    donor_indices,
    targets=None,
    alternate_targets=None,
    operations=("identity", "persistent_reset", "paired_values", "paired_persistent"),
):
    """Frozen-anchor values/full-state swaps, reset and self-copy sham from cycle004."""
    x = _array(tokens, ndim=1, integer=True)
    donor_indices = _indices(donor_indices, len(x), (len(x),))
    _require(
        isinstance(operations, (tuple, list))
        and operations
        and len(set(operations)) == len(operations)
        and set(operations)
        <= {"identity", "persistent_reset", "paired_values", "paired_persistent"},
        "bounded supported frozen state interventions required",
    )
    native = _invoke(ctx, "step", x, _invoke(ctx, "clone_state", state, phase="encode"))
    donor = _invoke(ctx, "select_state", state, donor_indices, phase="encode")
    base_arrays = _invoke(ctx, "state_arrays", state, phase="encode")
    donor_arrays = _invoke(ctx, "state_arrays", donor, phase="encode")
    same_history = bool(np.array_equal(base_arrays["history"], donor_arrays["history"]))
    same_current = bool(np.array_equal(x, x[donor_indices]))
    outputs, checks = (
        {},
        {"paired_history_exact": same_history, "paired_current_token_exact": same_current},
    )
    for operation in operations:
        edited = _invoke(ctx, "edit_state", state, operation, donor=donor, phase="update")
        observed = _invoke(ctx, "step", x, edited)
        outputs[operation] = {
            "logits": observed["logits"],
            "metrics": response_metrics(
                native["logits"],
                observed["logits"],
                targets=targets,
                alternate_targets=alternate_targets,
            ),
        }
        if operation == "identity":
            checks["self_sham_exact"] = bool(np.array_equal(native["logits"], observed["logits"]))
        if operation == "paired_persistent" and same_history and same_current:
            checks["full_persistent_counterpart_exact"] = bool(
                np.array_equal(observed["logits"], native["logits"][donor_indices])
            )
    return {
        "status": "FAILED"
        if any(
            value is False
            for key, value in checks.items()
            if key.endswith("sham_exact") or key.endswith("counterpart_exact")
        )
        else "TESTED",
        "native_logits": native["logits"],
        "conditions": outputs,
        "checks": checks,
        "retained_state_difference": state_distances(base_arrays, donor_arrays),
        "counterpart_identity_applicable": same_history and same_current,
    }


def native_component_sweep(ctx, *, input_ids, conditions, targets=None):
    """Execute declared native COG bank/successor controls through their source path."""
    _require(
        isinstance(conditions, (tuple, list))
        and conditions
        and len(set(conditions)) == len(conditions),
        "unique native condition names required",
    )
    native = _invoke(ctx, "native_forward", input_ids)
    outputs = {}
    for name in conditions:
        logits = _invoke(ctx, "forward_condition", input_ids, name)
        outputs[name] = {
            "logits": logits,
            "metrics": response_metrics(native, logits, targets=targets),
        }
    return {
        "native_logits": native,
        "conditions": outputs,
        "scope": "FROZEN_NATIVE_COMPONENT_PATH; FOREIGN_BANKS_CAN_BE_OUT_OF_DISTRIBUTION",
    }


def _trajectory(ctx, state, inputs):
    logits, heads, traces = [], [], {k: [] for k in READ_NAMES}
    for token in inputs.T:
        result = _invoke(ctx, "step", token, state)
        logits.append(result["logits"])
        heads.append(result["hidden"])
        for key in READ_NAMES:
            traces[key].append(result["trace"][key])
        state = result["state"]
    return {
        "logits": np.stack(logits, 1),
        "hidden": np.stack(heads, 1),
        "trace": {k: np.stack(v, 1) for k, v in traces.items()},
        "final_state": state,
    }


def unread_future(
    ctx,
    *,
    state,
    donor_state,
    input_ids,
    operation="transplant_unread",
    targets=None,
    trained_horizon=None,
    kl_threshold=1e-8,
):
    """Run same-index unread edits and shams from frozen native states, then trace access."""
    _require(
        operation in ("transplant_unread", "zero_unread"), "value-only unread operation required"
    )
    x = _array(input_ids, ndim=2, integer=True)
    base = _invoke(ctx, "state_arrays", state, phase="encode")
    probe_state = _invoke(ctx, "clone_state", state, phase="encode")
    probe = _invoke(ctx, "step", x[:, 0], probe_state)
    eligible = ~read_footprint(probe["trace"], base["values"].shape[1])
    edited = _invoke(
        ctx, "edit_state", state, operation, donor=donor_state, eligible=eligible, phase="update"
    )
    sham = _invoke(
        ctx,
        "edit_state",
        state,
        "transplant_unread",
        donor=state,
        eligible=eligible,
        phase="update",
    )
    edited_arrays = _invoke(ctx, "state_arrays", edited, phase="encode")
    changed = np.any(base["values"] != edited_arrays["values"], axis=-1)
    _require(not np.any(changed & ~eligible), "an edit touched a current read row")
    for name in ("links", "cursor", "history", "position"):
        _require(
            np.array_equal(base[name], edited_arrays[name]),
            "value-only edit changed another state field",
        )
    native = _trajectory(ctx, _invoke(ctx, "clone_state", state, phase="encode"), x)
    branch = _trajectory(ctx, edited, x)
    sham_result = _trajectory(ctx, sham, x)
    sham_exact = bool(np.array_equal(native["logits"], sham_result["logits"]))
    sham_states = state_distances(
        _invoke(ctx, "state_arrays", native["final_state"], phase="encode"),
        _invoke(ctx, "state_arrays", sham_result["final_state"], phase="encode"),
    )["exact"]
    analysis = analyze_future_access(
        native["logits"],
        branch["logits"],
        native["trace"],
        branch["trace"],
        changed,
        kl_threshold=kl_threshold,
        targets=targets,
        trained_horizon=trained_horizon,
        start_position=int(base["position"]),
    )
    if not sham_exact or not sham_states:
        analysis["status"] = "FAILED"
    analysis.update(
        sham_logits_exact=sham_exact,
        sham_final_state_exact=sham_states,
        eligible_rows=eligible,
        actually_changed_rows=changed,
        native_logits=native["logits"],
        edited_logits=branch["logits"],
        state_retention=state_distances(base, edited_arrays),
    )
    return analysis


def retrieval_sweep(
    ctx,
    *,
    input_ids,
    anchor,
    donor_indices=None,
    donor_input_ids=None,
    horizon=None,
    operations=("transplant_unread", "zero_unread"),
    frozen_state_operations=("identity", "persistent_reset", "paired_values", "paired_persistent"),
    targets=None,
    alternate_targets=None,
    trained_horizon=None,
    kl_threshold=1e-8,
):
    """Array-only entrypoint: reconstruct native prestates, edit, and replay inputs.

    ``anchor`` is the index of the first intervened prediction; exactly ``anchor``
    input tokens have been consumed into state. The continuation is always the
    recipient input array. Explicit donor prefixes can differ while preserving
    the final local suffix; this fact is measured, never assumed.
    """
    x = _array(input_ids, ndim=2, integer=True)
    _require(type(anchor) is int and 0 <= anchor < x.shape[1], "valid intervention anchor required")
    horizon = x.shape[1] - anchor if horizon is None else horizon
    _require(
        type(horizon) is int and 0 < horizon <= x.shape[1] - anchor,
        "future horizon exceeds supplied true continuation",
    )
    _require(
        (donor_indices is None) != (donor_input_ids is None),
        "supply one frozen donor map or explicit donor inputs",
    )
    _require(
        isinstance(operations, (tuple, list))
        and len(set(operations)) == len(operations)
        and set(operations) <= {"transplant_unread", "zero_unread"},
        "supported unread operations required",
    )
    _require(
        isinstance(frozen_state_operations, (tuple, list))
        and len(set(frozen_state_operations)) == len(frozen_state_operations)
        and set(frozen_state_operations)
        <= {"identity", "persistent_reset", "paired_values", "paired_persistent"},
        "supported frozen state conditions required",
    )
    _require(operations or frozen_state_operations, "at least one retrieval condition required")
    state = _invoke(ctx, "initial_state", len(x), phase="setup")
    for token in x[:, :anchor].T:
        state = _invoke(ctx, "step", token, state)["state"]
    if donor_input_ids is not None:
        donor_x = _array(donor_input_ids, ndim=2, integer=True)
        _require(donor_x.shape == x.shape, "donor and recipient sequence shapes differ")
        donor = _invoke(ctx, "initial_state", len(x), phase="setup")
        for token in donor_x[:, :anchor].T:
            donor = _invoke(ctx, "step", token, donor)["state"]
    else:
        donor_indices = _indices(donor_indices, len(x), (len(x),))
        donor_x = x[donor_indices]
        donor = _invoke(ctx, "select_state", state, donor_indices, phase="encode")
    base_arrays = _invoke(ctx, "state_arrays", state, phase="encode")
    donor_arrays = _invoke(ctx, "state_arrays", donor, phase="encode")
    target_array = None if targets is None else _array(targets, ndim=2, integer=True)
    _require(
        target_array is None or target_array.shape == x.shape,
        "target rows must align with every supplied input",
    )
    future_targets = None if target_array is None else target_array[:, anchor : anchor + horizon]
    outputs = {}
    for operation in operations:
        outputs[operation] = unread_future(
            ctx,
            state=state,
            donor_state=donor,
            input_ids=x[:, anchor : anchor + horizon],
            operation=operation,
            targets=future_targets,
            trained_horizon=trained_horizon,
            kl_threshold=kl_threshold,
        )
    frozen = {}
    if frozen_state_operations:
        native = _invoke(
            ctx, "step", x[:, anchor], _invoke(ctx, "clone_state", state, phase="encode")
        )
        for operation in frozen_state_operations:
            edited = _invoke(ctx, "edit_state", state, operation, donor=donor, phase="update")
            observed = _invoke(ctx, "step", x[:, anchor], edited)
            frozen[operation] = {
                "logits": observed["logits"],
                "metrics": response_metrics(
                    native["logits"],
                    observed["logits"],
                    targets=None if target_array is None else target_array[:, anchor],
                    alternate_targets=alternate_targets,
                ),
            }
        checks = {
            "self_sham_exact": bool(np.array_equal(native["logits"], frozen["identity"]["logits"]))
            if "identity" in frozen
            else None
        }
        if "paired_persistent" in frozen and np.array_equal(
            base_arrays["history"], donor_arrays["history"]
        ):
            counterpart = _invoke(
                ctx, "step", x[:, anchor], _invoke(ctx, "clone_state", donor, phase="encode")
            )
            checks["full_persistent_counterpart_exact"] = bool(
                np.array_equal(counterpart["logits"], frozen["paired_persistent"]["logits"])
            )
    else:
        checks = {}
    failed = any(value is False for value in checks.values()) or any(
        value["status"] == "FAILED" for value in outputs.values()
    )
    return {
        "status": "FAILED" if failed else "TESTED",
        "anchor": anchor,
        "horizon": horizon,
        "unread_conditions": outputs,
        "frozen_state_conditions": frozen,
        "checks": checks,
        "state_retention": state_distances(base_arrays, donor_arrays),
        "local_history_exact": bool(
            np.array_equal(base_arrays["history"], donor_arrays["history"])
        ),
        "current_token_exact": bool(np.array_equal(x[:, anchor], donor_x[:, anchor])),
        "shared_true_continuation": True,
        "training_updates": 0,
    }


def latency_sweep(ctx, *, input_ids, warmups=2, repeats=5, require_exact=True, quality_gate=None):
    """Warm native forward latency with repeat parity and separately declared quality.

    The timed adapter operation owns synchronization and the timing boundary. The
    Workbench still measures the full session, including all warmup/failed calls,
    checksum work and ledger writes. These intervals must never be substituted.
    """
    _array(input_ids, ndim=2, integer=True)
    _require(
        type(warmups) is int
        and 0 <= warmups <= 100
        and type(repeats) is int
        and 2 <= repeats <= 1000
        and type(require_exact) is bool,
        "bounded warmups/repeats and explicit parity requirement needed",
    )
    _require(
        quality_gate is None or type(quality_gate) is bool,
        "quality gate must be an explicit separately evaluated boolean",
    )
    before = _invoke(ctx, "weights_digest", phase="verify")
    reference = _invoke(ctx, "native_forward", input_ids)
    for _ in range(warmups):
        _invoke(ctx, "timed_native_forward", input_ids)
    rows, exact = [], True
    for _ in range(repeats):
        item = _invoke(ctx, "timed_native_forward", input_ids, condition="warm")
        _require(
            type(item) is dict
            and type(item.get("seconds")) in (int, float)
            and np.isfinite(item["seconds"])
            and item["seconds"] >= 0,
            "finite measured native duration required",
        )
        exact &= bool(np.array_equal(reference, item["logits"]))
        rows.append({key: value for key, value in item.items() if key != "logits"})
    after = _invoke(ctx, "weights_digest", phase="verify")
    seconds = np.array([row["seconds"] for row in rows], dtype=float)
    q1, median, q3 = np.quantile(seconds, [0.25, 0.5, 0.75])
    _require(
        all(
            row.get("scope") == rows[0].get("scope")
            and row.get("device") == rows[0].get("device")
            and row.get("device_completion") == rows[0].get("device_completion")
            for row in rows
        ),
        "timing repetitions do not share a measurement boundary",
    )
    valid = before == after and (exact or not require_exact)
    return {
        "status": "TESTED" if valid else "FAILED",
        "seconds": seconds,
        "median_seconds": float(median),
        "q1_seconds": float(q1),
        "q3_seconds": float(q3),
        "iqr_seconds": float(q3 - q1),
        "warmups": warmups,
        "repeats": repeats,
        "repeat_logits_exact": exact,
        "weights_unchanged": before == after,
        "quality_gate": "UNASSESSED"
        if quality_gate is None
        else "PASS"
        if quality_gate
        else "FAIL",
        "quality_cost_eligible": bool(valid and quality_gate is True),
        "observations": rows,
        "measurement_scope": rows[0].get("scope"),
        "excludes": [
            "model_load",
            "input_preparation",
            "output_export",
            "ledger_io",
            "weights_hashing",
        ],
        "unmeasured": ["memory_peak", "energy", "money"],
        "uncertainty_scope": "DESCRIPTIVE_REPEATED_TIMING_ON_ONE_RUNTIME_AND_WORKLOAD",
    }
