from __future__ import annotations

from pydantic import BaseModel, Field


class ChallengeValidation(BaseModel):
    challenge_id: str
    leakage_count: int = Field(ge=0)
    oracle_reward: float = Field(ge=0.0, le=1.0)
    exploit_max_reward: float = Field(ge=0.0, le=1.0)
    deterministic: bool
    public_solver_reward: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)


class PromotionPolicy(BaseModel):
    min_oracle_reward: float = 0.99
    max_exploit_reward: float = 0.20
    require_determinism: bool = True
    require_zero_leakage: bool = True


def promotion_failures(validation: ChallengeValidation, policy: PromotionPolicy | None = None) -> list[str]:
    policy = policy or PromotionPolicy()
    failures = []
    if policy.require_zero_leakage and validation.leakage_count:
        failures.append("private_truth_leakage")
    if validation.oracle_reward < policy.min_oracle_reward:
        failures.append("oracle_not_solvable")
    if validation.exploit_max_reward > policy.max_exploit_reward:
        failures.append("exploit_reward_too_high")
    if policy.require_determinism and not validation.deterministic:
        failures.append("nondeterministic")
    return failures


def promotable(validation: ChallengeValidation, policy: PromotionPolicy | None = None) -> bool:
    return not promotion_failures(validation, policy)
