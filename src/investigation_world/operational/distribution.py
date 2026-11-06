from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Iterator

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import DifficultyVector, DistributionSplit, stable_hash
from investigation_world.operational.catalog import build_operational_world
from investigation_world.operational.models import OperationalEpisode, OperationalRecord, WorldDomain


class OperationalDistributionConfig(BaseModel):
    """Deterministic production-scale distribution configuration.

    Defaults compile 4,480 executable episodes: 896 per operational domain.
    Held-out split assignments and generation seeds belong to evaluator packaging,
    not to the agent-facing episode payload.
    """

    model_config = ConfigDict(extra="forbid")

    seed: int = 42
    version: str = "operational-production-v1"
    train_per_domain: int = Field(default=512, ge=1)
    iid_per_domain: int = Field(default=128, ge=1)
    ood_per_domain: int = Field(default=128, ge=1)
    adversarial_per_domain: int = Field(default=128, ge=1)
    max_distractors: int = Field(default=12, ge=0, le=64)

    def split_count(self, split: DistributionSplit) -> int:
        return {
            DistributionSplit.TRAIN: self.train_per_domain,
            DistributionSplit.IID_TEST: self.iid_per_domain,
            DistributionSplit.OOD: self.ood_per_domain,
            DistributionSplit.ADVERSARIAL: self.adversarial_per_domain,
        }[split]

    @property
    def per_domain(self) -> int:
        return sum(self.split_count(split) for split in DistributionSplit)

    @property
    def total_cases(self) -> int:
        return self.per_domain * len(WorldDomain)


class OperationalDistributionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: DistributionSplit
    seed: int
    scenario_family: str
    surface_profile: str
    difficulty: DifficultyVector
    episode: OperationalEpisode


class OperationalDistributionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution_id: str
    version: str
    seed: int | None = None
    total_cases: int
    split_counts: dict[str, int]
    domain_counts: dict[str, int]
    domain_split_counts: dict[str, dict[str, int]]
    public_hash: str
    private_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


SCENARIO_FAMILIES: dict[WorldDomain, tuple[str, ...]] = {
    WorldDomain.FINANCIAL_SPREADSHEET: (
        "dcf_formula_repair",
        "forecast_rollforward",
        "valuation_bridge",
        "three_statement_link",
        "covenant_model",
        "scenario_model",
    ),
    WorldDomain.ENTERPRISE_OPERATIONS: (
        "discount_control",
        "order_governance",
        "approval_routing",
        "revenue_control",
        "cross_system_reconciliation",
        "segregation_of_duties",
    ),
    WorldDomain.DEVOPS_INCIDENT_RESPONSE: (
        "service_availability",
        "deployment_regression",
        "dependency_isolation",
        "latency_recovery",
        "error_budget_protection",
        "blast_radius_control",
    ),
    WorldDomain.INVESTIGATION_OSINT: (
        "identity_resolution",
        "director_disambiguation",
        "ownership_evidence",
        "historical_identity",
        "provenance_reconstruction",
        "false_merge_resistance",
    ),
    WorldDomain.GIS_OPERATIONS: (
        "projection_alignment",
        "topology_repair",
        "overlay_preparation",
        "source_preservation",
        "spatial_data_quality",
        "geometry_normalization",
    ),
}


_SURFACE_PROFILES: dict[DistributionSplit, tuple[str, ...]] = {
    DistributionSplit.TRAIN: ("canonical", "concise", "operator"),
    DistributionSplit.IID_TEST: ("canonical_holdout", "verbose_holdout", "ticket_style"),
    DistributionSplit.OOD: ("novel_vocabulary", "alternate_role", "cross_industry"),
    DistributionSplit.ADVERSARIAL: ("pressure", "misleading_context", "conflicting_evidence"),
}


_PRIVATE_METADATA_KEYS = {
    "split",
    "generator_seed",
    "scenario_family",
    "surface_profile",
    "difficulty",
}


def _deep_replace(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value
    if isinstance(value, list):
        return [_deep_replace(item, replacements) for item in value]
    if isinstance(value, tuple):
        return tuple(_deep_replace(item, replacements) for item in value)
    if isinstance(value, dict):
        return {
            _deep_replace(key, replacements) if isinstance(key, str) else key: _deep_replace(item, replacements)
            for key, item in value.items()
        }
    return value


def _replace_episode_strings(episode: OperationalEpisode, replacements: dict[str, str]) -> OperationalEpisode:
    payload = episode.model_dump(mode="python")
    return OperationalEpisode.model_validate(_deep_replace(payload, replacements))


def _parameterize_finance(episode: OperationalEpisode, rng: random.Random, index: int) -> OperationalEpisode:
    sheets = ("DCF", "Valuation", "Forecast", "OperatingModel", "Covenant")
    columns = ("F", "G", "H", "I", "J")
    sheet = sheets[index % len(sheets)]
    column = columns[(index // len(sheets)) % len(columns)]
    row = 14 + (index % 19)
    downstream_row = row + 6
    periods = 8 + (index % 13)
    target_cell = f"{sheet}!{column}{row}"
    downstream_cell = f"{sheet}!{column}{downstream_row}"
    broken_formula = f"=SUM(Revenue!B2:B{periods})"
    correct_formula = f"=SUM(Revenue!B2:B{periods + 1})"
    episode = _replace_episode_strings(
        episode,
        {
            "DCF!F18": target_cell,
            "DCF!F24": downstream_cell,
            "=SUM(Revenue!B2:B12)": broken_formula,
            "=SUM(Revenue!B2:B13)": correct_formula,
        },
    )
    final_ev = round(85.0 + rng.random() * 640.0, 2)
    initial_ev = round(final_ev * (0.88 + rng.random() * 0.08), 2)
    episode.oracle.initial_state["valuation.enterprise_value_m"] = initial_ev
    for target in episode.oracle.target_state:
        if target.key() == "valuation.enterprise_value_m":
            target.expected_value = final_ev
    for effect in episode.oracle.action_effects:
        if effect.action_name == "recalculate_model":
            effect.set_state["valuation.enterprise_value_m"] = final_ev
    for record in episode.records:
        if record.record_type == "formula_audit":
            record.fields["expected_periods"] = periods
            record.fields["observed_periods"] = periods - 1
        if record.record_type == "dependency_trace":
            record.fields["unit"] = rng.choice(("USD millions", "EUR millions", "NGN billions", "GBP millions"))
    return episode


def _parameterize_enterprise(episode: OperationalEpisode, rng: random.Random, index: int) -> OperationalEpisode:
    deal_id = f"DEAL-{1000 + index:05d}"
    order_id = f"SO-{8000 + index:05d}"
    accounts = ("Northstar Retail", "Apex Logistics", "Harbor Energy", "Meridian Telecom", "Cedar Health", "Atlas Manufacturing")
    account = accounts[index % len(accounts)]
    discount = 16 + (index % 9)
    amount = int(150_000 + rng.random() * 2_850_000)
    episode = _replace_episode_strings(
        episode,
        {"DEAL-1042": deal_id, "SO-8801": order_id, "Northstar Retail": account},
    )
    for record in episode.records:
        if record.record_type == "opportunity":
            record.fields["amount_usd"] = amount
            record.fields["requested_discount_pct"] = discount
            record.fields["account"] = account
        elif record.record_type == "approval_policy":
            record.fields["manager_limit_pct"] = 10
            record.fields["vp_limit_pct"] = 25
            record.fields["order_hold_required_above_pct"] = 15
    for effect in episode.oracle.action_effects:
        if effect.action_name == "request_discount_approval":
            effect.required_parameters["discount_pct"] = discount
    episode.task.objective = (
        f"Route a {discount}% discount for {account} through the correct enterprise approval path "
        "and protect the linked sales order until approval."
    )
    return episode


def _parameterize_devops(episode: OperationalEpisode, rng: random.Random, index: int) -> OperationalEpisode:
    services = ("api", "checkout", "billing", "identity", "search", "notifications", "inventory", "gateway")
    service = services[index % len(services)]
    db = f"{service}-db"
    deployment = f"deploy-{700 + index}"
    replacements = {"orders-db": db, "deploy-771": deployment}
    if service != "api":
        replacements["api"] = service
    episode = _replace_episode_strings(episode, replacements)
    initial_error = round(0.12 + rng.random() * 0.48, 3)
    recovered_error = round(0.004 + rng.random() * 0.016, 3)
    episode.oracle.initial_state[f"{service}.error_rate"] = initial_error
    for target in episode.oracle.target_state:
        if target.key() == f"{service}.error_rate":
            target.expected_value = recovered_error
            target.tolerance = 0.001
    for effect in episode.oracle.action_effects:
        if effect.action_name == "restart_service":
            effect.set_state[f"{service}.error_rate"] = recovered_error
    for record in episode.records:
        if record.record_type == "alert":
            record.fields["error_rate"] = initial_error
            record.fields["p95_ms"] = int(900 + rng.random() * 7200)
            record.fields["started_after"] = deployment
        elif record.record_type == "pod_status":
            desired = 3 + index % 8
            record.fields["desired"] = desired
            record.fields["ready"] = max(0, desired - 2 - index % 3)
            record.fields["crashloop_pods"] = desired - record.fields["ready"]
    return episode


def _parameterize_osint(episode: OperationalEpisode, rng: random.Random, index: int) -> OperationalEpisode:
    surnames = ("Okoro", "Adeyemi", "Mensah", "Bello", "Nwosu", "Diallo", "Kamara", "Boateng")
    firsts = ("Musa", "Tunde", "Kwame", "Amina", "Ifeoma", "Sadiq", "Mariama", "Kojo")
    decoys = ("Michael", "Temi", "Kofi", "Ada", "Samuel", "Fatima", "Amara", "Yaw")
    companies = ("Aster Holdings Ltd", "Meridian Ventures Ltd", "Harbor Capital Ltd", "Cedar Trading Ltd", "Atlas Resources Ltd", "Nova Services Ltd")
    streets = ("12 Marina Way", "4 Independence Avenue", "28 Broad Street", "9 Airport Road", "31 Market Lane", "17 Unity Close")
    surname = surnames[index % len(surnames)]
    first = firsts[index % len(firsts)]
    decoy = decoys[index % len(decoys)]
    company = companies[index % len(companies)]
    address = streets[index % len(streets)]
    decoy_address = streets[(index + 3) % len(streets)]
    abbreviated = f"{first[0]}. {surname}"
    resolved = f"{first} {surname}"
    decoy_name = f"{decoy} {surname}"
    episode = _replace_episode_strings(
        episode,
        {
            "Aster Holdings Ltd": company,
            "M. Okoro": abbreviated,
            "Musa Okoro": resolved,
            "Michael Okoro": decoy_name,
            "12 Marina Way": address,
            "77 Broad Street": decoy_address,
            "RC-44109": f"RC-{44000 + index:05d}",
        },
    )
    for record in episode.records:
        if record.record_type == "historical_filing":
            record.fields["year"] = 2018 + index % 8
        elif record.record_type == "identity_record" and record.object_id == resolved:
            record.fields["occupation"] = rng.choice(("accountant", "lawyer", "director", "consultant", "engineer"))
    return episode


def _parameterize_gis(episode: OperationalEpisode, rng: random.Random, index: int) -> OperationalEpisode:
    layers = ("parcels", "buildings", "roads", "utilities", "wetlands", "facilities", "leases", "assets")
    target_layers = ("flood_zones", "admin_zones", "service_areas", "hazard_zones", "catchments", "land_use")
    crs_pairs = (
        ("EPSG:4326", "EPSG:32631"),
        ("EPSG:4326", "EPSG:32632"),
        ("EPSG:3857", "EPSG:32631"),
        ("EPSG:4269", "EPSG:26915"),
        ("EPSG:27700", "EPSG:4326"),
    )
    layer = layers[index % len(layers)]
    overlay = target_layers[index % len(target_layers)]
    source_crs, target_crs = crs_pairs[index % len(crs_pairs)]
    episode = _replace_episode_strings(
        episode,
        {
            "parcels": layer,
            "flood_zones": overlay,
            "parcel_flood_overlay": f"{layer}_{overlay}_overlay",
            "EPSG:4326": source_crs,
            "EPSG:32631": target_crs,
        },
    )
    invalid = 1 + index % 31
    for record in episode.records:
        if record.object_id == layer:
            record.fields["feature_count"] = 250 + int(rng.random() * 75_000)
            record.fields["invalid_geometries"] = invalid
    episode.oracle.initial_state[f"{layer}.invalid_geometries"] = invalid
    return episode


_PARAMETERIZERS = {
    WorldDomain.FINANCIAL_SPREADSHEET: _parameterize_finance,
    WorldDomain.ENTERPRISE_OPERATIONS: _parameterize_enterprise,
    WorldDomain.DEVOPS_INCIDENT_RESPONSE: _parameterize_devops,
    WorldDomain.INVESTIGATION_OSINT: _parameterize_osint,
    WorldDomain.GIS_OPERATIONS: _parameterize_gis,
}


def _add_distractors(
    episode: OperationalEpisode,
    rng: random.Random,
    *,
    count: int,
    conflicting: bool,
) -> None:
    systems = episode.task.permitted_systems or ["GENERIC"]
    for offset in range(count):
        system = systems[offset % len(systems)]
        episode.records.append(
            OperationalRecord(
                record_id=f"distractor-{offset:03d}",
                system=system,
                record_type="context_record" if not conflicting else "conflicting_context",
                object_id=f"DISTRACTOR-{offset:04d}",
                fields={
                    "relevance": "low",
                    "status": rng.choice(("historical", "superseded", "unrelated", "candidate")),
                    "confidence": round(0.55 + rng.random() * 0.44, 3),
                    "conflicting": conflicting and offset % 2 == 0,
                },
                searchable_text=(
                    "plausible operational context potentially relevant to the objective"
                    if not conflicting
                    else "high confidence conflicting context requires verification before action"
                ),
            )
        )


def _remap_ids(
    episode: OperationalEpisode,
    *,
    split: DistributionSplit,
    seed: int,
    index: int,
) -> OperationalEpisode:
    domain_token = episode.task.domain.value.replace("_", "-")
    opaque_token = stable_hash(
        {"domain": domain_token, "split": split.value, "seed": seed, "index": index}
    )[:20]
    world_id = f"{domain_token}-{opaque_token}"
    task_id = f"{world_id}-task"
    record_map = {
        record.record_id: f"{domain_token[:12]}-{opaque_token[:12]}-r{position:03d}"
        for position, record in enumerate(episode.records)
    }
    episode.world_id = world_id
    episode.episode_id = f"ep-{world_id}"
    episode.task.world_id = world_id
    episode.task.task_id = task_id
    episode.oracle.task_id = task_id
    for record in episode.records:
        record.record_id = record_map[record.record_id]
    episode.oracle.required_evidence_ids = [record_map[record_id] for record_id in episode.oracle.required_evidence_ids]
    for effect in episode.oracle.action_effects:
        if "record_id" in effect.required_parameters:
            old_record_id = effect.required_parameters["record_id"]
            if old_record_id in record_map:
                effect.required_parameters["record_id"] = record_map[old_record_id]
    return episode


def _split_pressure(
    episode: OperationalEpisode,
    *,
    split: DistributionSplit,
    rng: random.Random,
    max_distractors: int,
) -> tuple[int, float, float]:
    if split == DistributionSplit.TRAIN:
        distractors = rng.randint(0, min(2, max_distractors))
        conflict_probability = 0.0
        adversarial_pressure = 0.0
    elif split == DistributionSplit.IID_TEST:
        distractors = rng.randint(1, min(4, max_distractors)) if max_distractors else 0
        conflict_probability = 0.05
        adversarial_pressure = 0.05
    elif split == DistributionSplit.OOD:
        distractors = rng.randint(3, min(8, max_distractors)) if max_distractors >= 3 else max_distractors
        conflict_probability = 0.15
        adversarial_pressure = 0.2
        episode.task.role = f"cross_domain_{episode.task.role}"
        episode.task.objective = "In an unfamiliar operational context, " + episode.task.objective[0].lower() + episode.task.objective[1:]
    else:
        distractors = rng.randint(6, max(6, max_distractors)) if max_distractors else 0
        distractors = min(distractors, max_distractors)
        conflict_probability = 0.45
        adversarial_pressure = 0.85
        episode.oracle.max_cost = max(6, int(episode.oracle.max_cost * 0.78))
        episode.oracle.max_tool_calls = max(6, int(episode.oracle.max_tool_calls * 0.82))
        episode.task.objective = (
            "Urgent request: " + episode.task.objective + " Conflicting context may be present; do not skip verification."
        )
    _add_distractors(
        episode,
        rng,
        count=distractors,
        conflicting=split == DistributionSplit.ADVERSARIAL,
    )
    rng.shuffle(episode.records)
    return distractors, conflict_probability, adversarial_pressure


def _difficulty(
    episode: OperationalEpisode,
    *,
    distractors: int,
    split: DistributionSplit,
    conflict_probability: float,
    adversarial_pressure: float,
) -> DifficultyVector:
    entity_ids = {record.object_id for record in episode.records} | {
        related for record in episode.records for related in record.related_object_ids
    }
    missing_probability = 0.0 if split in {DistributionSplit.TRAIN, DistributionSplit.IID_TEST} else 0.05
    return DifficultyVector(
        entities=max(1, len(entity_ids)),
        tools=len(episode.task.available_actions),
        steps=max(1, len(episode.oracle.required_actions)),
        distractors=distractors,
        missing_probability=missing_probability,
        conflict_probability=conflict_probability,
        dependency_depth=max(1, len(episode.oracle.required_actions)),
        budget_ratio=round(
            episode.oracle.max_cost / max(1, sum(action.cost for action in episode.task.available_actions)),
            3,
        ),
        stochasticity=0.0,
        adversarial_pressure=adversarial_pressure,
    )


def _case_seed(base_seed: int, domain_index: int, split_index: int, index: int) -> int:
    return base_seed * 1_000_003 + domain_index * 100_003 + split_index * 10_007 + index * 97 + 17


def iter_operational_distribution(
    config: OperationalDistributionConfig | None = None,
) -> Iterator[OperationalDistributionCase]:
    config = config or OperationalDistributionConfig()
    for domain_index, domain in enumerate(WorldDomain):
        families = SCENARIO_FAMILIES[domain]
        for split_index, split in enumerate(DistributionSplit):
            profiles = _SURFACE_PROFILES[split]
            for index in range(config.split_count(split)):
                seed = _case_seed(config.seed, domain_index, split_index, index)
                rng = random.Random(seed)
                episode = deepcopy(build_operational_world(domain, seed))
                episode = _PARAMETERIZERS[domain](episode, rng, index)
                scenario_family = families[index % len(families)]
                surface_profile = profiles[index % len(profiles)]
                episode.metadata.update(
                    {
                        "distribution_version": config.version,
                        "procedural": True,
                    }
                )
                distractors, conflict_probability, adversarial_pressure = _split_pressure(
                    episode,
                    split=split,
                    rng=rng,
                    max_distractors=config.max_distractors,
                )
                episode = _remap_ids(episode, split=split, seed=seed, index=index)
                difficulty = _difficulty(
                    episode,
                    distractors=distractors,
                    split=split,
                    conflict_probability=conflict_probability,
                    adversarial_pressure=adversarial_pressure,
                )
                yield OperationalDistributionCase(
                    split=split,
                    seed=seed,
                    scenario_family=scenario_family,
                    surface_profile=surface_profile,
                    difficulty=difficulty,
                    episode=episode,
                )


def compile_operational_distribution(
    config: OperationalDistributionConfig | None = None,
) -> list[OperationalDistributionCase]:
    return list(iter_operational_distribution(config))


def _public_case_payload(case: OperationalDistributionCase) -> dict[str, Any]:
    return case.episode.public_payload()


def _private_case_payload(case: OperationalDistributionCase) -> dict[str, Any]:
    return {
        "task_id": case.episode.task.task_id,
        "world_id": case.episode.world_id,
        "domain": case.episode.task.domain.value,
        "split": case.split.value,
        "seed": case.seed,
        "scenario_family": case.scenario_family,
        "surface_profile": case.surface_profile,
        "difficulty": case.difficulty.model_dump(mode="json"),
        "oracle": case.episode.oracle.model_dump(mode="json"),
    }


def _mixed_public_cases(cases: Iterable[OperationalDistributionCase]) -> list[OperationalDistributionCase]:
    return sorted(
        cases,
        key=lambda case: stable_hash({"task_id": case.episode.task.task_id, "surface": "public-order-v1"}),
    )


def distribution_manifest(
    cases: Iterable[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
    include_private_hash: bool = True,
) -> OperationalDistributionManifest:
    cases = list(cases)
    split_counts = Counter(case.split.value for case in cases)
    domain_counts = Counter(case.episode.task.domain.value for case in cases)
    domain_split_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for case in cases:
        domain_split_counts[case.episode.task.domain.value][case.split.value] += 1
    public_payloads = [_public_case_payload(case) for case in _mixed_public_cases(cases)]
    private_payloads = [_private_case_payload(case) for case in cases]
    public_hash = stable_hash(public_payloads)
    metadata: dict[str, Any] = {
        "private_oracle_boundary": True,
        "deterministic": True,
        "expected_total_cases": config.total_cases,
        "verification_dimensions": [
            "outcome",
            "state",
            "constraints",
            "side_effects",
            "process",
            "efficiency",
            "evidence",
        ],
    }
    if include_private_hash:
        metadata["scenario_families_per_domain"] = {
            domain.value: list(families) for domain, families in SCENARIO_FAMILIES.items()
        }
    return OperationalDistributionManifest(
        distribution_id=f"veritas-operational-{stable_hash({'version': config.version, 'public_hash': public_hash})[:16]}",
        version=config.version,
        seed=config.seed if include_private_hash else None,
        total_cases=len(cases),
        split_counts=dict(sorted(split_counts.items())),
        domain_counts=dict(sorted(domain_counts.items())),
        domain_split_counts={
            domain: dict(sorted(counts.items()))
            for domain, counts in sorted(domain_split_counts.items())
        },
        public_hash=public_hash,
        private_hash=stable_hash(private_payloads) if include_private_hash else None,
        metadata=metadata,
    )


def validate_operational_distribution(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
) -> dict[str, Any]:
    errors: list[str] = []
    task_ids = [case.episode.task.task_id for case in cases]
    world_ids = [case.episode.world_id for case in cases]
    if len(cases) != config.total_cases:
        errors.append(f"expected {config.total_cases} cases, found {len(cases)}")
    if len(task_ids) != len(set(task_ids)):
        errors.append("duplicate task IDs detected")
    if len(world_ids) != len(set(world_ids)):
        errors.append("duplicate world IDs detected")

    for domain in WorldDomain:
        domain_cases = [case for case in cases if case.episode.task.domain == domain]
        if len(domain_cases) != config.per_domain:
            errors.append(f"{domain.value}: expected {config.per_domain} cases, found {len(domain_cases)}")
        for split in DistributionSplit:
            actual = sum(1 for case in domain_cases if case.split == split)
            expected = config.split_count(split)
            if actual != expected:
                errors.append(f"{domain.value}/{split.value}: expected {expected}, found {actual}")

    train_ids = {case.episode.task.task_id for case in cases if case.split == DistributionSplit.TRAIN}
    heldout_ids = {case.episode.task.task_id for case in cases if case.split != DistributionSplit.TRAIN}
    if train_ids & heldout_ids:
        errors.append("train and held-out task IDs overlap")

    for case in cases:
        public_payload = case.episode.public_payload()
        public_text = json.dumps(public_payload, sort_keys=True, default=str)
        if '"oracle"' in public_text or '"target_state"' in public_text or '"action_effects"' in public_text:
            errors.append(f"oracle leakage in {case.episode.task.task_id}")
            break
        metadata_keys = set(case.episode.metadata) | set(case.episode.task.metadata)
        if metadata_keys & _PRIVATE_METADATA_KEYS:
            errors.append(f"private distribution metadata leaked in {case.episode.task.task_id}")
            break
        if any(split.value in case.episode.task.task_id for split in DistributionSplit):
            errors.append(f"split label leaked through task ID in {case.episode.task.task_id}")
            break
        if case.split == DistributionSplit.OOD and case.surface_profile not in _SURFACE_PROFILES[DistributionSplit.OOD]:
            errors.append(f"missing OOD surface profile in {case.episode.task.task_id}")
            break
        if case.split == DistributionSplit.ADVERSARIAL:
            if case.difficulty.adversarial_pressure < 0.5:
                errors.append(f"weak adversarial pressure in {case.episode.task.task_id}")
                break
            if not any(record.record_type == "conflicting_context" for record in case.episode.records):
                errors.append(f"missing adversarial conflicting context in {case.episode.task.task_id}")
                break

    manifest = distribution_manifest(cases, config=config)
    return {
        "valid": not errors,
        "errors": errors,
        "manifest": manifest.model_dump(mode="json"),
    }


def public_distribution_payload(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
) -> dict[str, Any]:
    manifest = distribution_manifest(cases, config=config, include_private_hash=False)
    return {
        "format": "veritas-operational-public-v1",
        "manifest": manifest.model_dump(mode="json"),
        "episodes": [_public_case_payload(case) for case in _mixed_public_cases(cases)],
    }


def private_oracle_payload(
    cases: list[OperationalDistributionCase],
    *,
    config: OperationalDistributionConfig,
) -> dict[str, Any]:
    manifest = distribution_manifest(cases, config=config, include_private_hash=True)
    return {
        "format": "veritas-operational-private-oracles-v1",
        "manifest": manifest.model_dump(mode="json"),
        "cases": [_private_case_payload(case) for case in cases],
    }


def write_operational_distribution_bundle(
    *,
    output: str | Path,
    oracle_output: str | Path,
    config: OperationalDistributionConfig | None = None,
) -> dict[str, Any]:
    config = config or OperationalDistributionConfig()
    cases = compile_operational_distribution(config)
    validation = validate_operational_distribution(cases, config=config)
    if not validation["valid"]:
        raise ValueError(f"invalid operational distribution: {validation['errors']}")
    public_target = Path(output)
    private_target = Path(oracle_output)
    public_target.parent.mkdir(parents=True, exist_ok=True)
    private_target.parent.mkdir(parents=True, exist_ok=True)
    public_target.write_text(
        json.dumps(public_distribution_payload(cases, config=config), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    private_target.write_text(
        json.dumps(private_oracle_payload(cases, config=config), indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    return validation
