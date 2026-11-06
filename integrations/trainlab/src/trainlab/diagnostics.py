"""Opt-in value checks and host-wall timing; no framework or device attestation."""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter_ns

from .runner import LabError, _finite


def require_finite(name: str, values) -> int:
    """Check numeric scalars without retaining or printing model/data values.

    Convert framework tensors explicitly; this function never moves device data.
    Empty collections are rejected rather than treated as successful inspection.
    """
    count = 0
    for value in values:
        if not _finite(value):
            raise LabError(f"nonfinite or nonnumeric value in {name}")
        count += 1
    if not count:
        raise LabError(f"no values inspected in {name}")
    return count


class ModuleProfiler:
    """Time explicitly named model regions, including nested inclusive regions.

    Host wall time includes instrumentation overhead. Async accelerator kernels
    require a caller-supplied synchronization function (e.g. cuda.synchronize).
    This is neither operator/kernel tracing nor physical-device qualification.
    Instances are intended for one execution thread; aggregate worker reports
    outside the measured path when using distributed launchers.
    """

    def __init__(self, *, synchronize=None):
        self.synchronize = synchronize
        self.modules = {}

    @contextmanager
    def measure(self, name: str):
        if not isinstance(name, str) or not name.strip() or len(name) > 120:
            raise LabError("module name must be a bounded nonempty string")
        if name not in self.modules and len(self.modules) >= 256:
            raise LabError("module profile supports at most 256 named regions")
        if self.synchronize is not None:
            self.synchronize()
        # Reserve on entry so nested active regions count toward the bound.
        row = self.modules.setdefault(
            name,
            {
                "calls": 0,
                "failed_calls": 0,
                "total_seconds": 0.0,
                "min_seconds": 0.0,
                "max_seconds": 0.0,
            },
        )
        start = perf_counter_ns()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            if self.synchronize is not None:
                self.synchronize()
            elapsed = (perf_counter_ns() - start) / 1_000_000_000
            row["calls"] += 1
            row["failed_calls"] += int(failed)
            row["total_seconds"] += elapsed
            row["min_seconds"] = elapsed if row["calls"] == 1 else min(row["min_seconds"], elapsed)
            row["max_seconds"] = max(row["max_seconds"], elapsed)

    def report(self) -> dict:
        return {
            "schema": "trainlab.module_profile.v1",
            "clock": "host_wall",
            "synchronized": self.synchronize is not None,
            "timing": "inclusive_instrumented_regions",
            "modules": {name: dict(row) for name, row in sorted(self.modules.items())},
            "qualification": "NOT_QUALIFIED",
        }
