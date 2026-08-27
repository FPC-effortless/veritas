from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.operational_world.models import (
    CalibrationProfile,
    CompanySizeBand,
    IndustryFamily,
    OperationalWorldSpec,
    RegionGroup,
    ScenarioKind,
)
from investigation_world.operational_world.production import OperationalWorldCompiler


PackSplit = Literal["train", "dev", "public_eval", "private_eval", "ood_eval"]


class InvestigationPackSpec(BaseModel):
    """Deterministic distribution specification for one investigation capability pack."""

    model_config = ConfigDict(extra="forbid")

    pack_id: str = "veritas-investigation-procurement-v1"
    seed_start: int = 10_000
    world_count: int = Field(default=100, ge=20, le=100_000)
    region: RegionGroup = RegionGroup.GLOBAL
    country_code: str | None = None
    industry: IndustryFamily = IndustryFamily.GENERIC
    size_band: CompanySizeBand = CompanySizeBand.MEDIUM
    simulation_days: int = Field(default=120, ge=7, le=3650)
    train_scenarios: list[ScenarioKind] = Field(
        default_factory=lambda: [
            ScenarioKind.DUPLICATE_INVOICE,
            ScenarioKind.APPROVAL_BYPASS,
            ScenarioKind.PHANTOM_RECEIPT,
        ]
    )
    ood_scenarios: list[ScenarioKind] = Field(
        default_factory=lambda: [
            ScenarioKind.SHELL_VENDOR_CONFLICT,
            ScenarioKind.SPLIT_PURCHASE_ORDERS,
        ]
    )
    split_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "train": 0.60,
            "dev": 0.10,
            "public_eval": 0.10,
            "private_eval": 0.10,
            "ood_eval": 0.10,
        }
    )
    tool_budget: float = Field(default=80.0, gt=0)
    metadata: dict[str, object] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_distribution(self) -> "InvestigationPackSpec":
        expected = {"train", "dev", "public_eval", "private_eval", "ood_eval"}
        if set(self.split_weights) != expected:
            raise ValueError(f"split_weights must define exactly {sorted(expected)}")
        if any(value < 0 for value in self.split_weights.values()):
            raise ValueError("split weights cannot be negative")
        total = sum(self.split_weights.values())
        if abs(total - 1.0) > 1e-9:
            raise ValueError("split weights must sum to 1")
        if not self.train_scenarios:
            raise ValueError("train_scenarios cannot be empty")
        if not self.ood_scenarios:
            raise ValueError("ood_scenarios cannot be empty")
        if set(self.train_scenarios) & set(self.ood_scenarios):
            raise ValueError("OOD scenarios must be disjoint from training scenarios")
        return self


class PackDifficulty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_count: int
    system_count: int
    evidence_density: float
    scenario_complexity: int
    score: float


class PackEpisodeMetadata(BaseModel):
    """Private distribution metadata. Scenario labels never enter public pack payloads."""

    model_config = ConfigDict(extra="forbid")

    episode_id: str
    world_id: str
    seed: int
    split: PackSplit
    scenario_type: ScenarioKind
    difficulty: PackDifficulty


class InvestigationCapabilityPack(BaseModel):
    model_config = ConfigDict(extra="forbid", arbitrary_types_allowed=True)

    spec: InvestigationPackSpec
    calibration_profile_id: str | None = None
    public_episodes: dict[str, list[dict]] = Field(default_factory=dict)
    private_oracles: dict[str, list[dict]] = Field(default_factory=dict)
    private_metadata: list[PackEpisodeMetadata] = Field(default_factory=list)

    def public_manifest(self) -> dict:
        split_counts = {split: len(items) for split, items in self.public_episodes.items()}
        return {
            "format": "veritas-investigation-capability-pack-public-v1",
            "pack_id": self.spec.pack_id,
            "world_count": sum(split_counts.values()),
            "splits": split_counts,
            "capability": "operational_procurement_investigation",
            "region": self.spec.region,
            "industry": self.spec.industry,
            "size_band": self.spec.size_band,
            "calibration_profile_id": self.calibration_profile_id,
            "seed_grouped_split": True,
            "ood_definition": "held-out scenario families with disjoint world seeds",
            "metadata": self.spec.metadata,
        }

    def private_manifest(self) -> dict:
        return {
            "format": "veritas-investigation-capability-pack-private-v1",
            "pack_id": self.spec.pack_id,
            "episodes": [item.model_dump(mode="json") for item in self.private_metadata],
        }

    def write(self, root: str | Path) -> dict[str, str]:
        root_path = Path(root)
        root_path.mkdir(parents=True, exist_ok=True)
        written: dict[str, str] = {}

        public_manifest = root_path / "manifest.public.json"
        public_manifest.write_text(json.dumps(self.public_manifest(), indent=2, default=str))
        written["public_manifest"] = str(public_manifest)

        private_manifest = root_path / "manifest.private.json"
        private_manifest.write_text(json.dumps(self.private_manifest(), indent=2, default=str))
        written["private_manifest"] = str(private_manifest)

        for split, episodes in self.public_episodes.items():
            path = root_path / f"{split}.public.json"
            path.write_text(
                json.dumps(
                    {
                        "format": "veritas-investigation-episodes-public-v1",
                        "pack_id": self.spec.pack_id,
                        "split": split,
                        "episodes": episodes,
                    },
                    indent=2,
                    default=str,
                )
            )
            written[f"{split}_public"] = str(path)

        for split, oracles in self.private_oracles.items():
            path = root_path / f"{split}.oracles.json"
            path.write_text(
                json.dumps(
                    {
                        "format": "veritas-investigation-oracles-private-v1",
                        "pack_id": self.spec.pack_id,
                        "split": split,
                        "oracles": oracles,
                    },
                    indent=2,
                    default=str,
                )
            )
            written[f"{split}_oracles"] = str(path)
        return written


def _stable_seed_rank(pack_id: str, seed: int) -> int:
    digest = hashlib.sha256(f"{pack_id}:{seed}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _allocate_counts(total: int, weights: dict[str, float]) -> dict[str, int]:
    raw = {split: total * weight for split, weight in weights.items()}
    counts = {split: int(value) for split, value in raw.items()}
    remainder = total - sum(counts.values())
    order = sorted(
        weights,
        key=lambda split: (raw[split] - counts[split], split),
        reverse=True,
    )
    for split in order[:remainder]:
        counts[split] += 1
    return counts


def _difficulty(episode_records: list[dict], scenario: ScenarioKind) -> PackDifficulty:
    systems = {str(record.get("system")) for record in episode_records}
    related = sum(len(record.get("related_object_ids") or []) for record in episode_records)
    evidence_density = related / max(1, len(episode_records))
    complexity = {
        ScenarioKind.DUPLICATE_INVOICE: 2,
        ScenarioKind.APPROVAL_BYPASS: 2,
        ScenarioKind.PHANTOM_RECEIPT: 3,
        ScenarioKind.SHELL_VENDOR_CONFLICT: 4,
        ScenarioKind.SPLIT_PURCHASE_ORDERS: 4,
    }[scenario]
    # Log-free monotone score so it is deterministic and easy to audit.
    volume_term = min(5.0, len(episode_records) / 250.0)
    system_term = min(2.0, len(systems) / 4.0)
    density_term = min(1.0, evidence_density / 4.0)
    score = round(min(10.0, complexity + volume_term + system_term + density_term), 4)
    return PackDifficulty(
        record_count=len(episode_records),
        system_count=len(systems),
        evidence_density=round(evidence_density, 6),
        scenario_complexity=complexity,
        score=score,
    )


class InvestigationCapabilityPackBuilder:
    """Compile disjoint world seeds into a leakage-safe investigation benchmark/training pack."""

    def __init__(self, calibration: CalibrationProfile | None = None) -> None:
        self.calibration = calibration

    def build(self, spec: InvestigationPackSpec) -> InvestigationCapabilityPack:
        seeds = list(range(spec.seed_start, spec.seed_start + spec.world_count))
        seeds.sort(key=lambda seed: (_stable_seed_rank(spec.pack_id, seed), seed))
        counts = _allocate_counts(spec.world_count, spec.split_weights)

        split_seeds: dict[str, list[int]] = defaultdict(list)
        cursor = 0
        for split in ("train", "dev", "public_eval", "private_eval", "ood_eval"):
            count = counts[split]
            split_seeds[split] = seeds[cursor : cursor + count]
            cursor += count

        compiler = OperationalWorldCompiler(calibration=self.calibration)
        public: dict[str, list[dict]] = defaultdict(list)
        oracles: dict[str, list[dict]] = defaultdict(list)
        metadata: list[PackEpisodeMetadata] = []

        for split in ("train", "dev", "public_eval", "private_eval", "ood_eval"):
            scenario_pool = spec.ood_scenarios if split == "ood_eval" else spec.train_scenarios
            for index, seed in enumerate(split_seeds[split]):
                scenario = scenario_pool[index % len(scenario_pool)]
                world_spec = OperationalWorldSpec(
                    seed=seed,
                    region=spec.region,
                    country_code=spec.country_code,
                    industry=spec.industry,
                    size_band=spec.size_band,
                    simulation_days=spec.simulation_days,
                    scenario_types=[scenario],
                    metadata={"capability_pack_id": spec.pack_id},
                )
                _, episode = compiler.compile_investigation_episode(
                    world_spec,
                    budget=spec.tool_budget,
                )
                public_payload = episode.public_payload()
                # Pack-level split and difficulty are safe; scenario identity is intentionally not.
                public_payload.setdefault("metadata", {})["split"] = split
                difficulty = _difficulty(public_payload["records"], scenario)
                public_payload["metadata"]["difficulty_score"] = difficulty.score
                public[split].append(public_payload)
                oracles[split].append(
                    {
                        "episode_id": episode.episode_id,
                        "world_id": episode.world_id,
                        "oracle": episode.oracle.model_dump(mode="json"),
                    }
                )
                metadata.append(
                    PackEpisodeMetadata(
                        episode_id=episode.episode_id,
                        world_id=episode.world_id,
                        seed=seed,
                        split=split,
                        scenario_type=scenario,
                        difficulty=difficulty,
                    )
                )

        self._validate_pack(spec, public, oracles, metadata)
        return InvestigationCapabilityPack(
            spec=spec,
            calibration_profile_id=self.calibration.profile_id if self.calibration else None,
            public_episodes=dict(public),
            private_oracles=dict(oracles),
            private_metadata=metadata,
        )

    @staticmethod
    def _validate_pack(
        spec: InvestigationPackSpec,
        public: dict[str, list[dict]],
        oracles: dict[str, list[dict]],
        metadata: list[PackEpisodeMetadata],
    ) -> None:
        if sum(len(items) for items in public.values()) != spec.world_count:
            raise ValueError("compiled pack world count does not match specification")

        seeds_by_split: dict[str, set[int]] = defaultdict(set)
        for item in metadata:
            seeds_by_split[item.split].add(item.seed)
        split_names = list(seeds_by_split)
        for index, left in enumerate(split_names):
            for right in split_names[index + 1 :]:
                overlap = seeds_by_split[left] & seeds_by_split[right]
                if overlap:
                    raise ValueError(f"world seed leakage between {left} and {right}: {overlap}")

        train_types = {
            item.scenario_type for item in metadata if item.split != "ood_eval"
        }
        ood_types = {item.scenario_type for item in metadata if item.split == "ood_eval"}
        if train_types & ood_types:
            raise ValueError("OOD scenario leakage into in-distribution splits")

        forbidden = ("scenario_type", "hidden_cause", "hidden_error_id", "expected_resolution")
        for split, episodes in public.items():
            for episode in episodes:
                serialized = json.dumps(episode, sort_keys=True).casefold()
                for field in forbidden:
                    if field.casefold() in serialized:
                        raise ValueError(f"private field leaked into {split} public payload: {field}")

        for split, public_items in public.items():
            oracle_items = oracles.get(split, [])
            if len(public_items) != len(oracle_items):
                raise ValueError(f"public/oracle count mismatch for {split}")
            public_ids = {item["episode_id"] for item in public_items}
            oracle_ids = {item["episode_id"] for item in oracle_items}
            if public_ids != oracle_ids:
                raise ValueError(f"public/oracle episode IDs mismatch for {split}")


def pack_distribution_summary(pack: InvestigationCapabilityPack) -> dict:
    scenario_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    difficulty_by_split: dict[str, list[float]] = defaultdict(list)
    for item in pack.private_metadata:
        scenario_by_split[item.split][item.scenario_type.value] += 1
        difficulty_by_split[item.split].append(item.difficulty.score)
    return {
        "pack_id": pack.spec.pack_id,
        "splits": {
            split: {
                "episodes": len(pack.public_episodes.get(split, [])),
                "scenarios_private": dict(sorted(scenario_by_split[split].items())),
                "difficulty_min": min(difficulty_by_split[split], default=None),
                "difficulty_max": max(difficulty_by_split[split], default=None),
            }
            for split in pack.public_episodes
        },
    }
