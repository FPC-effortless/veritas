"""Optional PyTorch diagnostics; importing the base runner never imports torch."""

from __future__ import annotations

import sys
from contextlib import contextmanager

import torch

from .diagnostics import ModuleProfiler
from .runner import LabError


def resolve_device(name: str) -> torch.device:
    """Select an explicit CPU/CUDA device, never silently fall back to CPU."""
    try:
        device = torch.device(name)
    except (TypeError, RuntimeError) as exc:
        raise LabError("expected cpu or an available cuda device") from exc
    if device.type == "cpu" and device.index is None:
        return device
    if device.type != "cuda":
        raise LabError("only cpu and cuda devices are supported")
    if not torch.cuda.is_available():
        raise LabError("CUDA hardware/runtime is unavailable")
    index = torch.cuda.current_device() if device.index is None else device.index
    if index >= torch.cuda.device_count():
        raise LabError("CUDA device index is unavailable")
    return torch.device("cuda", index)


def check_tensor(name: str, tensor: torch.Tensor) -> int:
    """Inspect dense tensor finiteness without logging values or copying to CPU."""
    if (
        not isinstance(tensor, torch.Tensor)
        or tensor.layout != torch.strided
        or tensor.numel() == 0
        or tensor.device.type not in ("cpu", "cuda")
    ):
        raise LabError(f"expected a nonempty dense CPU/CUDA tensor in {name}")
    if not torch.isfinite(tensor.detach()).all().item():
        raise LabError(f"nonfinite tensor in {name}")
    return tensor.numel()


def check_model(model: torch.nn.Module, *, gradients: bool = False) -> dict:
    """Check parameters and, when requested, every trainable parameter's gradient."""
    result = {"parameter_values": 0, "gradient_values": 0}
    for name, parameter in model.named_parameters():
        result["parameter_values"] += check_tensor("parameter " + name, parameter)
        if gradients and parameter.requires_grad:
            if parameter.grad is None:
                raise LabError("missing gradient in " + name)
            result["gradient_values"] += check_tensor("gradient " + name, parameter.grad)
    if not result["parameter_values"]:
        raise LabError("no model parameters inspected")
    if gradients and not result["gradient_values"]:
        raise LabError("no trainable gradients inspected")
    return result


def _tensors(value):
    if isinstance(value, torch.Tensor):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _tensors(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _tensors(item)


def _modules(model, names):
    modules = {name or "<root>": module for name, module in model.named_modules()}
    if names is None:
        names = [name for name, module in modules.items() if not list(module.children())]
    if (
        not isinstance(names, (list, tuple))
        or not 1 <= len(names) <= 256
        or any(
            not isinstance(name, str) or name not in modules or len(name) > 120 for name in names
        )
        or len(set(names)) != len(names)
    ):
        raise LabError("select 1–256 distinct existing module names (at most 120 characters each)")
    return [(name, modules[name]) for name in names]


@contextmanager
def check_activations(model: torch.nn.Module, *, names=None):
    """Inspect tensor outputs of selected modules (all leaves by default).

    Nested dict/list/tuple outputs are supported. Checks synchronize when they
    read a device boolean; keep numerical debugging separate from profiling.
    Hooks are removed on success and failure. An empty inspection fails closed.
    """
    handles = []
    result = {"tensor_outputs_checked": 0, "values_checked": 0}
    failed = False

    def hook(name):
        def inspect(_module, _args, output):
            nonlocal failed
            try:
                for tensor in _tensors(output):
                    result["values_checked"] += check_tensor("activation " + name, tensor)
                    result["tensor_outputs_checked"] += 1
            except BaseException:
                failed = True
                raise

        return inspect

    try:
        for name, module in _modules(model, names):
            handles.append(module.register_forward_hook(hook(name)))
        yield result
        if failed:
            raise LabError("activation inspection failed; context is invalid")
        if not result["tensor_outputs_checked"]:
            raise LabError("no tensor activations inspected")
    finally:
        for handle in handles:
            handle.remove()


@contextmanager
def profile_modules(model: torch.nn.Module, *, device: str = "cpu", names=None):
    """Time selected modules on one thread/device, one context per DDP rank.

    Default selection is all leaves. Timing is inclusive synchronized host-wall
    time on CUDA, not kernel/event time. Caught forward errors invalidate the
    profile because their hooks cannot supply a valid completion time.
    """
    selected = resolve_device(device)
    modules = _modules(model, names)
    for _, module in modules:
        for tensor in (*module.parameters(), *module.buffers()):
            if tensor.device != selected:
                raise LabError("profile device does not match selected module tensors")
    synchronize = (lambda: torch.cuda.synchronize(selected)) if selected.type == "cuda" else None
    profiler = ModuleProfiler(synchronize=synchronize)
    handles = []
    active = {module: [] for _, module in modules}
    failed = False

    def pre(name):
        def start(module, args, kwargs):
            nonlocal failed
            try:
                for tensor in _tensors((args, kwargs)):
                    if tensor.device != selected:
                        raise LabError("profile device does not match module inputs")
                region = profiler.measure(name)
                region.__enter__()
                active[module].append(region)
            except BaseException:
                failed = True
                raise

        return start

    def post(module, _args, _output):
        nonlocal failed
        try:
            for tensor in _tensors(_output):
                if tensor.device != selected:
                    raise LabError("profile device does not match module outputs")
            active[module].pop().__exit__(None, None, None)
        except BaseException:
            failed = True
            raise

    try:
        for name, module in modules:
            handles.append(module.register_forward_pre_hook(pre(name), with_kwargs=True))
            handles.append(module.register_forward_hook(post))
        yield profiler
        if failed or any(active.values()):
            raise LabError("a selected module forward did not complete; profile is invalid")
        if not profiler.modules:
            raise LabError("no selected module calls were profiled")
    finally:
        error = sys.exc_info()
        for handle in handles:
            handle.remove()
        for regions in active.values():
            while regions:
                regions.pop().__exit__(*error)
