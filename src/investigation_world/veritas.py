from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from investigation_world.operational import (
    OperationalDistributionCase,
    OperationalDistributionConfig,
    OperationalDistributionManifest,
    OperationalEntity,
    OperationalEpisode,
    OperationalRelation,
    OperationalRuntime,
    OperationalSuiteManifest,
    PersistentOperationalSubstrate,
    WorldDomain,
    build_operational_suite,
    build_operational_world,
    compile_operational_distribution,
    distribution_manifest as build_distribution_manifest,
    operational_suite_manifest,
    validate_operational_distribution,
    write_operational_distribution_bundle,
)


@dataclass(frozen=True)
class VeritasCapability:
    capability_id: str
    category: str
    maturity: str
    module: str
    description: str


_CAPABILITIES: tuple[VeritasCapability, ...] = (
    VeritasCapability(
        capability_id="unified_operational_worlds",
        category="environment",
        maturity="production_scale_distribution",
        module="investigation_world.operational",
        description="Five operational domains on one persistent runtime/verifier contract with deterministic train/IID/OOD/adversarial distributions.",
    ),
    VeritasCapability(
        capability_id="companyworld",
        category="environment",
        maturity="commercial_pilot",
        module="investigation_world.companyworld",
        description="Synthetic enterprise investigation, action, control, and dynamic-work environments.",
    ),
    VeritasCapability(
        capability_id="external_investigation",
        category="environment",
        maturity="implemented",
        module="investigation_world.external",
        description="Evidence-heavy OSINT and external-investigation capability family.",
    ),
    VeritasCapability(
        capability_id="selective_agency",
        category="benchmark",
        maturity="implemented_distribution",
        module="investigation_world.benchmark",
        description="Execute, clarify, reframe, decline, and no-op judgment under hidden consequences.",
    ),
    VeritasCapability(
        capability_id="capability_foundry",
        category="foundry",
        maturity="implemented",
        module="investigation_world.foundry",
        description="Trace, reward, failure mining, challenge generation, and capability-development plumbing.",
    ),
    VeritasCapability(
        capability_id="continuous_capability_observatory",
        category="evaluation",
        maturity="implemented",
        module="investigation_world.observatory",
        description="Longitudinal world × model × harness × seed × snapshot capability observation.",
    ),
    VeritasCapability(
        capability_id="reality_calibration",
        category="world_building",
        maturity="implemented_primitives",
        module="investigation_world.calibration",
        description="Provenance-backed calibration sources, targets, procedures, and quality reports.",
    ),
    VeritasCapability(
        capability_id="verified_training_products",
        category="training",
        maturity="implemented_boundary",
        module="investigation_world.foundry.training",
        description="Verifier-qualified demonstrations, preferences, SFT/RL bundles, and VOPSD inputs.",
    ),
)


@dataclass(frozen=True)
class VeritasProductInfo:
    name: str = "Veritas"
    product_type: str = "verified capability foundry"
    substrate: str = "persistent unified operational world"
    verifier: str = "independent multi-layer verifier"
    domains: tuple[str, ...] = tuple(domain.value for domain in WorldDomain)
    capability_ids: tuple[str, ...] = tuple(item.capability_id for item in _CAPABILITIES)
    default_operational_distribution_cases: int = OperationalDistributionConfig().total_cases


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
    """Canonical entry point for the complete Veritas capability foundry.

    Operational worlds share one substrate/runtime/verifier contract. Existing
    CompanyWorld, External Investigation, Selective Agency, observatory,
    calibration, foundry, and training-product modules remain first-class
    capabilities surfaced through the product catalog rather than separate brands.
    """

    def __init__(self, *, seed: int = 42):
        self.seed = seed
        self.info = VeritasProductInfo()

    def capabilities(self) -> list[VeritasCapability]:
        return list(_CAPABILITIES)

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

    def distribution_config(self, **overrides: int | str) -> OperationalDistributionConfig:
        payload: dict[str, int | str] = {"seed": self.seed}
        payload.update(overrides)
        return OperationalDistributionConfig.model_validate(payload)

    def build_distribution(
        self,
        config: OperationalDistributionConfig | None = None,
    ) -> list[OperationalDistributionCase]:
        return compile_operational_distribution(config or OperationalDistributionConfig(seed=self.seed))

    def distribution_manifest(
        self,
        cases: list[OperationalDistributionCase] | None = None,
        *,
        config: OperationalDistributionConfig | None = None,
    ) -> OperationalDistributionManifest:
        resolved_config = config or OperationalDistributionConfig(seed=self.seed)
        resolved_cases = cases if cases is not None else self.build_distribution(resolved_config)
        return build_distribution_manifest(resolved_cases, config=resolved_config)

    def validate_distribution(
        self,
        cases: list[OperationalDistributionCase] | None = None,
        *,
        config: OperationalDistributionConfig | None = None,
    ) -> dict[str, object]:
        resolved_config = config or OperationalDistributionConfig(seed=self.seed)
        resolved_cases = cases if cases is not None else self.build_distribution(resolved_config)
        return validate_operational_distribution(resolved_cases, config=resolved_config)

    def write_distribution(
        self,
        *,
        output: str | Path,
        oracle_output: str | Path,
        config: OperationalDistributionConfig | None = None,
    ) -> dict[str, object]:
        return write_operational_distribution_bundle(
            output=output,
            oracle_output=oracle_output,
            config=config or OperationalDistributionConfig(seed=self.seed),
        )

    @staticmethod
    def _populate_entity_graph(
        substrate: PersistentOperationalSubstrate,
        episodes: list[OperationalEpisode],
    ) -> None:
        all_domains = sorted({episode.task.domain for episode in episodes}, key=lambda d: d.value)
        substrate.register_entity(
            OperationalEntity(
                entity_id=substrate.organization_id,
                entity_type="organization",
                label=substrate.organization_id,
                domains=all_domains,
                attributes={"seed": substrate.seed},
            )
        )

        aggregate: dict[str, dict[str, object]] = {}
        record_domains: dict[str, WorldDomain] = {}
        for episode in episodes:
            for record in episode.records:
                record_domains[record.record_id] = episode.task.domain
                bucket = aggregate.setdefault(
                    record.object_id,
                    {
                        "domains": set(),
                        "record_types": set(),
                        "systems": set(),
                        "record_ids": set(),
                    },
                )
                bucket["domains"].add(episode.task.domain)  # type: ignore[union-attr]
                bucket["record_types"].add(record.record_type)  # type: ignore[union-attr]
                bucket["systems"].add(record.system)  # type: ignore[union-attr]
                bucket["record_ids"].add(record.record_id)  # type: ignore[union-attr]

        for object_id in sorted(aggregate):
            bucket = aggregate[object_id]
            domains = sorted(bucket["domains"], key=lambda d: d.value)  # type: ignore[arg-type]
            record_types = sorted(bucket["record_types"])  # type: ignore[arg-type]
            systems = sorted(bucket["systems"])  # type: ignore[arg-type]
            record_ids = sorted(bucket["record_ids"])  # type: ignore[arg-type]
            substrate.register_entity(
                OperationalEntity(
                    entity_id=object_id,
                    entity_type=(record_types[0] if len(record_types) == 1 else "operational_object"),
                    label=object_id,
                    domains=domains,
                    attributes={
                        "record_types": record_types,
                        "systems": systems,
                        "record_ids": record_ids,
                    },
                )
            )
            substrate.register_relation(
                OperationalRelation(
                    relation_id=f"{substrate.organization_id}::scope::{object_id}",
                    source_entity_id=substrate.organization_id,
                    relation_type="operational_scope_contains",
                    target_entity_id=object_id,
                    domains=domains,
                )
            )

        for episode in episodes:
            for record in episode.records:
                for target_id in record.related_object_ids:
                    if target_id not in aggregate:
                        continue
                    substrate.register_relation(
                        OperationalRelation(
                            relation_id=f"{record.record_id}::related::{target_id}",
                            source_entity_id=record.object_id,
                            relation_type="record_related_to",
                            target_entity_id=target_id,
                            domains=[record_domains[record.record_id]],
                            attributes={"record_id": record.record_id},
                        )
                    )

    def build_company(
        self,
        *,
        organization_id: str = "ORG-VERITAS-001",
        seed: int | None = None,
    ) -> VeritasCompany:
        resolved_seed = self.seed if seed is None else seed
        episodes = self.build_suite(seed=resolved_seed)
        for episode in episodes:
            episode.metadata["organization_id"] = organization_id
            episode.task.metadata["organization_id"] = organization_id
        substrate = PersistentOperationalSubstrate(organization_id, seed=resolved_seed)
        substrate.mount_suite(episodes)
        self._populate_entity_graph(substrate, episodes)
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
