from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class PolicyStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid")
    policy: str
    privileged: bool = False
    episodes: int = 0
    mean_reward: float = 0.0
    min_reward: float = 0.0
    max_reward: float = 0.0
    median_reward: float = 0.0
    p95_reward: float = 0.0
    nonzero_rate: float = 0.0
    perfect_rate: float = 0.0
    by_family: dict[str, dict[str, float | int]] = Field(default_factory=dict)


class BenchmarkInvariant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    passed: bool
    observed: Any = None
    expected: Any = None
    detail: str = ""


class CompanyWorldBenchmarkReport(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: str = "veritas-companyworld-validation-v1"
    world_id: str
    episodes: int
    task_families: dict[str, int]
    splits: dict[str, int]
    invariants: list[BenchmarkInvariant] = Field(default_factory=list)
    policies: list[PolicyStatistics] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return not self.errors and all(item.passed for item in self.invariants)
