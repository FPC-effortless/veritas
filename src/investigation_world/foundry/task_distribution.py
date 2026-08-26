from __future__ import annotations

import random
from typing import Any

from pydantic import BaseModel, Field, model_validator

from investigation_world.foundry.models import DifficultyVector, DistributionSplit, stable_hash


class IntRange(BaseModel):
    minimum: int
    maximum: int

    @model_validator(mode="after")
    def ordered(self):
        if self.maximum < self.minimum:
            raise ValueError("maximum must be >= minimum")
        return self

    def sample(self, rng: random.Random) -> int:
        return rng.randint(self.minimum, self.maximum)


class FloatRange(BaseModel):
    minimum: float
    maximum: float

    @model_validator(mode="after")
    def ordered(self):
        if self.maximum < self.minimum:
            raise ValueError("maximum must be >= minimum")
        return self

    def sample(self, rng: random.Random) -> float:
        return rng.uniform(self.minimum, self.maximum)


class DifficultyDistribution(BaseModel):
    entities: IntRange = Field(default_factory=lambda: IntRange(minimum=1, maximum=4))
    tools: IntRange = Field(default_factory=lambda: IntRange(minimum=1, maximum=3))
    steps: IntRange = Field(default_factory=lambda: IntRange(minimum=1, maximum=4))
    distractors: IntRange = Field(default_factory=lambda: IntRange(minimum=0, maximum=2))
    missing_probability: FloatRange = Field(default_factory=lambda: FloatRange(minimum=0.0, maximum=0.1))
    conflict_probability: FloatRange = Field(default_factory=lambda: FloatRange(minimum=0.0, maximum=0.1))
    dependency_depth: IntRange = Field(default_factory=lambda: IntRange(minimum=1, maximum=3))
    budget_ratio: FloatRange = Field(default_factory=lambda: FloatRange(minimum=0.75, maximum=1.25))
    stochasticity: FloatRange = Field(default_factory=lambda: FloatRange(minimum=0.0, maximum=0.2))
    adversarial_pressure: FloatRange = Field(default_factory=lambda: FloatRange(minimum=0.0, maximum=0.1))

    def sample(self, rng: random.Random) -> DifficultyVector:
        return DifficultyVector(
            entities=self.entities.sample(rng),
            tools=self.tools.sample(rng),
            steps=self.steps.sample(rng),
            distractors=self.distractors.sample(rng),
            missing_probability=self.missing_probability.sample(rng),
            conflict_probability=self.conflict_probability.sample(rng),
            dependency_depth=self.dependency_depth.sample(rng),
            budget_ratio=self.budget_ratio.sample(rng),
            stochasticity=self.stochasticity.sample(rng),
            adversarial_pressure=self.adversarial_pressure.sample(rng),
        )


class CapabilityBundle(BaseModel):
    """Weighted combination of capabilities that a sampled task must exercise together."""

    tags: list[str] = Field(min_length=1)
    weight: float = Field(default=1.0, gt=0.0)

    @model_validator(mode="after")
    def unique_nonempty_tags(self):
        cleaned = [tag.strip() for tag in self.tags if tag.strip()]
        if not cleaned:
            raise ValueError("capability bundle must contain at least one non-empty tag")
        if len(set(cleaned)) != len(cleaned):
            raise ValueError("capability bundle tags must be unique")
        self.tags = cleaned
        return self


class TaskDistributionSpec(BaseModel):
    """Generative task-distribution contract, decoupled from harness and runtime."""

    distribution_id: str
    version: str = "1"
    split: DistributionSplit
    capability_mix: dict[str, float] = Field(default_factory=dict)
    capability_bundles: list[CapabilityBundle] = Field(default_factory=list)
    difficulty: DifficultyDistribution = Field(default_factory=DifficultyDistribution)
    task_families: list[str] = Field(default_factory=list)
    task_family_mix: dict[str, float] = Field(default_factory=dict)
    domain_mix: dict[str, float] = Field(default_factory=dict)
    generator_parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mix(self):
        if not self.capability_mix and not self.capability_bundles:
            raise ValueError("at least one capability mix or capability bundle is required")
        if any(weight <= 0 for weight in self.capability_mix.values()):
            raise ValueError("capability weights must be positive")
        if self.task_family_mix and any(weight <= 0 for weight in self.task_family_mix.values()):
            raise ValueError("task-family weights must be positive")
        if self.domain_mix and any(weight <= 0 for weight in self.domain_mix.values()):
            raise ValueError("domain weights must be positive")
        if self.task_family_mix and self.task_families:
            overlap = set(self.task_family_mix).intersection(self.task_families)
            if not overlap and self.task_families:
                raise ValueError("task_families and task_family_mix describe disjoint families")
        return self


class SampledTaskParameters(BaseModel):
    sample_id: str
    distribution_id: str
    split: DistributionSplit
    seed: int
    capability_tags: list[str]
    task_family: str | None = None
    domain: str | None = None
    difficulty: DifficultyVector
    generator_parameters: dict[str, Any] = Field(default_factory=dict)


def _weighted_choice(rng: random.Random, values: dict[str, float]) -> str:
    names = list(values)
    weights = [values[name] for name in names]
    return rng.choices(names, weights=weights, k=1)[0]


def _sample_capabilities(rng: random.Random, spec: TaskDistributionSpec) -> list[str]:
    if spec.capability_bundles:
        selected = rng.choices(
            spec.capability_bundles,
            weights=[bundle.weight for bundle in spec.capability_bundles],
            k=1,
        )[0]
        return list(selected.tags)
    return [_weighted_choice(rng, spec.capability_mix)]


def _sample_family(rng: random.Random, spec: TaskDistributionSpec) -> str | None:
    if spec.task_family_mix:
        return _weighted_choice(rng, spec.task_family_mix)
    return rng.choice(spec.task_families) if spec.task_families else None


def sample_task_parameters(spec: TaskDistributionSpec, *, seed: int) -> SampledTaskParameters:
    rng = random.Random(seed)
    capabilities = _sample_capabilities(rng, spec)
    family = _sample_family(rng, spec)
    domain = _weighted_choice(rng, spec.domain_mix) if spec.domain_mix else None
    difficulty = spec.difficulty.sample(rng)
    sample_id = f"TDS-{stable_hash([spec.distribution_id, spec.version, spec.split.value, seed])[:16].upper()}"
    return SampledTaskParameters(
        sample_id=sample_id,
        distribution_id=spec.distribution_id,
        split=spec.split,
        seed=seed,
        capability_tags=capabilities,
        task_family=family,
        domain=domain,
        difficulty=difficulty,
        generator_parameters=dict(spec.generator_parameters),
    )


def sample_task_batch(spec: TaskDistributionSpec, *, seed_start: int, count: int) -> list[SampledTaskParameters]:
    return [sample_task_parameters(spec, seed=seed_start + index) for index in range(max(0, count))]
