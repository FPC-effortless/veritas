"""Explicit trusted-source factory for the latent suite's native opt-in mode.

Copy this file beside a plan, list the source files/checkpoint as opaque artifacts,
and declare adapter.factory = "build_adapter". See latent-native.md. No source or
checkpoint from a research study is distributed with this example.
"""

from __future__ import annotations

import hashlib
import importlib.util
import io
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import ModuleType

from trainlab.latent.native import language_adapter
from trainlab.runner import LabError, contained_file


def _require(condition, message):
    if not condition:
        raise LabError(message)


def _pinned_bytes(plan, source, key, maximum):
    item = plan["artifacts"].get(key)
    _require(
        type(item) is dict and item.get("kind") == "opaque",
        "native input must name an opaque artifact",
    )
    path = contained_file(source, item["path"])
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    _require(
        len(payload) <= maximum and hashlib.sha256(payload).hexdigest() == item["sha256"],
        "native input size or hash mismatch",
    )
    return payload


def _module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    _require(spec is not None and spec.loader is not None, "cannot load pinned native module")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def build_adapter(plan, source):
    """Load exact approved source bytes and tensor weights, then expose capabilities.

    provenance.native has architecture, model_source, native_source, checkpoint,
    cpu_threads and optionally torch_version. Values ending in _source and the
    checkpoint value are artifact names, not unrestricted paths. For COG,
    native_source names the inspected vendor/mamba2.py; for the other three it
    names native_csm.py. The pinned models.py/model.py supplies the constructor.

    Loading trusted Python is code execution. The suite requires --allow-native
    before invoking this factory. Hash checks bind bytes; they do not sandbox code
    or attest its license, honesty or scientific qualification.
    """
    import torch

    spec = plan.get("provenance", {}).get("native")
    required = {"architecture", "model_source", "native_source", "checkpoint", "cpu_threads"}
    _require(
        type(spec) is dict and required <= set(spec) and set(spec) <= required | {"torch_version"},
        "explicit native source specification required",
    )
    arm = spec["architecture"]
    _require(
        arm in ("csm", "transformer", "gated_delta_reference", "cog"),
        "unsupported source interface",
    )
    _require(
        type(spec["cpu_threads"]) is int and 1 <= spec["cpu_threads"] <= 8,
        "native CPU threads must be explicitly bounded to 1..8",
    )
    if "torch_version" in spec:
        _require(
            str(torch.__version__) == spec["torch_version"], "declared PyTorch runtime differs"
        )
    source = Path(source).resolve()
    model_bytes = _pinned_bytes(plan, source, spec["model_source"], 2 * 1024 * 1024)
    native_bytes = _pinned_bytes(plan, source, spec["native_source"], 2 * 1024 * 1024)
    checkpoint_bytes = _pinned_bytes(plan, source, spec["checkpoint"], 256 * 1024 * 1024)
    checkpoint_pin = hashlib.sha256(checkpoint_bytes).hexdigest()
    _require(
        plan["identities"]["model"] == checkpoint_pin,
        "model identity must bind the exact checkpoint bytes",
    )
    # weights_only forbids arbitrary checkpoint-pickle constructors. Python model
    # sources above remain explicitly trusted code, separate from the checkpoint.
    checkpoint = torch.load(io.BytesIO(checkpoint_bytes), map_location="cpu", weights_only=True)
    _require(type(checkpoint) is dict, "checkpoint mapping required")
    state_key = "state" if arm == "cog" else "state_dict"
    weights = checkpoint.get(state_key)
    _require(
        isinstance(weights, dict)
        and weights
        and all(
            isinstance(value, torch.Tensor)
            and (not value.is_floating_point() or bool(torch.isfinite(value).all()))
            for value in weights.values()
        ),
        "finite tensor-only state dictionary required",
    )
    if "arm" in checkpoint:
        _require(checkpoint["arm"] == arm, "checkpoint architecture metadata differs")
    names = (
        ("vendor", "vendor.mamba2", "_veritas_pinned_cog")
        if arm == "cog"
        else ("native_csm", "_veritas_pinned_models")
    )
    prior = {name: sys.modules.get(name) for name in names}
    try:
        with TemporaryDirectory(prefix="veritas-latent-native-") as temporary:
            root = Path(temporary)
            native_path, model_path = root / "native.py", root / "model.py"
            native_path.write_bytes(native_bytes)
            model_path.write_bytes(model_bytes)
            if arm == "cog":
                vendor = ModuleType("vendor")
                vendor.__path__ = []
                sys.modules["vendor"] = vendor
                _module("vendor.mamba2", native_path)
                module = _module("_veritas_pinned_cog", model_path)
            else:
                _module("native_csm", native_path)
                module = _module("_veritas_pinned_models", model_path)
            torch.set_num_threads(spec["cpu_threads"])
            with torch.random.fork_rng(devices=[]):
                torch.manual_seed(0)
                model = (
                    module.LM(module.Config(**checkpoint["config"]))
                    if arm == "cog"
                    else module.make(arm)
                )
            initial = model.state_dict()
            _require(
                set(initial) == set(weights)
                and all(initial[key].dtype == weights[key].dtype for key in initial),
                "checkpoint keys and dtypes must match the native constructor without casting",
            )
            expected = {key: value.detach().cpu().clone() for key, value in weights.items()}
            model.load_state_dict(weights, strict=True)
            model = model.cpu().eval()
            restored = model.state_dict()
            _require(
                set(restored) == set(expected)
                and all(
                    restored[key].dtype == expected[key].dtype
                    and torch.equal(restored[key].detach().cpu(), expected[key])
                    for key in restored
                ),
                "loaded model tensors differ from the exact checkpoint state",
            )
            for parameter in model.parameters():
                parameter.requires_grad_(False)
            options = (
                {"successor_ids": module.successor_ids, "mix": module.mix} if arm == "cog" else {}
            )
            return language_adapter(model, arm, **options)
    finally:
        for name, previous in prior.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
