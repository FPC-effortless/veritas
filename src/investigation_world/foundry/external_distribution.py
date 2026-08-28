from __future__ import annotations

import json
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, model_validator

from investigation_world.core.models import CanonicalWorld
from investigation_world.evidence.projector import project
from investigation_world.foundry.distributions import (
    FoundryDistributionManifest,
    manifest_from_tasks,
)
from investigation_world.foundry.external_investigation import (
    external_investigation_task_metadata,
)
from investigation_world.foundry.external_runtime import ExternalInvestigationEpisode
from investigation_world.foundry.models import (
    DistributionSplit,
    FoundryTaskMetadata,
    stable_hash,
)
from investigation_world.foundry.world_calibration import (
    WorldCalibrationSpec,
    calibration_fingerprint,
)
from investigation_world.tasks.spec import TaskOracle, TaskSpec, generate_task_bundle
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig


class CalibrationParameter(StrEnum):
    NUM_PEOPLE = "num_people"
    NUM_ORGANIZATIONS = "num_organizations"
    NUM_ADDRESSES = "num_addresses"
    RELATIONSHIP_DENSITY = "relationship_density"
    ALIAS_RATE = "alias_rate"
    RENAME_RATE = "rename_rate"
    OWNERSHIP_CHAIN_DEPTH = "ownership_chain_depth"
    OMISSION_PROBABILITY = "omission_probability"
    STALE_PROBABILITY = "stale_probability"


class CalibrationBinding(BaseModel):
    target_id: str
    parameter: CalibrationParameter
    scale: float = 1.0
    offset: float = 0.0
    minimum: float | None = None
    maximum: float | None = None


class ExternalInvestigationWorldSpec(BaseModel):
    split: DistributionSplit
    world_seed: int
    evidence_seed: int
    task_seed: int
    public_world_id: str | None = None
    task_count: int = Field(default=48, ge=1)
    config: WorldGenerationConfig = Field(default_factory=WorldGenerationConfig)
    omission_probability: float = Field(default=0.08, ge=0.0, le=1.0)
    stale_probability: float = Field(default=0.12, ge=0.0, le=1.0)
    calibration_scale: float = Field(default=1.0, gt=0.0)
    total_cost: int = Field(default=40, ge=1)
    max_tool_calls: int = Field(default=30, ge=1)


class ExternalInvestigationBuildPlan(BaseModel):
    version: str = "1"
    distribution_id: str = Field(
        default="external-investigation-dev-v1",
        min_length=1,
    )
    taskset_version: str = "external-investigation-v1"
    runtime_version: str = "external-investigation-runtime-v1"
    harness_version: str = "unspecified"
    worlds: list[ExternalInvestigationWorldSpec]
    calibration_spec: WorldCalibrationSpec | None = None
    calibration_bindings: list[CalibrationBinding] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_disjoint(self):
        splits = [world.split for world in self.worlds]
        if len(splits) != len(set(splits)):
            raise ValueError("external investigation build plan requires unique splits")
        for name, values in {
            "world_seed": [world.world_seed for world in self.worlds],
            "evidence_seed": [world.evidence_seed for world in self.worlds],
            "task_seed": [world.task_seed for world in self.worlds],
        }.items():
            if len(values) != len(set(values)):
                raise ValueError(f"external investigation {name} values must be disjoint")
        explicit_public_ids = [
            world.public_world_id
            for world in self.worlds
            if world.public_world_id is not None
        ]
        if len(explicit_public_ids) != len(set(explicit_public_ids)):
            raise ValueError("external investigation public_world_id values must be unique")
        if self.calibration_bindings and self.calibration_spec is None:
            raise ValueError("calibration bindings require calibration_spec")
        if self.calibration_spec is not None:
            target_ids = {
                target.target_id for target in self.calibration_spec.distribution_targets
            }
            missing = {
                binding.target_id
                for binding in self.calibration_bindings
                if binding.target_id not in target_ids
            }
            if missing:
                raise ValueError(
                    f"calibration bindings reference unknown targets: {sorted(missing)}"
                )
        return self


class ExternalWorldSummary(BaseModel):
    split: DistributionSplit
    world_id: str
    world_seed: int
    evidence_seed: int
    task_seed: int
    task_count: int
    config: dict[str, Any]
    omission_probability: float
    stale_probability: float
    calibration_fingerprint: str | None = None

    def public_payload(self) -> dict[str, Any]:
        """Operator-safe summary with all replayable seed material removed."""
        return {
            "split": self.split.value,
            "world_id": self.world_id,
            "task_count": self.task_count,
            "config": self.config,
            "omission_probability": self.omission_probability,
            "stale_probability": self.stale_probability,
            "calibration_fingerprint": self.calibration_fingerprint,
        }


def _public_manifest_payload(
    manifest: FoundryDistributionManifest,
) -> dict[str, Any]:
    """Return a split manifest that cannot act as a commitment oracle for secret seeds."""
    partitions = [
        {
            "split": partition.split.value,
            "task_ids": list(partition.task_ids),
        }
        for partition in manifest.partitions
    ]
    public_id = "EFM-" + stable_hash(
        {
            "version": manifest.version,
            "partitions": partitions,
        }
    )[:16].upper()
    return {
        "manifest_id": public_id,
        "version": manifest.version,
        "partitions": partitions,
    }


class ExternalInvestigationDistribution(BaseModel):
    """Materialized private distribution plus a seed-safe public split manifest."""

    manifest: FoundryDistributionManifest
    episodes: list[ExternalInvestigationEpisode]
    world_summaries: list[ExternalWorldSummary]
    plan_hash: str

    def public_payload(self) -> dict[str, Any]:
        payload = {
            "format": "veritas-external-investigation-public-v1",
            "manifest": _public_manifest_payload(self.manifest),
            "worlds": [summary.public_payload() for summary in self.world_summaries],
            "episode_count": len(self.episodes),
        }
        payload["public_manifest_hash"] = stable_hash(payload)
        return payload

    def private_payload(self) -> dict[str, Any]:
        worlds: dict[str, dict[str, Any]] = {}
        private_episodes: list[dict[str, Any]] = []
        for episode in self.episodes:
            worlds.setdefault(
                episode.world.world_id,
                episode.world.model_dump(mode="json"),
            )
            private_episodes.append(
                {
                    "world_id": episode.world.world_id,
                    "task": episode.task.model_dump(mode="json"),
                    "oracle": episode.oracle.model_dump(mode="json"),
                    "metadata": episode.metadata.model_dump(mode="json"),
                    "total_cost": episode.total_cost,
                    "max_tool_calls": episode.max_tool_calls,
                }
            )
        return {
            "format": "veritas-external-investigation-private-v1",
            "manifest": self.manifest.model_dump(mode="json"),
            "world_summaries": [
                summary.model_dump(mode="json") for summary in self.world_summaries
            ],
            "plan_hash": self.plan_hash,
            "worlds": worlds,
            "episodes": private_episodes,
        }


_INTEGER_PARAMETERS = {
    CalibrationParameter.NUM_PEOPLE,
    CalibrationParameter.NUM_ORGANIZATIONS,
    CalibrationParameter.NUM_ADDRESSES,
    CalibrationParameter.OWNERSHIP_CHAIN_DEPTH,
}
_PROBABILITY_PARAMETERS = {
    CalibrationParameter.RELATIONSHIP_DENSITY,
    CalibrationParameter.ALIAS_RATE,
    CalibrationParameter.RENAME_RATE,
    CalibrationParameter.OMISSION_PROBABILITY,
    CalibrationParameter.STALE_PROBABILITY,
}


def _target_numeric_value(spec: WorldCalibrationSpec, target_id: str) -> float:
    target = next(
        (
            item
            for item in spec.distribution_targets
            if item.target_id == target_id
        ),
        None,
    )
    if target is None:
        raise KeyError(target_id)
    value = target.expected_value
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(
            f"calibration target {target_id} is not numeric and cannot parameterize a world"
        )
    return float(value)


def _bound_value(
    value: float,
    binding: CalibrationBinding,
    *,
    world_scale: float,
) -> float:
    result = value * binding.scale * world_scale + binding.offset
    if binding.minimum is not None:
        result = max(result, binding.minimum)
    if binding.maximum is not None:
        result = min(result, binding.maximum)
    if binding.parameter in _PROBABILITY_PARAMETERS:
        result = max(0.0, min(1.0, result))
    return result


def resolve_external_world_spec(
    world_spec: ExternalInvestigationWorldSpec,
    *,
    calibration_spec: WorldCalibrationSpec | None = None,
    bindings: list[CalibrationBinding] | None = None,
) -> ExternalInvestigationWorldSpec:
    if calibration_spec is None or not bindings:
        return world_spec.model_copy(deep=True)

    config = world_spec.config.model_dump()
    omission_probability = world_spec.omission_probability
    stale_probability = world_spec.stale_probability

    for binding in bindings:
        value = _bound_value(
            _target_numeric_value(calibration_spec, binding.target_id),
            binding,
            world_scale=world_spec.calibration_scale,
        )
        if binding.parameter in _INTEGER_PARAMETERS:
            resolved: int | float = max(1, int(round(value)))
        else:
            resolved = float(value)
        if binding.parameter == CalibrationParameter.OMISSION_PROBABILITY:
            omission_probability = float(resolved)
        elif binding.parameter == CalibrationParameter.STALE_PROBABILITY:
            stale_probability = float(resolved)
        else:
            config[binding.parameter.value] = resolved

    return world_spec.model_copy(
        update={
            "config": WorldGenerationConfig.model_validate(config),
            "omission_probability": omission_probability,
            "stale_probability": stale_probability,
        },
        deep=True,
    )


def default_external_investigation_build_plan(
    *,
    calibration_spec: WorldCalibrationSpec | None = None,
    calibration_bindings: list[CalibrationBinding] | None = None,
    tasks_per_split: int = 48,
) -> ExternalInvestigationBuildPlan:
    """Return a reproducible development plan.

    The checked-in seeds are intentionally public and are therefore unsuitable for a
    private commercial evaluation. Private benchmark plans must supply fresh secret seeds
    outside the repository. Public artifacts never serialize those secret seed values.
    """
    return ExternalInvestigationBuildPlan(
        distribution_id="external-investigation-dev-v1",
        calibration_spec=calibration_spec,
        calibration_bindings=calibration_bindings or [],
        worlds=[
            ExternalInvestigationWorldSpec(
                split=DistributionSplit.TRAIN,
                world_seed=31001,
                evidence_seed=41001,
                task_seed=51001,
                task_count=tasks_per_split,
            ),
            ExternalInvestigationWorldSpec(
                split=DistributionSplit.IID_TEST,
                world_seed=31002,
                evidence_seed=41002,
                task_seed=51002,
                task_count=tasks_per_split,
            ),
            ExternalInvestigationWorldSpec(
                split=DistributionSplit.OOD,
                world_seed=31101,
                evidence_seed=41101,
                task_seed=51101,
                task_count=tasks_per_split,
                config=WorldGenerationConfig(
                    num_people=180,
                    num_organizations=90,
                    num_addresses=70,
                    relationship_density=0.18,
                    alias_rate=0.55,
                    rename_rate=0.35,
                    ownership_chain_depth=5,
                ),
                omission_probability=0.12,
                stale_probability=0.20,
                calibration_scale=1.35,
            ),
            ExternalInvestigationWorldSpec(
                split=DistributionSplit.ADVERSARIAL,
                world_seed=31201,
                evidence_seed=41201,
                task_seed=51201,
                task_count=tasks_per_split,
                config=WorldGenerationConfig(
                    num_people=130,
                    num_organizations=70,
                    num_addresses=55,
                    relationship_density=0.16,
                    alias_rate=0.60,
                    rename_rate=0.45,
                    ownership_chain_depth=4,
                ),
                omission_probability=0.25,
                stale_probability=0.35,
                calibration_scale=1.15,
                total_cost=32,
                max_tool_calls=24,
            ),
        ],
    )


def _opaque_world_id(
    plan: ExternalInvestigationBuildPlan,
    world_spec: ExternalInvestigationWorldSpec,
) -> str:
    if world_spec.public_world_id is not None:
        return world_spec.public_world_id
    payload = {
        "distribution_id": plan.distribution_id,
        "version": plan.version,
        "split": world_spec.split.value,
    }
    return "EXT-" + stable_hash(payload)[:16].upper()


def materialize_external_investigation_build_plan(
    plan: ExternalInvestigationBuildPlan,
) -> ExternalInvestigationDistribution:
    episodes: list[ExternalInvestigationEpisode] = []
    summaries: list[ExternalWorldSummary] = []
    all_metadata: list[FoundryTaskMetadata] = []
    calibration_hash = (
        calibration_fingerprint(plan.calibration_spec)
        if plan.calibration_spec is not None
        else None
    )

    for raw_spec in plan.worlds:
        world_spec = resolve_external_world_spec(
            raw_spec,
            calibration_spec=plan.calibration_spec,
            bindings=plan.calibration_bindings,
        )
        world = WorldFactory.generate(world_spec.world_seed, world_spec.config)
        # WorldFactory's development ID contains the generation seed. External Foundry
        # replaces it before evidence/task compilation with an opaque, non-seed-derived ID.
        world.world_id = _opaque_world_id(plan, world_spec)
        world, _ = project(
            world,
            seed=world_spec.evidence_seed,
            omission_probability=world_spec.omission_probability,
            stale_probability=world_spec.stale_probability,
        )
        task_bundle = generate_task_bundle(
            world,
            count=world_spec.task_count,
            seed=world_spec.task_seed,
        )
        for index, instance in enumerate(task_bundle):
            metadata = external_investigation_task_metadata(
                instance.public,
                split=world_spec.split,
                taskset_version=plan.taskset_version,
                harness_version=plan.harness_version,
                runtime_version=plan.runtime_version,
                seed=world_spec.task_seed * 1000 + index,
            )
            metadata = metadata.model_copy(
                update={
                    "generator_parameters": {
                        **metadata.generator_parameters,
                        "world_seed": world_spec.world_seed,
                        "evidence_seed": world_spec.evidence_seed,
                        "task_seed": world_spec.task_seed,
                        "omission_probability": world_spec.omission_probability,
                        "stale_probability": world_spec.stale_probability,
                        "calibration_fingerprint": calibration_hash,
                    }
                }
            )
            all_metadata.append(metadata)
            episodes.append(
                ExternalInvestigationEpisode(
                    world=world,
                    task=instance.public,
                    oracle=instance.oracle,
                    metadata=metadata,
                    total_cost=world_spec.total_cost,
                    max_tool_calls=world_spec.max_tool_calls,
                )
            )
        summaries.append(
            ExternalWorldSummary(
                split=world_spec.split,
                world_id=world.world_id,
                world_seed=world_spec.world_seed,
                evidence_seed=world_spec.evidence_seed,
                task_seed=world_spec.task_seed,
                task_count=len(task_bundle),
                config=world_spec.config.model_dump(mode="json"),
                omission_probability=world_spec.omission_probability,
                stale_probability=world_spec.stale_probability,
                calibration_fingerprint=calibration_hash,
            )
        )

    manifest = manifest_from_tasks(all_metadata, version=plan.version)
    return ExternalInvestigationDistribution(
        manifest=manifest,
        episodes=episodes,
        world_summaries=summaries,
        plan_hash=stable_hash(plan.model_dump(mode="json")),
    )


def write_external_investigation_distribution(
    distribution: ExternalInvestigationDistribution,
    public_output: str | Path,
    *,
    private_output: str | Path | None = None,
) -> dict[str, Any]:
    public_path = Path(public_output)
    public_path.parent.mkdir(parents=True, exist_ok=True)
    public_payload = distribution.public_payload()
    public_path.write_text(
        json.dumps(
            public_payload,
            indent=2,
            sort_keys=True,
            default=str,
        ),
        encoding="utf-8",
    )
    result = {
        "public_output": str(public_path),
        "episode_count": len(distribution.episodes),
        "manifest_id": public_payload["manifest"]["manifest_id"],
        "private_output": None,
    }
    if private_output is not None:
        private_path = Path(private_output)
        private_path.parent.mkdir(parents=True, exist_ok=True)
        private_path.write_text(
            json.dumps(
                distribution.private_payload(),
                indent=2,
                sort_keys=True,
                default=str,
            ),
            encoding="utf-8",
        )
        result["private_output"] = str(private_path)
    return result


def load_external_investigation_distribution(
    private_input: str | Path,
) -> ExternalInvestigationDistribution:
    payload = json.loads(Path(private_input).read_text(encoding="utf-8"))
    if payload.get("format") != "veritas-external-investigation-private-v1":
        raise ValueError("unsupported external investigation private bundle format")
    worlds = {
        world_id: CanonicalWorld.model_validate(world_payload)
        for world_id, world_payload in payload.get("worlds", {}).items()
    }
    episodes: list[ExternalInvestigationEpisode] = []
    for item in payload.get("episodes", []):
        world_id = str(item["world_id"])
        if world_id not in worlds:
            raise ValueError(f"episode references unavailable world {world_id}")
        episodes.append(
            ExternalInvestigationEpisode(
                world=worlds[world_id],
                task=TaskSpec.model_validate(item["task"]),
                oracle=TaskOracle.model_validate(item["oracle"]),
                metadata=FoundryTaskMetadata.model_validate(item["metadata"]),
                total_cost=int(item.get("total_cost", 40)),
                max_tool_calls=int(item.get("max_tool_calls", 30)),
            )
        )
    return ExternalInvestigationDistribution(
        manifest=FoundryDistributionManifest.model_validate(payload["manifest"]),
        episodes=episodes,
        world_summaries=[
            ExternalWorldSummary.model_validate(item)
            for item in payload.get("world_summaries", [])
        ],
        plan_hash=str(payload["plan_hash"]),
    )
