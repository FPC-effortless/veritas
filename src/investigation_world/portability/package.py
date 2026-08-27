from __future__ import annotations

import hashlib
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash


class PortablePackageFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str
    bytes: int = Field(ge=0)


class PortablePackageBuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    package_id: str = ""
    adapter: str
    manifest_id: str
    output_dir: str
    files: list[PortablePackageFile]

    @model_validator(mode="after")
    def validate_package_id(self) -> "PortablePackageBuildResult":
        payload = {
            "adapter": self.adapter,
            "manifest_id": self.manifest_id,
            "files": [
                item.model_dump(mode="json")
                for item in sorted(self.files, key=lambda item: item.path)
            ],
        }
        expected = f"PPKG-{stable_hash(payload)[:24].upper()}"
        if self.package_id and self.package_id != expected:
            raise ValueError("portable package ID does not match immutable package contents")
        object.__setattr__(self, "package_id", expected)
        return self


def write_portable_package(
    output_dir: Path,
    *,
    adapter: str,
    manifest_id: str,
    files: dict[str, str],
) -> PortablePackageBuildResult:
    root = output_dir.resolve()
    root.mkdir(parents=True, exist_ok=True)
    written: list[PortablePackageFile] = []

    for relative_path, text in sorted(files.items()):
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"portable package path must be relative: {relative_path}")
        target = (root / relative).resolve()
        if root not in target.parents and target != root:
            raise ValueError(f"portable package path escapes output directory: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = text.encode("utf-8")
        target.write_bytes(payload)
        written.append(
            PortablePackageFile(
                path=relative.as_posix(),
                sha256=hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            )
        )

    return PortablePackageBuildResult(
        adapter=adapter,
        manifest_id=manifest_id,
        output_dir=str(root),
        files=written,
    )
