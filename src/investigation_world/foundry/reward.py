from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, Field, model_validator


class RewardWeights(BaseModel):
    outcome: float = Field(default=0.65, ge=0.0)
    evidence: float = Field(default=0.15, ge=0.0)
    process: float = Field(default=0.10, ge=0.0)
    efficiency: float = Field(default=0.10, ge=0.0)

    @model_validator(mode="after")
    def nonzero(self):
        if self.outcome + self.evidence + self.process + self.efficiency <= 0:
            raise ValueError("at least one reward weight must be positive")
        return self


class GatedRewardContract(BaseModel):
    weights: RewardWeights = Field(default_factory=RewardWeights)
    hard_invariants: list[str] = Field(default_factory=list)
    terminal_outcome_min_share: float = Field(default=0.50, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def outcome_dominant(self):
        total = self.weights.outcome + self.weights.evidence + self.weights.process + self.weights.efficiency
        if self.weights.outcome / total < self.terminal_outcome_min_share:
            raise ValueError("terminal outcome must dominate the reward contract")
        return self


def gated_reward(
    components: Mapping[str, float],
    *,
    invariant_results: Mapping[str, bool],
    contract: GatedRewardContract | None = None,
) -> float:
    contract = contract or GatedRewardContract()
    for invariant in contract.hard_invariants:
        if invariant_results.get(invariant) is not True:
            return 0.0

    weights = contract.weights
    weighted = (
        max(0.0, min(1.0, float(components.get("outcome", 0.0)))) * weights.outcome
        + max(0.0, min(1.0, float(components.get("evidence", 0.0)))) * weights.evidence
        + max(0.0, min(1.0, float(components.get("process", 0.0)))) * weights.process
        + max(0.0, min(1.0, float(components.get("efficiency", 0.0)))) * weights.efficiency
    )
    total = weights.outcome + weights.evidence + weights.process + weights.efficiency
    return weighted / total
