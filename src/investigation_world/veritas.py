from __future__ import annotations

from dataclasses import dataclass

from investigation_world.operational import (
    OperationalEpisode,
    OperationalRuntime,
    OperationalSuiteManifest,
    WorldDomain,
    build_operational_suite,
    build_operational_world,
    operational_suite_manifest,
)


@dataclass(frozen=True)
class VeritasProductInfo:
    name: str = "Veritas"
    product_type: str = "operational-world capability foundry"
    substrate: str = "unified operational world"
    verifier: str = "independent multi-layer verifier"
    domains: tuple[str, ...] = tuple(domain.value for domain in WorldDomain)


class Veritas:
    """Unified entry point for Veritas operational worlds and executable episodes.

    Existing CompanyWorld, External Investigation, Selective Agency, observatory,
    calibration, and training-product modules remain valid capability layers. This
    facade provides the common product surface for the new operational-world suite.
    """

    def __init__(self, *, seed: int = 42):
        self.seed = seed
        self.info = VeritasProductInfo()

    def domains(self) -> list[WorldDomain]:
        return list(WorldDomain)

    def build_world(self, domain: WorldDomain | str, *, seed: int | None = None) -> OperationalEpisode:
        return build_operational_world(domain, self.seed if seed is None else seed)

    def build_suite(self, *, seed: int | None = None) -> list[OperationalEpisode]:
        return build_operational_suite(self.seed if seed is None else seed)

    def manifest(self, *, seed: int | None = None, version: str = "1.0.0") -> OperationalSuiteManifest:
        return operational_suite_manifest(self.seed if seed is None else seed, version=version)

    def runtime(self, domain: WorldDomain | str, *, seed: int | None = None) -> OperationalRuntime:
        return OperationalRuntime(self.build_world(domain, seed=seed))
