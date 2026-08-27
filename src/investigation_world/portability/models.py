from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash


class PortableVisibility(StrEnum):
    PUBLIC_SAMPLE = "public_sample"
    BUYER_SAFE = "buyer_safe"
    PRIVATE_OPERATOR = "private_operator"


class PortableSplit(StrEnum):
    TRAIN = "train"
    DEV = "dev"
    PRIVATE_TEST = "private_test"


class PortableReleaseIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str
    candidate_version: str
    evidence_manifest_id: str
    qualification_report_id: str
    panel_id: str
    private_release_manifest_id: str
    source_bundle_sha256: str | None = None


class PortableCapability(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    capability_id: str
    version: str = "1"
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    deterministic: bool = True


class PortableResetContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    deterministic: bool = True
    identity_inputs: list[str] = Field(default_factory=lambda: ["environment_version", "task_id", "seed"])
    state_digest_algorithm: str = "sha256"
    reset_semantics: str


class PortableVerifierContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    verifier_id: str
    version: str = "1"
    reward_range: tuple[float, float] = (0.0, 1.0)
    deterministic: bool = True
    requires_private_ground_truth: bool = True
    description: str

    @model_validator(mode="after")
    def validate_reward_range(self) -> "PortableVerifierContract":
        low, high = self.reward_range
        if low > high:
            raise ValueError("reward_range lower bound must not exceed upper bound")
        return self


class PortableArtifactReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    role: str
    content_sha256: str
    visibility: PortableVisibility
    media_type: str = "application/octet-stream"
    path_hint: str | None = None


class PortableTask(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    split: PortableSplit
    seed: int
    agent_payload: dict[str, Any]
    content_digest: str
    capability_tags: list[str] = Field(default_factory=list)
    source_group_digest: str | None = None
    verifier_reference: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class PortableTasksetManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    taskset_id: str = ""
    taskset_version: str
    visible_tasks: list[PortableTask] = Field(default_factory=list)
    private_task_count: int = Field(default=0, ge=0)
    private_task_ids_included: bool = False
    private_ground_truth_included: bool = False

    @model_validator(mode="after")
    def validate_identity_and_boundary(self) -> "PortableTasksetManifest":
        task_ids = [task.task_id for task in self.visible_tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("portable task IDs must be unique")
        if self.private_ground_truth_included and not self.private_task_ids_included:
            raise ValueError("private ground truth cannot be included without private task identities")
        payload = self.model_dump(mode="json", exclude={"taskset_id"})
        expected = f"PTASK-{stable_hash(payload)[:24].upper()}"
        if self.taskset_id and self.taskset_id != expected:
            raise ValueError("portable taskset ID does not match immutable contents")
        object.__setattr__(self, "taskset_id", expected)
        return self


class PortableMeteringContract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id_required: bool = True
    task_id_required: bool = True
    environment_version_required: bool = True
    fields: list[str] = Field(
        default_factory=lambda: [
            "run_id",
            "environment_id",
            "environment_version",
            "task_id",
            "seed",
            "started_at",
            "finished_at",
            "reward",
        ]
    )


class PortableEnvironmentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = "0.11.0"
    manifest_id: str = ""
    environment_id: str
    environment_version: str
    sku: str
    domain: str
    description: str
    visibility: PortableVisibility
    release: PortableReleaseIdentity
    taskset: PortableTasksetManifest
    capabilities: list[PortableCapability]
    reset: PortableResetContract
    verifier: PortableVerifierContract
    artifacts: list[PortableArtifactReference] = Field(default_factory=list)
    adapters: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    licensing: dict[str, Any] = Field(default_factory=dict)
    metering: PortableMeteringContract = Field(default_factory=PortableMeteringContract)

    @model_validator(mode="after")
    def validate_manifest_id(self) -> "PortableEnvironmentManifest":
        capability_ids = [capability.capability_id for capability in self.capabilities]
        if len(capability_ids) != len(set(capability_ids)):
            raise ValueError("portable capability IDs must be unique")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("portable artifact IDs must be unique")
        payload = self.model_dump(mode="json", exclude={"manifest_id"})
        expected = f"PENV-{stable_hash(payload)[:24].upper()}"
        if self.manifest_id and self.manifest_id != expected:
            raise ValueError("portable environment manifest ID does not match immutable contents")
        object.__setattr__(self, "manifest_id", expected)
        return self
