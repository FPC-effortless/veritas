from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SANDBOX_CONTRACT_VERSION = "sandbox-provider-v1"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _validate_relative_path(value: str) -> str:
    if not value:
        raise ValueError("path must not be empty")
    path = PurePosixPath(value)
    if path.is_absolute():
        raise ValueError("path must be relative to the sandbox root")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("path must not contain traversal or dot segments")
    normalized = path.as_posix()
    if normalized != value:
        raise ValueError("path must use normalized POSIX syntax")
    return normalized


class SandboxFailureOrigin(StrEnum):
    REQUEST = "request"
    POLICY = "policy"
    WORKLOAD = "workload"
    INFRASTRUCTURE = "infrastructure"


class SandboxFailureCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    SESSION_DESTROYED = "session_destroyed"
    ASSET_UNDECLARED = "asset_undeclared"
    ASSET_DIGEST_MISMATCH = "asset_digest_mismatch"
    PATH_NOT_ALLOWED = "path_not_allowed"
    CAPABILITY_NOT_ALLOWED = "capability_not_allowed"
    EXECUTION_LIMIT = "execution_limit"
    TIMEOUT = "timeout"
    OUTPUT_LIMIT = "output_limit"
    ARTIFACT_LIMIT = "artifact_limit"
    HANDLER_UNAVAILABLE = "handler_unavailable"
    WORKLOAD_FAILED = "workload_failed"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class SandboxExecutionKind(StrEnum):
    COMMAND = "command"
    TOOL = "tool"


class SandboxExecutionStatus(StrEnum):
    SUCCEEDED = "succeeded"
    WORKLOAD_FAILED = "workload_failed"
    REJECTED = "rejected"
    TIMED_OUT = "timed_out"
    INFRASTRUCTURE_ERROR = "infrastructure_error"


class SandboxResourcePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    timeout_ms: int = Field(default=5_000, ge=1)
    max_output_bytes: int = Field(default=1_048_576, ge=0)
    max_artifact_bytes: int = Field(default=8_388_608, ge=0)
    max_executions: int = Field(default=128, ge=0)


class SandboxAssetDeclaration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str = Field(min_length=1)
    mount_path: str
    sha256: str
    read_only: bool = True

    @field_validator("mount_path")
    @classmethod
    def validate_mount_path(cls, value: str) -> str:
        return _validate_relative_path(value)

    @field_validator("sha256")
    @classmethod
    def validate_sha256(cls, value: str) -> str:
        value = value.lower()
        if not _SHA256_RE.fullmatch(value):
            raise ValueError("sha256 must be a lowercase hexadecimal SHA-256 digest")
        return value


class SandboxSecretRef(BaseModel):
    """Non-secret reference to provider-private secret material."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alias: str = Field(min_length=1)
    opaque_id: str = Field(min_length=1)


class SandboxCapabilityPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    commands: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()

    @field_validator("commands", "tools")
    @classmethod
    def validate_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item for item in value):
            raise ValueError("capability names must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("capability names must be unique")
        return value


class SandboxCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    seed: int = 0
    assets: tuple[SandboxAssetDeclaration, ...] = ()
    writable_paths: tuple[str, ...] = ()
    capabilities: SandboxCapabilityPolicy = Field(default_factory=SandboxCapabilityPolicy)
    resources: SandboxResourcePolicy = Field(default_factory=SandboxResourcePolicy)
    secret_refs: tuple[SandboxSecretRef, ...] = ()

    @field_validator("writable_paths")
    @classmethod
    def validate_writable_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        paths = tuple(_validate_relative_path(item) for item in value)
        if len(set(paths)) != len(paths):
            raise ValueError("writable paths must be unique")
        return paths

    @model_validator(mode="after")
    def validate_unique_declarations(self) -> "SandboxCreateRequest":
        asset_ids = [asset.asset_id for asset in self.assets]
        mount_paths = [asset.mount_path for asset in self.assets]
        aliases = [ref.alias for ref in self.secret_refs]
        opaque_ids = [ref.opaque_id for ref in self.secret_refs]
        if len(set(asset_ids)) != len(asset_ids):
            raise ValueError("asset ids must be unique")
        if len(set(mount_paths)) != len(mount_paths):
            raise ValueError("asset mount paths must be unique")
        if len(set(aliases)) != len(aliases):
            raise ValueError("secret aliases must be unique")
        if len(set(opaque_ids)) != len(opaque_ids):
            raise ValueError("secret opaque ids must be unique")
        return self


class SandboxExecutionRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    kind: SandboxExecutionKind
    name: str = Field(min_length=1)
    argv: tuple[str, ...] = ()
    arguments: dict[str, Any] = Field(default_factory=dict)
    stdin: bytes = b""

    @model_validator(mode="after")
    def validate_kind_shape(self) -> "SandboxExecutionRequest":
        if self.kind is SandboxExecutionKind.TOOL and self.argv:
            raise ValueError("tool requests must use arguments rather than argv")
        if self.kind is SandboxExecutionKind.COMMAND and self.arguments:
            raise ValueError("command requests must use argv rather than arguments")
        return self


class SandboxFailureStatus(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: SandboxFailureOrigin
    code: SandboxFailureCode
    message: str
    retryable: bool = False


class SandboxReplayMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: str = SANDBOX_CONTRACT_VERSION
    provider_name: str
    provider_version: str
    spec_digest: str
    asset_manifest_digest: str
    seed: int
    reset_generation: int = Field(ge=0)
    execution_index: int = Field(ge=0)
    filesystem_digest: str


class SandboxCreateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    metadata: SandboxReplayMetadata


class SandboxMountResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str
    mount_path: str
    size_bytes: int = Field(ge=0)
    sha256: str
    metadata: SandboxReplayMetadata


class SandboxArtifactMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    size_bytes: int = Field(ge=0)
    sha256: str


class SandboxArtifact(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    path: str
    content: bytes
    size_bytes: int = Field(ge=0)
    sha256: str


class SandboxExecutionResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        ser_json_bytes="base64",
        val_json_bytes="base64",
    )

    status: SandboxExecutionStatus
    stdout: bytes = b""
    stderr: bytes = b""
    exit_code: int | None = None
    artifacts: tuple[SandboxArtifactMetadata, ...] = ()
    failure: SandboxFailureStatus | None = None
    metadata: SandboxReplayMetadata


class SandboxCaptureResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifacts: tuple[SandboxArtifact, ...]
    metadata: SandboxReplayMetadata


class SandboxResetResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    metadata: SandboxReplayMetadata


class SandboxDestroyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    session_id: str
    destroyed: bool = True
