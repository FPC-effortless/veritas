from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_IMAGE_DIGEST_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")
_TASK_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


class HarborExportError(ValueError):
    """Fail-closed Harbor export validation or materialization error."""


class HarborArtifactVisibility(StrEnum):
    AGENT_PUBLIC = "agent_public"
    OPERATIONAL_PRIVATE = "operational_private"
    EVALUATOR_PRIVATE = "evaluator_private"
    PROVENANCE = "provenance"


class HarborExportConfig(BaseModel):
    """Immutable inputs that determine a Harbor task package byte-for-byte."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_name: str
    agent_image: str
    runtime_image: str
    verifier_image: str | None = None
    seed: int = Field(default=0, strict=True)
    agent_timeout_sec: float = Field(default=1800.0, gt=0.0)
    verifier_timeout_sec: float = Field(default=600.0, gt=0.0)
    build_timeout_sec: float = Field(default=600.0, gt=0.0)

    @field_validator("task_name")
    @classmethod
    def validate_task_name(cls, value: str) -> str:
        if not _TASK_NAME_RE.fullmatch(value):
            raise ValueError("Harbor task_name must be a lowercase org/name package name")
        return value

    @field_validator("agent_image", "runtime_image", "verifier_image")
    @classmethod
    def validate_immutable_image(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if not _IMAGE_DIGEST_RE.fullmatch(value):
            raise ValueError("Harbor images must be immutable sha256 digest references")
        return value

    @model_validator(mode="after")
    def bind_verifier_image(self) -> "HarborExportConfig":
        if self.verifier_image is None:
            object.__setattr__(self, "verifier_image", self.runtime_image)
        return self


class HarborPackageFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str
    bytes: int = Field(ge=0)
    visibility: HarborArtifactVisibility
    mode: str = "0644"


class HarborExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = ""
    task_name: str
    contract_id: str
    public_contract_id: str
    mcp_surface_id: str
    output_dir: str
    files: tuple[HarborPackageFile, ...]

    @model_validator(mode="after")
    def bind_package_id(self) -> "HarborExportResult":
        payload = {
            "task_name": self.task_name,
            "contract_id": self.contract_id,
            "public_contract_id": self.public_contract_id,
            "mcp_surface_id": self.mcp_surface_id,
            "files": [
                item.model_dump(mode="json")
                for item in sorted(self.files, key=lambda item: item.path)
            ],
        }
        expected = "harbor-package-v1:sha256:" + hashlib.sha256(
            _canonical_json_bytes(payload)
        ).hexdigest()
        if self.package_id and self.package_id != expected:
            raise ValueError("Harbor package_id does not match immutable package contents")
        object.__setattr__(self, "package_id", expected)
        return self
