"""Explicit trusted PyTorch hooks for latent diagnostics; never load model code.

Factories receive existing model objects. The small language-model conveniences
target the inspected source interfaces from the latent studies, not every model
with the same architecture label. Other backends supply their own Adapter.
"""

from __future__ import annotations

import hashlib
from dataclasses import fields, is_dataclass
from time import perf_counter_ns

import numpy as np

from ..research_diagnostics import Adapter
from .interventions import _array, _indices, _require, read_footprint


def _numpy(value):
    if hasattr(value, "detach"):
        detached = value.detach().cpu()
        # NumPy lacks native bfloat16. Its values are exactly representable in
        # float32; keep the model arithmetic/dtype unchanged and widen on export.
        if str(detached.dtype) == "torch.bfloat16":
            detached = detached.float()
        value = detached.numpy()
    result = np.asarray(value)
    _require(
        result.dtype.kind in "biuf" and np.isfinite(result).all(),
        "native hook returned nonfinite or nonnumeric data",
    )
    return result.copy()


def _clone(value):
    if hasattr(value, "detach"):
        return value.detach().clone()
    if isinstance(value, np.ndarray):
        return value.copy()
    if is_dataclass(value) and not isinstance(value, type):
        return type(value)(
            **{field.name: _clone(getattr(value, field.name)) for field in fields(value)}
        )
    if isinstance(value, tuple):
        return (
            type(value)(*(_clone(v) for v in value))
            if hasattr(value, "_fields")
            else tuple(_clone(v) for v in value)
        )
    if isinstance(value, list):
        return [_clone(v) for v in value]
    if isinstance(value, dict):
        return {key: _clone(item) for key, item in value.items()}
    _require(
        value is None or type(value) in (str, bool, int, float),
        "state needs an explicit clone callback",
    )
    return value


def _tensor_inputs(model, value, *, ndim=2):
    import torch

    a = _array(value, ndim=ndim, integer=True)
    _require(a.size <= 2**20 and np.all(a >= 0), "bounded nonnegative token IDs required")
    _require(not model.training, "diagnostic model must already be in evaluation mode")
    return torch.as_tensor(a.copy(), dtype=torch.long, device=next(model.parameters()).device)


def _digest(model):
    import torch

    h = hashlib.sha256()
    for name, value in sorted(model.state_dict().items()):
        h.update(name.encode())
        h.update(str(value.dtype).encode())
        h.update(str(tuple(value.shape)).encode())
        h.update(value.detach().cpu().contiguous().reshape(-1).view(torch.uint8).numpy().tobytes())
    return h.hexdigest()


def _input_digest(input_ids):
    a = np.ascontiguousarray(_array(input_ids, ndim=2, integer=True), dtype=np.int64)
    h = hashlib.sha256(str(a.shape).encode())
    h.update(a.tobytes())
    return h.hexdigest()


def _timed_forward(model, input_ids, forward, select):
    import torch

    x = _tensor_inputs(model, input_ids)
    device = next(model.parameters()).device
    _require(
        device.type in ("cpu", "cuda"), "timed backend needs an explicit completion synchronizer"
    )
    synchronize = (
        (lambda: torch.cuda.synchronize(device)) if device.type == "cuda" else (lambda: None)
    )
    synchronize()
    with torch.inference_mode():
        started = perf_counter_ns()
        result = select(forward(x))
        synchronize()
        elapsed = (perf_counter_ns() - started) / 1_000_000_000
    logits = _numpy(result)
    _require(
        logits.ndim == 3 and logits.shape[:2] == tuple(x.shape),
        "timed native token logits shape changed",
    )
    return {
        "seconds": elapsed,
        "logits": logits,
        "device": str(device),
        "clock": "perf_counter_ns",
        "device_completion": "CUDA_SYNCHRONIZED"
        if device.type == "cuda"
        else "DECLARED_CPU_SYNCHRONOUS",
        "scope": "NATIVE_FORWARD_AFTER_INPUT_PREPARATION_BEFORE_OUTPUT_EXPORT_EXCLUDING_LEDGER_IO",
    }


def _join_capture(items, shape):
    import torch

    _require(items, "native forward did not invoke the declared capture module")
    value = torch.stack(items, 1) if items[0].ndim == 2 else torch.cat(items, 1)
    _require(value.shape[:2] == shape, "captured representations do not align with tokens")
    return _numpy(value)


def module_adapter(
    model,
    *,
    name,
    head,
    embedding=None,
    position_embedding=None,
    position_absent=False,
    select_logits=None,
    decode=None,
    views=None,
    forward_fn=None,
):
    """Hook an explicitly named readout; custom decode preserves nonlinear heads.

    ``head`` is the module whose input is the representation. ``decode`` receives
    a torch tensor and must reproduce all later bias/normalization/softcap/mixing
    semantics. If omitted, the declared head is the entire readout. No graph or
    architecture inference is attempted. Extra views map names to actual modules
    whose outputs are tensors. Models must already be in eval mode.
    """
    import torch

    _require(
        isinstance(model, torch.nn.Module)
        and isinstance(head, torch.nn.Module)
        and not model.training,
        "existing eval model and explicit readout module required",
    )
    _require(select_logits is None or callable(select_logits), "output selector must be callable")
    _require(decode is None or callable(decode), "native decoder must be callable")
    _require(forward_fn is None or callable(forward_fn), "native forward must be callable")
    _require(
        type(position_absent) is bool and not (position_absent and position_embedding is not None),
        "position capability must be unambiguous",
    )
    raw_views = {} if views is None else dict(views)
    views = {}
    for key, specification in raw_views.items():
        specification = (
            {"module": specification, "capture": "output"}
            if isinstance(specification, torch.nn.Module)
            else specification
        )
        _require(
            type(key) is str
            and type(specification) is dict
            and set(specification) <= {"module", "capture", "select"}
            and isinstance(specification.get("module"), torch.nn.Module)
            and specification.get("capture", "output") in ("input", "output")
            and (specification.get("select") is None or callable(specification["select"])),
            "named modules with explicit input/output capture required",
        )
        views[key] = specification
    select = select_logits or (lambda output: output)
    call_forward = forward_fn or model

    def native_forward(input_ids):
        x = _tensor_inputs(model, input_ids)
        with torch.inference_mode():
            result = _numpy(select(call_forward(x)))
        _require(
            result.ndim == 3 and result.shape[:2] == tuple(x.shape),
            "native token logits shape changed",
        )
        return result

    def forward(input_ids):
        x = _tensor_inputs(model, input_ids)
        captured = {"hidden": []}
        handles = [
            head.register_forward_pre_hook(
                lambda module, args: captured["hidden"].append(args[0].detach().clone())
            )
        ]
        restored = []
        for key, specification in views.items():
            module = specification["module"]
            captured[key] = []
            # TransformerEncoderLayer inspects registered hooks to decide whether
            # to use its fused evaluation kernel. A stage hook changes that path.
            # Wrapping the callable preserves native dispatch and is restored even
            # on failure; this adapter is trusted, synchronous and single-threaded.
            had_instance_forward = "forward" in module.__dict__
            saved = module.__dict__.get("forward")
            original = module.forward

            def capture(*args, _forward=original, _key=key, _spec=specification, **kwargs):
                selected = args[0] if _spec.get("capture", "output") == "input" else None
                output = _forward(*args, **kwargs)
                if _spec.get("capture", "output") == "output":
                    selected = output
                if _spec.get("select") is not None:
                    selected = _spec["select"](selected)
                _require(
                    isinstance(selected, torch.Tensor), "capture needs an explicit tensor selector"
                )
                captured[_key].append(selected.detach().clone())
                return output

            restored.append((module, had_instance_forward, saved))
            module.forward = capture
        try:
            with torch.inference_mode():
                logits = _numpy(select(call_forward(x)))
        finally:
            for handle in handles:
                handle.remove()
            for module, had_instance_forward, saved in reversed(restored):
                if had_instance_forward:
                    module.forward = saved
                else:
                    del module.forward
        _require(
            logits.ndim == 3 and logits.shape[:2] == tuple(x.shape),
            "native token logits shape changed",
        )
        hidden = _join_capture(captured.pop("hidden"), tuple(x.shape))
        outputs = {}
        for key, items in captured.items():
            if len(items) > 1 and all(
                item.ndim >= 3 and item.shape[:2] == tuple(x.shape) for item in items
            ):
                # Reused decoder modules are distinct execution stages, never
                # concatenate them onto the token axis or silently retain last.
                outputs.update(
                    {f"{key}_call_{i + 1:02d}": _numpy(item) for i, item in enumerate(items)}
                )
            else:
                outputs[key] = _join_capture(items, tuple(x.shape))
        return {
            "logits": logits,
            "hidden": hidden,
            "views": outputs,
            "context": {},
            "readout_kind": "logits",
            "input_sha256": _input_digest(input_ids),
        }

    def readout(hidden, *, row_indices=None, context=None, **kwargs):
        _require(
            not model.training and not kwargs, "unsupported decoder intervention or training mode"
        )
        a = _array(hidden)
        parameter = next(head.parameters(), next(model.parameters()))
        h = torch.as_tensor(a.copy(), device=parameter.device, dtype=parameter.dtype)
        with torch.inference_mode():
            return _numpy((decode or head)(h))

    def position_info():
        return {
            "kind": "learned_table" if position_embedding is not None else "absent",
            "table_size": int(position_embedding.num_embeddings)
            if position_embedding is not None
            else None,
            "scope": "DECLARED_NATIVE_LOOKUP_ONLY",
        }

    def position_forward(input_ids, ids, *, native=None):
        x = _tensor_inputs(model, input_ids)
        lookup = _array(ids, ndim=1, integer=True)
        _require(
            lookup.shape == (x.shape[1],) and np.all(lookup >= 0),
            "one position ID per physical token required",
        )
        if position_embedding is None:
            _require(position_absent, "learned position capability is unknown")
            _require(
                native is None
                or (
                    type(native) is dict and native.get("input_sha256") == _input_digest(input_ids)
                ),
                "identity alias requires the matching native input capture",
            )
            result = forward(input_ids) if native is None else _clone(native)
            result.update(alias_of="native", measurement_type="IDENTITY_ALIAS_NO_POSITION_TABLE")
            return result
        _require(
            int(lookup.max()) < position_embedding.num_embeddings, "position lookup out of range"
        )
        replacement = torch.as_tensor(lookup.copy(), device=x.device, dtype=torch.long)
        invoked = []

        def replace(module, args):
            expected = torch.arange(x.shape[1], device=x.device)
            _require(
                len(args) == 1 and torch.equal(args[0], expected),
                "unexpected native position lookup; refusing semantic substitution",
            )
            invoked.append(True)
            return (replacement,)

        handle = position_embedding.register_forward_pre_hook(replace)
        try:
            result = forward(input_ids)
        finally:
            handle.remove()
        _require(len(invoked) == 1, "position lookup must execute exactly once")
        result.update(alias_of=None, measurement_type="LEARNED_POSITION_LOOKUP_INTERVENTION")
        return result

    operations = {
        "native_forward": native_forward,
        "forward": forward,
        "readout": readout,
        "weights_digest": lambda: _digest(model),
        "timed_native_forward": lambda input_ids: _timed_forward(
            model, input_ids, call_forward, select
        ),
    }
    if embedding is not None:
        operations["embedding"] = lambda: _numpy(
            embedding()
            if callable(embedding) and not isinstance(embedding, torch.nn.Module)
            else embedding.weight
        )
    if position_embedding is not None or position_absent:
        operations.update(position_info=position_info, position_forward=position_forward)
    return Adapter(
        name,
        operations,
        {
            "persists": "fresh native sequence state on each forward",
            "query_mutates": False,
            "reset": "native forward initialization",
        },
    )


def torch_hook_adapter(
    model, *, forward, head, embedding, readout, stages=None, name="torch-hooks"
):
    """Explicit module adapter for other inspected model sources, including legacy7.

    The forward callback returns token logits. The readout callback takes the
    captured tensor and owns the exact vocabulary slice, bias and nonlinearities;
    for example a soft-capped model must include its native tanh in this callback.
    Call native_parity through Workbench before trusting extracted representations.
    """
    _require(
        callable(forward) and callable(readout),
        "explicit native forward and readout callbacks required",
    )
    return module_adapter(
        model,
        name=name,
        head=head,
        embedding=embedding,
        decode=readout,
        views=stages,
        forward_fn=forward,
    )


def _csm_adapter(model, name):
    import torch

    for key in (
        "config",
        "embedding",
        "frontend",
        "controller",
        "transform",
        "output",
        "init_state",
        "step",
    ):
        _require(hasattr(model, key), "CSM source interface is incomplete")
    base = module_adapter(
        model, name=name, head=model.output, embedding=model.embedding, position_absent=True
    )
    operations = dict(base.operations)
    width = model.config.width

    def initial_state(batch):
        _require(type(batch) is int and 0 < batch <= 65536, "bounded native batch required")
        with torch.inference_mode():
            return model.init_state(batch, next(model.parameters()).device)

    def state_arrays(state):
        return {
            key: _numpy(getattr(state, key))
            for key in ("values", "links", "cursor", "history", "position")
        }

    def select_state(state, indices):
        ix = _indices(indices, len(state.values), (len(state.values),))
        ix = torch.as_tensor(ix.copy(), device=state.values.device, dtype=torch.long)
        result = _clone(state)
        for key in ("values", "links", "cursor", "history"):
            setattr(result, key, getattr(state, key)[ix].clone())
        return result

    def edit_state(state, operation, *, donor=None, eligible=None):
        result = _clone(state)
        if operation in ("transplant_unread", "zero_unread"):
            mask = _array(eligible, ndim=2)
            _require(
                mask.dtype.kind == "b" and tuple(mask.shape) == tuple(state.values.shape[:2]),
                "boolean eligible-row mask required",
            )
            mask = torch.as_tensor(mask.copy(), device=state.values.device)
            if operation == "transplant_unread":
                _require(
                    donor is not None and donor.values.shape == state.values.shape,
                    "aligned donor values required",
                )
                result.values[mask] = donor.values[mask].clone()
            else:
                result.values[mask] = 0
        elif operation in ("paired_values", "paired_persistent", "foreign_record_memory"):
            _require(
                donor is not None and donor.position == state.position,
                "same-position donor state required",
            )
            names = ("values",) if operation == "paired_values" else ("values", "links", "cursor")
            for key in names:
                _require(
                    getattr(donor, key).shape == getattr(state, key).shape,
                    "donor state shape differs",
                )
                setattr(result, key, _clone(getattr(donor, key)))
        elif operation == "persistent_reset":
            fresh = initial_state(len(state.values))
            result.values, result.links, result.cursor = fresh.values, fresh.links, fresh.cursor
        elif operation == "prior_values_zero":
            result.values.zero_()
        elif operation == "history_zero":
            result.history.zero_()
        else:
            _require(operation == "identity", "unsupported state intervention")
        return result

    def step(tokens, state, *, components=()):
        x = _tensor_inputs(model, tokens, ndim=1)
        _require(len(x) == len(state.values), "token and state batches differ")
        _require(
            isinstance(components, (tuple, list)) and len(set(components)) == len(components),
            "unique component lesion list required",
        )
        names = set(components)
        allowed = {
            "controller_active_zero",
            "proposal_values_zero",
            "controller_and_proposal_zero",
            "prior_values_zero",
            "history_zero",
            "links_off",
            "constant_operator",
        }
        _require(names <= allowed, "unsupported component lesion")
        working = _clone(state)
        for key in ("prior_values_zero", "history_zero"):
            if key in names:
                working = edit_state(working, key)
        handles, captured = [], {}

        def zero_control(module, args):
            value = args[0].clone()
            _require(value.shape[-1] == 2 * width, "controller input semantics changed")
            value[..., width:] = 0
            return (value,)

        def zero_proposal(module, args):
            value = args[0].clone()
            _require(value.shape[-1] == 4 * width, "proposal input semantics changed")
            value[..., width : 3 * width] = 0
            return (value,)

        if names & {"controller_active_zero", "controller_and_proposal_zero"}:
            handles.append(model.controller.register_forward_pre_hook(zero_control))
        if names & {"proposal_values_zero", "controller_and_proposal_zero"}:
            handles.append(model.transform.register_forward_pre_hook(zero_proposal))
        handles.extend(
            [
                model.output.register_forward_pre_hook(
                    lambda module, args: captured.update(hidden=args[0].detach().clone())
                ),
                model.frontend.register_forward_pre_hook(
                    lambda module, args: captured.update(frontend=args[0].detach().clone())
                ),
                model.controller.register_forward_hook(
                    lambda module, args, output: captured.update(controller=output.detach().tanh())
                ),
            ]
        )
        try:
            with torch.inference_mode():
                logits, following, trace = model.step(
                    x,
                    working,
                    interventions={key: True for key in names & {"links_off", "constant_operator"}},
                    return_trace=True,
                )
        finally:
            for handle in handles:
                handle.remove()
        trace = {key: _numpy(value) for key, value in trace.items()}
        trace["cursor"] = _numpy(working.cursor.argmax(-1))
        read_footprint(trace, model.config.slots)
        return {
            "logits": _numpy(logits),
            "state": _clone(following),
            "hidden": _numpy(captured["hidden"]),
            "trace": trace,
            "views": {key: _numpy(value) for key, value in captured.items() if key != "hidden"},
        }

    def forward(input_ids):
        x = _array(input_ids, ndim=2, integer=True)
        _require(x.size <= 2**20, "bounded native token panel required")
        state = initial_state(len(x))
        logits, hidden, views = (
            [],
            [],
            {key: [] for key in ("frontend", "controller", "memory", "full_state")},
        )
        trace = {}
        for token in x.T:
            result = step(token, state)
            state = result["state"]
            logits.append(result["logits"])
            hidden.append(result["hidden"])
            for key, value in result["views"].items():
                views[key].append(value)
            arrays = state_arrays(state)
            views["memory"].append(arrays["values"].reshape(len(x), -1))
            tensors = [
                arrays[key].reshape(len(x), -1) for key in ("values", "links", "cursor", "history")
            ]
            # Absolute position can affect a ring-write source. Include its exact
            # bounded integer value rather than label tensor-only state complete.
            tensors.append(np.full((len(x), 1), state.position, dtype=np.float64))
            views["full_state"].append(np.concatenate(tensors, -1))
            for key, value in result["trace"].items():
                trace.setdefault(key, []).append(value)
        return {
            "logits": np.stack(logits, 1),
            "hidden": np.stack(hidden, 1),
            "views": {key: np.stack(values, 1) for key, values in views.items()},
            "trace": {key: np.stack(values, 1) for key, values in trace.items()},
            "context": {},
            "readout_kind": "logits",
            "input_sha256": _input_digest(input_ids),
        }

    native_readout = operations["readout"]

    def readout(hidden, **kwargs):
        # Native CSM invokes its affine head once per time step. Preserve that
        # batching for strict identity; flattened fitting callers declare theirs.
        a = _array(hidden)
        if a.ndim == 3:
            return np.stack([native_readout(a[:, t], **kwargs) for t in range(a.shape[1])], 1)
        return native_readout(hidden, **kwargs)

    operations.update(
        forward=forward,
        readout=readout,
        initial_state=initial_state,
        clone_state=_clone,
        state_arrays=state_arrays,
        step=step,
        select_state=select_state,
        edit_state=edit_state,
        read_footprint=lambda trace: read_footprint(trace, model.config.slots),
    )
    return Adapter(
        name,
        operations,
        {
            "persists": "explicit native values, links, cursor and two-token history",
            "query_mutates": False,
            "reset": "init_state; edits preserve history and position unless named",
        },
    )


def _cog_adapter(model, name, successor_ids, mix):
    import torch
    from torch.nn import functional as F

    _require(
        callable(successor_ids) and callable(mix),
        "explicit native successor and mixture callbacks required",
    )
    for key in ("c", "emb", "norm", "bank", "gate"):
        _require(hasattr(model, key), "COG source interface incomplete")
    _require(model.c.arm == "cog" and not model.training, "native COG eval object required")

    def native_forward(input_ids):
        x = _tensor_inputs(model, input_ids)
        with torch.inference_mode():
            return _numpy(model(x)[0])

    def readout(
        hidden,
        *,
        row_indices=None,
        context=None,
        gate_mode="adaptive",
        gate_hidden=None,
        no_mixture=False,
    ):
        _require(
            not model.training and gate_mode in ("adaptive", "native") and type(no_mixture) is bool,
            "explicit native/adaptive gate and mixture mode required",
        )
        a = _array(hidden)
        h = torch.as_tensor(a.copy(), device=model.emb.weight.device, dtype=model.emb.weight.dtype)
        with torch.inference_mode():
            head = F.log_softmax(F.linear(h, model.emb.weight), -1)
            if no_mixture:
                return _numpy(head)
            _require(
                type(context) is dict and "successor_ids" in context,
                "native successor context required",
            )

            def select(key):
                value = _array(context[key])
                if row_indices is not None:
                    rows = _indices(row_indices, value.size, (len(a),))
                    value = value.reshape(-1)[rows]
                _require(
                    value.shape == tuple(h.shape[:-1]), "decoder context and hidden rows differ"
                )
                return value

            ids = select("successor_ids")
            _require(
                ids.dtype.kind in "iu" and np.all(ids >= -1) and np.all(ids < model.c.vocab),
                "invalid successor IDs",
            )
            ids = torch.as_tensor(ids.copy(), device=h.device, dtype=torch.long)
            if gate_mode == "native":
                _require(
                    "native_gate_logits" in context and gate_hidden is None,
                    "fixed gate needs frozen native gate logits and no alternate gate input",
                )
                gate = torch.as_tensor(
                    select("native_gate_logits").copy(), device=h.device, dtype=h.dtype
                )
            else:
                source = (
                    h
                    if gate_hidden is None
                    else torch.as_tensor(_array(gate_hidden).copy(), device=h.device, dtype=h.dtype)
                )
                _require(source.shape == h.shape, "head and gate input shapes differ")
                gate = model.gate(source).squeeze(-1)
            return _numpy(mix(head, ids, gate))

    def forward(input_ids):
        x = _tensor_inputs(model, input_ids)
        captured = {}
        handles = [
            model.norm.register_forward_hook(
                lambda module, args, output: captured.update(prebank=output.detach().clone())
            ),
            model.bank.register_forward_hook(
                lambda module, args, output: captured.update(bank_read=output[0].detach().clone())
            ),
        ]
        try:
            with torch.inference_mode():
                logits, _ = model(x)
                h = captured["prebank"] + captured["bank_read"]
                keys = successor_ids(x, model.c.capacity)
                gate = model.gate(h).squeeze(-1)
        finally:
            for handle in handles:
                handle.remove()
        return {
            "logits": _numpy(logits),
            "hidden": _numpy(h),
            "views": {key: _numpy(value) for key, value in captured.items()},
            "context": {"successor_ids": _numpy(keys), "native_gate_logits": _numpy(gate)},
            "readout_kind": "log_probabilities",
            "input_sha256": _input_digest(input_ids),
        }

    def forward_condition(input_ids, intervention):
        _require(
            intervention in ("full", "no_slots", "foreign_slots", "no_episode", "no_memory"),
            "unsupported native COG intervention",
        )
        x = _tensor_inputs(model, input_ids)
        _require(
            intervention != "foreign_slots" or len(x) > 1,
            "foreign-bank condition needs distinct paired rows",
        )
        with torch.inference_mode():
            return _numpy(model(x, intervention=intervention)[0])

    return Adapter(
        name,
        {
            "native_forward": native_forward,
            "forward": forward,
            "readout": readout,
            "forward_condition": forward_condition,
            "embedding": lambda: _numpy(model.emb.weight),
            "weights_digest": lambda: _digest(model),
            "timed_native_forward": lambda input_ids: _timed_forward(
                model, input_ids, model, lambda output: output[0]
            ),
        },
        {
            "persists": "native sequence cache, bank and successor table inside each fresh forward",
            "query_mutates": False,
            "reset": "native state=None",
        },
    )


def language_adapter(model, architecture, *, name=None, successor_ids=None, mix=None):
    """Adapt an already loaded source-compatible model; names do not attest parity."""
    name = architecture if name is None else name
    if architecture == "csm":
        return _csm_adapter(model, name)
    if architecture == "cog":
        return _cog_adapter(model, name, successor_ids, mix)
    _require(
        architecture in ("transformer", "gated_delta_reference"),
        "unsupported source interface; supply an explicit module_adapter",
    )
    _require(
        all(hasattr(model, key) for key in ("out", "emb")),
        "language source readout interface missing",
    )
    if architecture == "transformer":
        _require(
            hasattr(model, "pos") and hasattr(model, "layers"),
            "learned-position transformer source interface missing",
        )
        return module_adapter(
            model,
            name=name,
            head=model.out,
            embedding=model.emb,
            position_embedding=model.pos,
            views={f"layer_{i + 1:02d}": layer for i, layer in enumerate(model.layers)},
        )
    return module_adapter(
        model, name=name, head=model.out, embedding=model.emb, position_absent=True
    )
