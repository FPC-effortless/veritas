from __future__ import annotations

from dataclasses import dataclass

from investigation_world.operational import (
    OperationalEpisode,
    OperationalRuntime,
    OperationalSuiteManifest,
    PersistentOperationalSubstrate,
    WorldDomain,
    build_operational_suite,
    build_operational_world,
    operational_suite_manifest,
)


@dataclass(frozen=True)
class VeritasProductInfo:
    name: str = "Veritas"
    product_type: str = "operational-world capability foundry"
    substrate: str = "persistent unified operational world"
    verifier: str = "independent multi-layer verifier"
    domains: tuple[str, ...] = tuple(domain.value for domain in WorldDomain)


@dataclass
class VeritasCompany:
    """One persistent synthetic organization spanning all operational domains."""

    organization_id: str
    episodes: list[OperationalEpisode]
    substrate: PersistentOperationalSubstrate

    def world(self, domain: WorldDomain | str) -> OperationalEpisode:
        resolved = WorldDomain(domain)
        for episode in self.episodes:
            if episode.task.domain == resolved:
                return episode
        raise KeyError(resolved.value)

    def runtime(self, domain: WorldDomain | str) -> OperationalRuntime:
        return OperationalRuntime(self.world(domain), substrate=self.substrate)

    def snapshot(self):
        return self.substrate.snapshot()

    def fork(self, sequence: int | None = None) -> "VeritasCompany":
        return VeritasCompany(
            organization_id=self.organization_id,
            episodes=self.episodes,
            substrate=self.substrate.fork_at(sequence),
        )


class Veritas:
    """Canonical entry point for Veritas worlds, runtimes, and persistent companies.

    Existing CompanyWorld, External Investigation, Selective Agency, observatory,
    calibration, and training-product modules remain valid capability layers. This
    facade provides the common product surface for the operational-world suite.
    """

    def __init__(self, *, seed: int = 42):
        self.seed = seed
        self.info = VeritasProductInfo()

    def domains(self) -> list[WorldDomain]:
        return list(WorldDomain)

    def build_world(
        self,
        domain: WorldDomain | str,
        *,
        seed: int | None = None,
    ) -> OperationalEpisode:
        return build_operational_world(domain, self.seed if seed is None else seed)

    def build_suite(self, *, seed: int | None = None) -> list[OperationalEpisode]:
        return build_operational_suite(self.seed if seed is None else seed)

    def build_company(
        self,
        *,
        organization_id: str = "ORG-VERITAS-001",
        seed: int | None = None,
    ) -> VeritasCompany:
        resolved_seed = self.seed if seed is None else seed
        episodes = self.build_suite(seed=resolved_seed)
        substrate = PersistentOperationalSubstrate(organization_id, seed=resolved_seed)
        substrate.mount_suite(episodes)
        return VeritasCompany(
            organization_id=organization_id,
            episodes=episodes,
            substrate=substrate,
        )

    def manifest(
        self,
        *,
        seed: int | None = None,
        version: str = "1.0.0",
    ) -> OperationalSuiteManifest:
        return operational_suite_manifest(
            self.seed if seed is None else seed,
            version=version,
        )

    def runtime(
        self,
        domain: WorldDomain | str,
        *,
        seed: int | None = None,
        substrate: PersistentOperationalSubstrate | None = None,
    ) -> OperationalRuntime:
        return OperationalRuntime(
            self.build_world(domain, seed=seed),
            substrate=substrate,
        )
