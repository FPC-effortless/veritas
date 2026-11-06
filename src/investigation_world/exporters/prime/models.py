from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PrimeReplayRequest(BaseModel):
    """One portable invocation recorded by the Prime adapter for deterministic replay."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["action", "operation"]
    name: str
    arguments: dict[str, object] = Field(default_factory=dict)


class PrimePackageFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str
    bytes: int = Field(ge=0)


class PrimePackageBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str
    export_id: str
    output_dir: str
    files: tuple[PrimePackageFile, ...]
