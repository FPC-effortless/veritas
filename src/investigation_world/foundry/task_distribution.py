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


class TaskDistributionSpec(BaseModel):
    distribution_id: str
    version: str = "1"
    split: DistributionSplit
    capability_mix: dict[str, float]
    difficulty: DifficultyDistribution = Field(default_factory=DifficultyDistribution)
    task_families: list[str] = Field(default_factory=list)
    domain_mix: dict[str, float] = Field(default_factory=dict)
    generator_parameters: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_mix(self):
        if not self.capability_mix:
            raise ValueError("capability_mix cannot be empty")
        if any(weight <= 0 for weight in self.capability_mix.values()):
            raise ValueError("capability weights must be positive")
        if self.domain_mix and any(weight <= 0 for weight in self.domain_mix.values()):
            raise ValueError("domain weights must be positive")
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


def sample_task_parameters(spec: TaskDistributionSpec, *, seed: int) -> SampledTaskParameters:
    rng = random.Random(seed)
    capability = _weighted_choice(rng, spec.capability_mix)
    family = rng.choice(spec.task_families) if spec.task_families else None
    domain = _weighted_choice(rng, spec.domain_mix) if spec.domain_mix else None
    difficulty = spec.difficulty.sample(rng)
    sample_id = f"TDS-{stable_hash([spec.distribution_id, spec.version, spec.split.value, seed])[:16].upper()}"
    return SampledTaskParameters(
        sample_id=sample_id,
        distribution_id=spec.distribution_id,
        split=spec.split,
        seed=seed,
        capability_tags=[capability],
        task_family=family,
        domain=domain,
        difficulty=difficulty,
        generator_parameters=dict(spec.generator_parameters),
    )


def sample_task_batch(spec: TaskDistributionSpec, *, seed_start: int, count: int) -> list[SampledTaskParameters]:
    return [sample_task_parameters(spec, seed=seed_start + index) for index in range(max(0, count))]
