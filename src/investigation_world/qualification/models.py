from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from statistics import mean
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash


class QualificationSplit(StrEnum):
    TRAIN = "train"
    DEV = "dev"
    PRIVATE_TEST = "private_test"


class PolicyClass(StrEnum):
    ORACLE = "oracle"
    COMPETENT_HEURISTIC = "competent_heuristic"
    MYOPIC = "myopic"
    RANDOM = "random"
    EXPLOIT = "exploit"


class QualificationScenario(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    source_group_id: str
    split: QualificationSplit
    normalized_text: str = ""
    public_digest: str
    private_digest: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    reward: float = Field(ge=0.0, le=1.0)
    passed: bool = False
    replay_match: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class PolicyEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_class: PolicyClass
    policy_name: str
    outcomes: list[PolicyOutcome] = Field(min_length=1)

    @property
    def mean_reward(self) -> float:
        return mean(item.reward for item in self.outcomes)

    @property
    def replay_rate(self) -> float:
        return mean(1.0 if item.replay_match else 0.0 for item in self.outcomes)


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: str
    source_group_id: str
    source_uri: str
    content_sha256: str
    acquired_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    manifest_id: str = ""
    items: list[EvidenceItem] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest_id(self) -> "EvidenceManifest":
        ids = [item.evidence_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("evidence IDs must be unique")
        payload = [
            item.model_dump(mode="json", exclude={"acquired_at"})
            for item in sorted(self.items, key=lambda item: item.evidence_id)
        ]
        expected = f"EVID-{stable_hash(payload)[:24].upper()}"
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("evidence manifest ID does not match immutable contents")
        object.__setattr__(self, "manifest_id", expected)
        return self


class QualificationThresholds(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    minimum_source_groups: int = Field(default=12, ge=1)
    minimum_train_source_groups: int = Field(default=6, ge=1)
    minimum_dev_source_groups: int = Field(default=2, ge=1)
    minimum_private_test_source_groups: int = Field(default=3, ge=1)
    minimum_private_test_scenarios: int = Field(default=30, ge=1)
    minimum_provenance_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_replay_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_programmatic_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    maximum_broken_rate: float = Field(default=0.05, ge=0.0, le=1.0)
    minimum_oracle_reward: float = Field(default=0.95, ge=0.0, le=1.0)
    maximum_competent_reward: float = Field(default=0.90, ge=0.0, le=1.0)
    maximum_random_reward: float = Field(default=0.20, ge=0.0, le=1.0)
    maximum_exploit_reward: float = Field(default=0.20, ge=0.0, le=1.0)
    minimum_oracle_competent_gap: float = Field(default=0.05, ge=0.0, le=1.0)
    maximum_cross_split_near_duplicates: int = Field(default=0, ge=0)
    maximum_private_leakage_count: int = Field(default=0, ge=0)


class QualificationCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    domain: str
    version: str
    scenarios: list[QualificationScenario] = Field(min_length=1)
    evidence_manifest: EvidenceManifest
    provenance_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    replay_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    programmatic_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    broken_rate: float = Field(default=0.0, ge=0.0, le=1.0)
    private_leakage_count: int = Field(default=0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_scenario_ids(self) -> "QualificationCandidate":
        ids = [item.scenario_id for item in self.scenarios]
        if len(ids) != len(set(ids)):
            raise ValueError("qualification scenario IDs must be unique")
        return self


class QualificationGate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str
    passed: bool
    observed: Any = None
    required: Any = None
    detail: str = ""


class QualificationReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str
    candidate_id: str
    candidate_version: str
    evidence_manifest_id: str
    panel_id: str
    gates: list[QualificationGate]
    policy_means: dict[PolicyClass, float]
    source_overlap: dict[str, list[str]] = Field(default_factory=dict)
    cross_split_near_duplicate_pairs: list[tuple[str, str]] = Field(default_factory=list)
    releaseable: bool


class PrivateReleaseManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    manifest_id: str = ""
    candidate_id: str
    candidate_version: str
    qualification_report_id: str
    evidence_manifest_id: str
    panel_id: str
    train_scenario_ids: list[str]
    dev_scenario_ids: list[str]
    private_test_scenario_ids: list[str]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @model_validator(mode="after")
    def validate_manifest_id(self) -> "PrivateReleaseManifest":
        payload = self.model_dump(mode="json", exclude={"manifest_id", "created_at"})
        expected = f"PRIVREL-{stable_hash(payload)[:24].upper()}"
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("private release manifest ID does not match sealed contents")
        object.__setattr__(self, "manifest_id", expected)
        return self
