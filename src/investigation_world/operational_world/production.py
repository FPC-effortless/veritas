from __future__ import annotations

from investigation_world.operational_world.calibration import compose_calibration_profiles
from investigation_world.operational_world.fusion import build_bootstrap_calibration
from investigation_world.operational_world.models import CompiledOperationalWorld, OperationalWorldSpec
from investigation_world.operational_world.pipeline import OperationalWorldCompiler as _PipelineCompiler


class OperationalWorldCompiler(_PipelineCompiler):
    """Public production compiler with explicit calibration completion.

    Source-specific empirical profiles are intentionally allowed to be partial. Before world
    generation, this facade composes the supplied profile with a bootstrap profile scoped to the
    requested world. Empirical/source-specific metrics win where compatible; uncovered metrics
    remain bootstrap priors and keep `state=hybrid`. This prevents both partial-profile crashes
    and the more dangerous alternative of silently relabeling missing dimensions as empirical.
    """

    def compile(self, spec: OperationalWorldSpec) -> CompiledOperationalWorld:
        original = self._calibration
        if original is None:
            return super().compile(spec)

        bootstrap = build_bootstrap_calibration(
            region=spec.region,
            industry=spec.industry,
            size_band=spec.size_band,
        )
        effective = compose_calibration_profiles(
            [bootstrap, original],
            profile_id=f"generation-{original.profile_id}-{spec.size_band.value}",
            region=spec.region,
            industry=spec.industry,
            size_band=spec.size_band,
        )
        self._calibration = effective
        try:
            return super().compile(spec)
        finally:
            self._calibration = original
