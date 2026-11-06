from __future__ import annotations

import json
import random
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import DifficultyVector, DistributionSplit, stable_hash
from investigation_world.projectworld.construction import build_construction_project_world
from investigation_world.projectworld.models import (
    HiddenDefect,
    ProjectPhase,
    ProjectScenario,
)


class ProjectDistributionConfig(BaseModel):
    """Deterministic construction ProjectWorld distribution.

    The default distribution contains 896 long-horizon projects with explicit
    train/IID/OOD/adversarial separation. Split identity and generator seed are
    evaluator-only and are not emitted in public scenario payloads.
    """

    model_config = ConfigDict(extra="forbid")

    seed: int = 42
    version: str = "projectworld-construction-v1"
    train: int = Field(default=512, ge=1)
    iid_test: int = Field(default=128, ge=1)
    ood: int = Field(default=128, ge=1)
    adversarial: int = Field(default=128, ge=1)

    def split_count(self, split: DistributionSplit) -> int:
        return {
            DistributionSplit.TRAIN: self.train,
            DistributionSplit.IID_TEST: self.iid_test,
            DistributionSplit.OOD: self.ood,
            DistributionSplit.ADVERSARIAL: self.adversarial,
        }[split]

    @property
    def total_cases(self) -> int:
        return sum(self.split_count(split) for split in DistributionSplit)


class ProjectDistributionCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    split: DistributionSplit
    seed: int
    scenario_family: str
    surface_profile: str
    difficulty: DifficultyVector
    scenario: ProjectScenario


class ProjectDistributionManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    distribution_id: str
    version: str
    seed: int | None = None
    total_cases: int
    split_counts: dict[str, int]
    project_type_counts: dict[str, int]
    public_hash: str
    private_hash: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


_PROJECT_TYPES: dict[DistributionSplit, tuple[str, ...]] = {
    DistributionSplit.TRAIN: (
        "mixed_use",
        "residential",
        "office",
        "hotel",
    ),
    DistributionSplit.IID_TEST: (
        "mixed_use",
        "residential",
        "office",
        "hotel",
    ),
    DistributionSplit.OOD: (
        "hospital",
        "laboratory",
        "data_center",
        "education",
    ),
    DistributionSplit.ADVERSARIAL: (
        "mixed_use",
        "hospital",
        "data_center",
        "hotel",
    ),
}

_SITE_PROFILES: dict[DistributionSplit, tuple[str, ...]] = {
    DistributionSplit.TRAIN: ("standard_urban", "suburban", "constrained_urban"),
    DistributionSplit.IID_TEST: ("standard_urban", "suburban", "constrained_urban"),
    DistributionSplit.OOD: ("brownfield", "coastal", "remote", "dense_cbd"),
    DistributionSplit.ADVERSARIAL: ("dense_cbd", "brownfield", "coastal", "constrained_urban"),
}

_DELIVERY_MODELS = (
    "design_bid_build",
    "design_build",
    "construction_management",
)

_SURFACE_PROFILES: dict[DistributionSplit, tuple[str, ...]] = {
    DistributionSplit.TRAIN: ("canonical", "operator", "commercial_brief"),
    DistributionSplit.IID_TEST: ("holdout", "client_brief", "project_controls"),
    DistributionSplit.OOD: ("novel_archetype", "unfamiliar_site", "alternate_delivery"),
    DistributionSplit.ADVERSARIAL: ("compressed_schedule", "volatile_market", "compound_disruption"),
}

_TYPE_FACTORS: dict[str, dict[str, float]] = {
    "mixed_use": {"cost": 1.00, "duration": 1.00, "mep": 1.00, "facade": 1.00},
    "residential": {"cost": 0.90, "duration": 0.94, "mep": 0.86, "facade": 0.92},
    "office": {"cost": 1.05, "duration": 0.98, "mep": 1.05, "facade": 1.06},
    "hotel": {"cost": 1.12, "duration": 1.06, "mep": 1.14, "facade": 1.04},
    "hospital": {"cost": 1.38, "duration": 1.18, "mep": 1.48, "facade": 1.08},
    "laboratory": {"cost": 1.46, "duration": 1.16, "mep": 1.52, "facade": 1.03},
    "data_center": {"cost": 1.52, "duration": 1.08, "mep": 1.78, "facade": 0.82},
    "education": {"cost": 0.96, "duration": 0.98, "mep": 0.96, "facade": 0.91},
}

_SITE_FACTORS: dict[str, dict[str, float]] = {
    "standard_urban": {"cost": 1.00, "duration": 1.00, "lead": 1.00},
    "suburban": {"cost": 0.96, "duration": 0.97, "lead": 0.94},
    "constrained_urban": {"cost": 1.08, "duration": 1.08, "lead": 1.10},
    "brownfield": {"cost": 1.14, "duration": 1.16, "lead": 1.08},
    "coastal": {"cost": 1.11, "duration": 1.12, "lead": 1.16},
    "remote": {"cost": 1.18, "duration": 1.15, "lead": 1.38},
    "dense_cbd": {"cost": 1.16, "duration": 1.18, "lead": 1.22},
}

_SCENARIO_FAMILY_BY_TYPE = {
    "mixed_use": "vertical_mixed_use_delivery",
    "residential": "multifamily_delivery",
    "office": "commercial_office_delivery",
    "hotel": "hospitality_delivery",
    "hospital": "healthcare_complex_delivery",
    "laboratory": "research_facility_delivery",
    "data_center": "mission_critical_delivery",
    "education": "institutional_delivery",
}

_BASE_GFA_M2 = 43_200.0


def _case_seed(base_seed: int, split_index: int, index: int) -> int:
    return base_seed * 1_000_003 + split_index * 100_003 + index * 97 + 31


def _range_for_storeys(split: DistributionSplit, rng: random.Random) -> int:
    if split in {DistributionSplit.TRAIN, DistributionSplit.IID_TEST}:
        return rng.randint(6, 24)
    if split == DistributionSplit.OOD:
        return rng.choice([rng.randint(2, 5), rng.randint(25, 42)])
    return rng.randint(14, 36)


def _profile(split: DistributionSplit, rng: random.Random, index: int) -> dict[str, Any]:
    project_type = _PROJECT_TYPES[split][index % len(_PROJECT_TYPES[split])]
    site_profile = _SITE_PROFILES[split][(index // len(_PROJECT_TYPES[split])) % len(_SITE_PROFILES[split])]
    storeys = _range_for_storeys(split, rng)
    floorplate_m2 = rng.randint(1_800, 5_600)
    gross_floor_area_m2 = storeys * floorplate_m2
    delivery_model = _DELIVERY_MODELS[index % len(_DELIVERY_MODELS)]
    market_index = round(rng.uniform(0.91, 1.16), 3)
    if split == DistributionSplit.ADVERSARIAL:
        market_index = round(rng.uniform(1.10, 1.32), 3)
    return {
        "project_type": project_type,
        "site_profile": site_profile,
        "storeys": storeys,
        "floorplate_m2": floorplate_m2,
        "gross_floor_area_m2": gross_floor_area_m2,
        "delivery_model": delivery_model,
        "market_index": market_index,
    }


def _critical_path_days(scenario: ProjectScenario) -> int:
    by_id = {work.work_package_id: work for work in scenario.spec.work_packages}
    memo: dict[str, int] = {}

    def finish(work_id: str) -> int:
        if work_id in memo:
            return memo[work_id]
        work = by_id[work_id]
        dependency_finish = max((finish(dep) for dep in work.dependencies), default=0)
        memo[work_id] = dependency_finish + work.duration_days
        return memo[work_id]

    return max((finish(work_id) for work_id in by_id), default=1)


def _parameterize_public_world(
    scenario: ProjectScenario,
    *,
    split: DistributionSplit,
    profile: dict[str, Any],
    rng: random.Random,
    opaque_token: str,
) -> ProjectScenario:
    scenario = deepcopy(scenario)
    spec = scenario.spec
    project_type = str(profile["project_type"])
    site_profile = str(profile["site_profile"])
    type_factor = _TYPE_FACTORS[project_type]
    site_factor = _SITE_FACTORS[site_profile]
    market_index = float(profile["market_index"])
    gross_floor_area_m2 = float(profile["gross_floor_area_m2"])

    scale = max(0.35, gross_floor_area_m2 / _BASE_GFA_M2)
    cost_scale = scale * type_factor["cost"] * site_factor["cost"] * market_index
    duration_scale = max(0.72, scale ** 0.28) * type_factor["duration"] * site_factor["duration"]
    resource_scale = max(0.42, scale ** 0.84)

    spec.world_id = f"construction-project-{opaque_token}"
    spec.project_id = f"PROJECT-{opaque_token.upper()}"
    spec.name = f"{int(profile['storeys'])}-storey {project_type.replace('_', ' ')} development"
    spec.metadata.update(
        {
            "project_type": project_type,
            "storeys": int(profile["storeys"]),
            "floorplate_m2": int(profile["floorplate_m2"]),
            "gross_floor_area_m2": int(profile["gross_floor_area_m2"]),
            "delivery_model": profile["delivery_model"],
            "site_profile": site_profile,
            "market_index": market_index,
            "procedural": True,
        }
    )

    mep_ids = {"mep_design", "mep_roughin", "commissioning"}
    facade_ids = {"envelope"}
    for work in spec.work_packages:
        package_factor = 1.0
        if work.work_package_id in mep_ids:
            package_factor *= type_factor["mep"]
        if work.work_package_id in facade_ids:
            package_factor *= type_factor["facade"]
        if work.phase in {ProjectPhase.DESIGN, ProjectPhase.PLANNING}:
            package_factor *= 0.82 + 0.18 * type_factor["duration"]
        work.direct_cost = round(work.direct_cost * cost_scale * package_factor, 2)
        work.duration_days = max(2, round(work.duration_days * duration_scale * package_factor ** 0.15))
        for resource_id, amount in list(work.required_resources.items()):
            resource_factor = resource_scale
            if resource_id == "mep_equipment":
                resource_factor *= type_factor["mep"]
            if resource_id == "facade_units":
                resource_factor *= type_factor["facade"]
            work.required_resources[resource_id] = round(max(1.0, amount * resource_factor), 2)

    for resource in spec.resources:
        resource.unit_cost = round(resource.unit_cost * market_index * site_factor["cost"], 2)
        if resource.procurement_lead_days:
            resource.procurement_lead_days = max(
                1,
                round(resource.procurement_lead_days * site_factor["lead"]),
            )
        if resource.resource_id == "site_labor":
            resource.initial_available = max(
                60,
                round(resource.initial_available * max(0.85, scale ** 0.22)),
            )

    for decision in spec.decisions:
        for option in decision.options:
            for work_id, delta in list(option.cost_delta_by_work_package.items()):
                option.cost_delta_by_work_package[work_id] = round(delta * cost_scale, 2)
            for work_id, delta in list(option.duration_delta_by_work_package.items()):
                sign = -1 if delta < 0 else 1
                option.duration_delta_by_work_package[work_id] = sign * max(
                    1,
                    round(abs(delta) * duration_scale),
                )
            for work_id, resources in option.resource_requirements_by_work_package.items():
                for resource_id, amount in list(resources.items()):
                    resources[resource_id] = round(max(1.0, amount * resource_scale), 2)

    base_direct = sum(work.direct_cost for work in spec.work_packages)
    procurement_value = 0.0
    resource_by_id = {resource.resource_id: resource for resource in spec.resources}
    for work in spec.work_packages:
        for resource_id, quantity in work.required_resources.items():
            resource = resource_by_id[resource_id]
            if resource.consumable:
                procurement_value += resource.unit_cost * quantity

    contingency = {
        DistributionSplit.TRAIN: 1.23,
        DistributionSplit.IID_TEST: 1.20,
        DistributionSplit.OOD: 1.18,
        DistributionSplit.ADVERSARIAL: 1.10,
    }[split]
    spec.budget = round((base_direct + procurement_value) * contingency, 2)

    critical_path = _critical_path_days(scenario)
    schedule_buffer = {
        DistributionSplit.TRAIN: 1.30,
        DistributionSplit.IID_TEST: 1.26,
        DistributionSplit.OOD: 1.20,
        DistributionSplit.ADVERSARIAL: 1.10,
    }[split]
    spec.deadline_days = max(90, round(critical_path * schedule_buffer))

    return ProjectScenario.model_validate(scenario.model_dump(mode="python"))


def _parameterize_private_oracle(
    scenario: ProjectScenario,
    *,
    split: DistributionSplit,
    profile: dict[str, Any],
    rng: random.Random,
    opaque_token: str,
) -> ProjectScenario:
    scenario = deepcopy(scenario)
    oracle = scenario.oracle
    site_profile = str(profile["site_profile"])
    site_factor = _SITE_FACTORS[site_profile]

    permit_delay = max(1, round(rng.randint(3, 12) * site_factor["duration"]))
    oracle.work_package_delay_days = {"permit_release": permit_delay}
    if split in {DistributionSplit.OOD, DistributionSplit.ADVERSARIAL}:
        delay_target = rng.choice(["foundations", "superstructure", "envelope", "mep_roughin"])
        oracle.work_package_delay_days[delay_target] = rng.randint(4, 16)
    if split == DistributionSplit.ADVERSARIAL:
        second_target = rng.choice(["design_coordination", "interiors", "commissioning"])
        oracle.work_package_delay_days[second_target] = rng.randint(5, 18)

    lead_target = rng.choice(["mep_equipment", "facade_units", "structural_steel", "rebar"])
    oracle.resource_delay_days = {
        lead_target: max(2, round(rng.randint(5, 18) * site_factor["lead"]))
    }
    if split == DistributionSplit.ADVERSARIAL:
        second_resource = rng.choice(
            [resource for resource in ("mep_equipment", "facade_units", "structural_steel", "concrete") if resource != lead_target]
        )
        oracle.resource_delay_days[second_resource] = rng.randint(8, 28)

    inspected_targets = [
        work.work_package_id
        for work in scenario.spec.work_packages
        if work.requires_inspection
    ]
    defect_count = 1
    if split == DistributionSplit.OOD:
        defect_count = 2
    elif split == DistributionSplit.ADVERSARIAL:
        defect_count = 3
    defect_targets = rng.sample(inspected_targets, k=min(defect_count, len(inspected_targets)))
    oracle.latent_defects = {}
    for position, target in enumerate(defect_targets):
        severity = round(min(0.98, rng.uniform(0.45, 0.88) + (0.08 if split == DistributionSplit.ADVERSARIAL else 0.0)), 3)
        oracle.latent_defects[target] = HiddenDefect(
            issue_id=f"NCR-{opaque_token.upper()}-{position + 1:02d}",
            description="Latent quality defect requires verified rework before acceptance.",
            severity=severity,
            rework_cost=round(rng.uniform(75_000, 360_000) * _TYPE_FACTORS[str(profile["project_type"])]["cost"], 2),
            rework_days=rng.randint(3, 12 if split != DistributionSplit.ADVERSARIAL else 18),
        )

    oracle.metadata = {
        "private_ground_truth": True,
        "compound_disruption": split == DistributionSplit.ADVERSARIAL,
    }
    return ProjectScenario.model_validate(scenario.model_dump(mode="python"))


def _dependency_depth(scenario: ProjectScenario) -> int:
    by_id = {work.work_package_id: work for work in scenario.spec.work_packages}
    memo: dict[str, int] = {}

    def depth(work_id: str) -> int:
        if work_id in memo:
            return memo[work_id]
        dependencies = by_id[work_id].dependencies
        memo[work_id] = 1 + max((depth(dep) for dep in dependencies), default=0)
        return memo[work_id]

    return max((depth(work_id) for work_id in by_id), default=1)


def _difficulty(scenario: ProjectScenario, split: DistributionSplit) -> DifficultyVector:
    spec = scenario.spec
    hidden_disruptions = (
        len(scenario.oracle.work_package_delay_days)
        + len(scenario.oracle.resource_delay_days)
        + len(scenario.oracle.latent_defects)
    )
    adversarial_pressure = {
        DistributionSplit.TRAIN: 0.0,
        DistributionSplit.IID_TEST: 0.05,
        DistributionSplit.OOD: 0.35,
        DistributionSplit.ADVERSARIAL: 0.90,
    }[split]
    return DifficultyVector(
        entities=len(spec.work_packages) + len(spec.resources) + len(spec.roles) + len(spec.decisions),
        tools=7,
        steps=len(spec.work_packages) + len(spec.decisions) + hidden_disruptions,
        distractors=0,
        missing_probability=0.0,
        conflict_probability=0.0,
        dependency_depth=_dependency_depth(scenario),
        budget_ratio=round(spec.budget / max(1.0, sum(work.direct_cost for work in spec.work_packages)), 3),
        stochasticity=0.0,
        adversarial_pressure=adversarial_pressure,
    )


def iter_project_distribution(
    config: ProjectDistributionConfig | None = None,
) -> Iterator[ProjectDistributionCase]:
    config = config or ProjectDistributionConfig()
    for split_index, split in enumerate(DistributionSplit):
        for index in range(config.split_count(split)):
            seed = _case_seed(config.seed, split_index, index)
            rng = random.Random(seed)
            profile = _profile(split, rng, index)
            opaque_token = stable_hash(
                {
                    "distribution": config.version,
                    "seed": seed,
                    "index": index,
                    "split": split.value,
                }
            )[:16]
            scenario = build_construction_project_world(seed=seed)
            scenario = _parameterize_public_world(
                scenario,
                split=split,
                profile=profile,
                rng=rng,
                opaque_token=opaque_token,
            )
            scenario = _parameterize_private_oracle(
                scenario,
                split=split,
                profile=profile,
                rng=rng,
                opaque_token=opaque_token,
            )
            scenario.spec.metadata["distribution_version"] = config.version
            yield ProjectDistributionCase(
                split=split,
                seed=seed,
                scenario_family=_SCENARIO_FAMILY_BY_TYPE[str(profile["project_type"])],
                surface_profile=_SURFACE_PROFILES[split][index % len(_SURFACE_PROFILES[split])],
                difficulty=_difficulty(scenario, split),
                scenario=scenario,
            )


def compile_project_distribution(
    config: ProjectDistributionConfig | None = None,
) -> list[ProjectDistributionCase]:
    return list(iter_project_distribution(config))


def _public_cases(cases: list[ProjectDistributionCase]) -> list[dict[str, Any]]:
    return [case.scenario.public_payload() for case in cases]


def _private_cases(cases: list[ProjectDistributionCase]) -> list[dict[str, Any]]:
    return [
        {
            "split": case.split.value,
            "seed": case.seed,
            "scenario_family": case.scenario_family,
            "surface_profile": case.surface_profile,
            "difficulty": case.difficulty.model_dump(mode="json"),
            "scenario": case.scenario.model_dump(mode="json"),
        }
        for case in cases
    ]


def project_distribution_manifest(
    cases: list[ProjectDistributionCase],
    *,
    config: ProjectDistributionConfig,
    public: bool = False,
) -> ProjectDistributionManifest:
    public_cases = _public_cases(cases)
    private_cases = _private_cases(cases)
    split_counts = Counter(case.split.value for case in cases)
    project_type_counts = Counter(
        str(case.scenario.spec.metadata.get("project_type", "unknown")) for case in cases
    )
    return ProjectDistributionManifest(
        distribution_id=f"projectworld-construction-{stable_hash({'version': config.version, 'seed': config.seed})[:12]}",
        version=config.version,
        seed=None if public else config.seed,
        total_cases=len(cases),
        split_counts=dict(sorted(split_counts.items())),
        project_type_counts=dict(sorted(project_type_counts.items())),
        public_hash=stable_hash(public_cases),
        private_hash=None if public else stable_hash(private_cases),
        metadata={
            "environment_family": "operational_project_world",
            "domain": "construction",
            "long_horizon": True,
            "private_oracle_boundary": True,
            "split_identity_public": False,
            "generator_seed_public": False,
        },
    )


def public_project_distribution_payload(
    cases: list[ProjectDistributionCase],
    *,
    config: ProjectDistributionConfig,
) -> dict[str, Any]:
    manifest = project_distribution_manifest(cases, config=config, public=True)
    return {
        "manifest": manifest.model_dump(mode="json"),
        "scenarios": _public_cases(cases),
    }


def private_project_distribution_payload(
    cases: list[ProjectDistributionCase],
    *,
    config: ProjectDistributionConfig,
) -> dict[str, Any]:
    manifest = project_distribution_manifest(cases, config=config, public=False)
    return {
        "manifest": manifest.model_dump(mode="json"),
        "cases": _private_cases(cases),
    }


def validate_project_distribution(
    cases: list[ProjectDistributionCase],
    *,
    config: ProjectDistributionConfig,
) -> dict[str, Any]:
    errors: list[str] = []
    if len(cases) != config.total_cases:
        errors.append(f"expected {config.total_cases} cases, found {len(cases)}")

    world_ids = [case.scenario.spec.world_id for case in cases]
    project_ids = [case.scenario.spec.project_id for case in cases]
    if len(world_ids) != len(set(world_ids)):
        errors.append("world IDs are not unique")
    if len(project_ids) != len(set(project_ids)):
        errors.append("project IDs are not unique")

    counts = Counter(case.split for case in cases)
    for split in DistributionSplit:
        if counts[split] != config.split_count(split):
            errors.append(
                f"split {split.value} expected {config.split_count(split)}, found {counts[split]}"
            )

    public_text = json.dumps(
        public_project_distribution_payload(cases, config=config),
        sort_keys=True,
    )
    for forbidden in (
        '"oracle"',
        '"split"',
        '"scenario_family"',
        '"surface_profile"',
        '"compound_disruption"',
        '"private_ground_truth"',
    ):
        if forbidden in public_text:
            errors.append(f"public payload leaks evaluator field {forbidden}")

    train_types = {
        str(case.scenario.spec.metadata["project_type"])
        for case in cases
        if case.split == DistributionSplit.TRAIN
    }
    ood_types = {
        str(case.scenario.spec.metadata["project_type"])
        for case in cases
        if case.split == DistributionSplit.OOD
    }
    if not (ood_types - train_types):
        errors.append("OOD split does not contain held-out project archetypes")

    for case in cases:
        if case.scenario.spec.budget <= 0 or case.scenario.spec.deadline_days <= 0:
            errors.append(f"invalid budget/deadline: {case.scenario.spec.world_id}")
        if case.split == DistributionSplit.ADVERSARIAL:
            hidden_disruptions = (
                len(case.scenario.oracle.work_package_delay_days)
                + len(case.scenario.oracle.resource_delay_days)
                + len(case.scenario.oracle.latent_defects)
            )
            if hidden_disruptions < 6:
                errors.append(
                    f"adversarial case lacks compound disruption: {case.scenario.spec.world_id}"
                )

    return {
        "valid": not errors,
        "errors": errors,
        "total_cases": len(cases),
        "split_counts": {split.value: counts[split] for split in DistributionSplit},
    }


def write_project_distribution_bundle(
    *,
    output: str | Path,
    oracle_output: str | Path,
    config: ProjectDistributionConfig | None = None,
) -> dict[str, Any]:
    config = config or ProjectDistributionConfig()
    cases = compile_project_distribution(config)
    validation = validate_project_distribution(cases, config=config)
    if not validation["valid"]:
        raise ValueError(f"invalid project distribution: {validation['errors']}")

    public_payload = public_project_distribution_payload(cases, config=config)
    private_payload = private_project_distribution_payload(cases, config=config)
    output_path = Path(output)
    oracle_path = Path(oracle_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    oracle_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(public_payload, indent=2, sort_keys=True), encoding="utf-8")
    oracle_path.write_text(json.dumps(private_payload, indent=2, sort_keys=True), encoding="utf-8")
    return {
        "public_path": str(output_path),
        "oracle_path": str(oracle_path),
        "validation": validation,
        "manifest": private_payload["manifest"],
    }
