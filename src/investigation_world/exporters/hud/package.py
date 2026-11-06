from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.exporters.hud.adapter import (
    HUD_EXPORT_VERSION,
    HUD_PINNED_SDK,
    HudOperationalAdapter,
)
from investigation_world.exporters.hud.templates import (
    PINNED_FASTMCP,
    PINNED_MCP,
    PINNED_PYTHON_BASE_IMAGE,
    render_dockerfile,
    render_env,
    render_mcp_service,
    render_operator_readme,
    render_pyproject,
)
from investigation_world.exporters.hud.vendoring import vendor_files
from investigation_world.portable_contract import PortableOperationalContract


class HudPackageFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str
    sha256: str
    bytes: int = Field(ge=0)


class HudOperationalExportResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    export_id: str
    public_package_id: str
    operator_package_id: str
    public_contract_id: str
    contract_id: str
    output_dir: str
    files: tuple[HudPackageFile, ...]


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )


def _content_id(namespace: str, value: Any) -> str:
    digest = hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()
    return f"{namespace}:sha256:{digest}"


def _file_fingerprints(files: dict[str, str]) -> list[dict[str, Any]]:
    fingerprints: list[dict[str, Any]] = []
    for path, text in sorted(files.items()):
        payload = text.encode("utf-8")
        fingerprints.append(
            {
                "path": path,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "bytes": len(payload),
            }
        )
    return fingerprints


def _public_base_files(adapter: HudOperationalAdapter) -> dict[str, str]:
    return {
        "public/portable_public_contract.json": (
            adapter.contract.public.canonical_bytes().decode("utf-8")
        ),
        "public/mcp_surface.json": _canonical_json(
            adapter.surface.model_dump(mode="json", by_alias=True)
        ),
        "public/README.md": (
            "# Veritas generic HUD public package\n\n"
            "This directory contains only agent-safe/public contract and compiled MCP surface "
            "metadata. The evaluator-bearing HUD runtime image is built from the separate "
            "operator directory and must remain operator-side.\n"
        ),
    }


def _operator_base_files(adapter: HudOperationalAdapter) -> dict[str, str]:
    files = vendor_files()
    files.update(
        {
            "contract.json": adapter.contract.canonical_bytes().decode("utf-8"),
            "env.py": render_env(),
            "mcp_service.py": render_mcp_service(),
            "pyproject.toml": render_pyproject(),
            "Dockerfile": render_dockerfile(),
            "README.md": render_operator_readme(adapter),
        }
    )
    return {f"operator/{path}": text for path, text in files.items()}


def _write_files(root: Path, files: dict[str, str]) -> tuple[HudPackageFile, ...]:
    root = root.resolve()
    if root.exists() and any(root.iterdir()):
        raise RuntimeError(
            "HUD export output directory must be empty to avoid undeclared stale package files"
        )
    root.mkdir(parents=True, exist_ok=True)
    written: list[HudPackageFile] = []
    for relative_path, text in sorted(files.items()):
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"HUD package path must be relative: {relative_path}")
        target = (root / relative).resolve()
        if root not in target.parents:
            raise ValueError(f"HUD package path escapes output directory: {relative_path}")
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = text.encode("utf-8")
        target.write_bytes(payload)
        written.append(
            HudPackageFile(
                path=relative.as_posix(),
                sha256=hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            )
        )
    return tuple(written)


def build_hud_operational_export(
    contract: PortableOperationalContract,
    output_dir: Path,
) -> HudOperationalExportResult:
    """Build public metadata plus a sealed operator-side HUD container context."""

    adapter = HudOperationalAdapter(contract)
    public_base = _public_base_files(adapter)
    public_metadata = adapter.metadata(include_private_identity=False)
    public_package_id = _content_id(
        "HUDPUB",
        {
            "version": HUD_EXPORT_VERSION,
            "metadata": public_metadata,
            "files": _file_fingerprints(public_base),
        },
    )
    public_metadata["public_package_id"] = public_package_id
    public_files = dict(public_base)
    public_files["public/package.json"] = _canonical_json(public_metadata)

    operator_base = _operator_base_files(adapter)
    operator_metadata = adapter.metadata(include_private_identity=True)
    operator_metadata.update(
        {
            "public_package_id": public_package_id,
            "python_base_image": PINNED_PYTHON_BASE_IMAGE,
            "hud_dependency": HUD_PINNED_SDK,
            "mcp_dependency": PINNED_MCP,
            "fastmcp_dependency": PINNED_FASTMCP,
        }
    )
    operator_package_id = _content_id(
        "HUDOP",
        {
            "version": HUD_EXPORT_VERSION,
            "metadata": operator_metadata,
            "files": _file_fingerprints(operator_base),
        },
    )
    operator_metadata["operator_package_id"] = operator_package_id
    operator_files = dict(operator_base)
    operator_files["operator/package.json"] = _canonical_json(operator_metadata)

    files = {**public_files, **operator_files}
    written = _write_files(output_dir, files)
    export_id = _content_id(
        "HUDEXPORT",
        {
            "public_package_id": public_package_id,
            "operator_package_id": operator_package_id,
            "files": [item.model_dump(mode="json") for item in written],
        },
    )
    return HudOperationalExportResult(
        export_id=export_id,
        public_package_id=public_package_id,
        operator_package_id=operator_package_id,
        public_contract_id=contract.public.public_id,
        contract_id=contract.contract_id,
        output_dir=str(output_dir.resolve()),
        files=written,
    )
