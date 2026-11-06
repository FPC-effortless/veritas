from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


class PreparationError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExtractedMember:
    path: str
    byte_count: int
    sha256: str


def safe_extract_zip(
    archive: Path,
    destination: Path,
    *,
    max_members: int = 100_000,
    max_uncompressed_bytes: int = 20 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 1000.0,
) -> tuple[ExtractedMember, ...]:
    """Extract a ZIP without allowing traversal, links, encryption, or zip bombs."""
    destination = destination.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[ExtractedMember] = []

    with zipfile.ZipFile(archive) as bundle:
        members = bundle.infolist()
        if len(members) > max_members:
            raise PreparationError(
                f"archive has {len(members)} members, exceeding max_members={max_members}"
            )

        total_declared = 0
        normalized_members: set[str] = set()
        for info in members:
            relative = _safe_member_path(info.filename)
            collision_key = relative.as_posix().casefold()
            if collision_key in normalized_members:
                raise PreparationError(
                    f"duplicate normalized ZIP member path is not allowed: {info.filename}"
                )
            normalized_members.add(collision_key)
            if info.flag_bits & 0x1:
                raise PreparationError(f"encrypted ZIP member is not allowed: {info.filename}")
            if _is_symlink(info):
                raise PreparationError(f"symbolic-link ZIP member is not allowed: {info.filename}")
            if info.is_dir():
                continue
            total_declared += info.file_size
            if total_declared > max_uncompressed_bytes:
                raise PreparationError(
                    "archive declared uncompressed size exceeds configured limit"
                )
            if info.compress_size == 0 and info.file_size > 0:
                raise PreparationError(f"invalid compressed size for member: {info.filename}")
            if info.compress_size > 0:
                ratio = info.file_size / info.compress_size
                if ratio > max_compression_ratio:
                    raise PreparationError(
                        f"compression ratio {ratio:.1f} exceeds limit for {info.filename}"
                    )
            _assert_within(destination, destination / relative)

        actual_total = 0
        for info in members:
            relative = _safe_member_path(info.filename)
            target = (destination / relative).resolve()
            _assert_within(destination, target)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256()
            byte_count = 0
            temp_path = target.with_name(f".{target.name}.part")
            try:
                with bundle.open(info, "r") as source, temp_path.open("wb") as output:
                    while True:
                        chunk = source.read(1024 * 1024)
                        if not chunk:
                            break
                        byte_count += len(chunk)
                        actual_total += len(chunk)
                        if actual_total > max_uncompressed_bytes:
                            raise PreparationError(
                                "archive extracted bytes exceed configured limit"
                            )
                        if byte_count > info.file_size:
                            raise PreparationError(
                                f"member exceeded declared size while extracting: {info.filename}"
                            )
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                if byte_count != info.file_size:
                    raise PreparationError(
                        f"member size mismatch for {info.filename}: "
                        f"declared={info.file_size}, extracted={byte_count}"
                    )
                os.replace(temp_path, target)
            finally:
                temp_path.unlink(missing_ok=True)
            extracted.append(
                ExtractedMember(
                    path=relative.as_posix(),
                    byte_count=byte_count,
                    sha256=digest.hexdigest(),
                )
            )

    return tuple(extracted)


def deterministic_stratified_select(
    rows: Sequence[Mapping[str, Any]],
    *,
    id_field: str,
    stratum_field: str,
    quotas: Mapping[str, int],
    salt: str,
) -> tuple[Mapping[str, Any], ...]:
    """Select rows reproducibly within declared strata using stable SHA-256 ordering."""
    if not salt:
        raise ValueError("salt must be non-empty")
    if any(quota < 0 for quota in quotas.values()):
        raise ValueError("quotas must be non-negative")

    grouped: dict[str, list[Mapping[str, Any]]] = {stratum: [] for stratum in quotas}
    seen_ids: set[str] = set()
    for row in rows:
        if id_field not in row or stratum_field not in row:
            raise ValueError(f"row must contain {id_field!r} and {stratum_field!r}")
        identity = str(row[id_field])
        if identity in seen_ids:
            raise ValueError(f"duplicate source-case identity: {identity}")
        seen_ids.add(identity)
        stratum = str(row[stratum_field])
        if stratum in grouped:
            grouped[stratum].append(row)

    selected: list[Mapping[str, Any]] = []
    for stratum in sorted(quotas):
        quota = quotas[stratum]
        candidates = sorted(
            grouped[stratum],
            key=lambda row: _selection_digest(salt, str(row[id_field])),
        )
        if len(candidates) < quota:
            raise PreparationError(
                f"stratum {stratum!r} has {len(candidates)} eligible rows; quota requires {quota}"
            )
        selected.extend(candidates[:quota])
    return tuple(selected)


def copy_with_sha256(source: Path, destination: Path) -> str:
    """Copy a normalized artifact atomically while computing its content identity."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path = destination.with_name(f".{destination.name}.part")
    digest = hashlib.sha256()
    try:
        with source.open("rb") as input_file, temp_path.open("wb") as output_file:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                output_file.write(chunk)
            output_file.flush()
            os.fsync(output_file.fileno())
        os.replace(temp_path, destination)
    finally:
        temp_path.unlink(missing_ok=True)
    return digest.hexdigest()


def prepare_zip_artifact(
    receipt_path: Path,
    acquisition_root: Path,
    prepared_root: Path,
    *,
    max_members: int = 100_000,
    max_uncompressed_bytes: int = 20 * 1024 * 1024 * 1024,
    max_compression_ratio: float = 1000.0,
) -> Path:
    """Verify an acquisition receipt, safely extract its ZIP, and write a hash manifest."""
    from .acquisition import verify_receipt
    from .models import ArtifactReceipt

    receipt_bytes = receipt_path.read_bytes()
    receipt = ArtifactReceipt.model_validate_json(receipt_bytes)
    if not verify_receipt(acquisition_root, receipt):
        raise PreparationError("acquired artifact does not match its provenance receipt")

    archive = (acquisition_root.resolve() / receipt.local_path).resolve()
    root = acquisition_root.resolve()
    if root not in archive.parents:
        raise PreparationError("receipt artifact path escaped acquisition root")

    destination = (
        prepared_root.resolve() / receipt.source_id / receipt.artifact_id / receipt.sha256[:16]
    )
    members = safe_extract_zip(
        archive,
        destination,
        max_members=max_members,
        max_uncompressed_bytes=max_uncompressed_bytes,
        max_compression_ratio=max_compression_ratio,
    )
    manifest = {
        "schema_version": "1.0",
        "source_id": receipt.source_id,
        "artifact_id": receipt.artifact_id,
        "artifact_sha256": receipt.sha256,
        "catalog_sha256": receipt.catalog_sha256,
        "receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
        "members": [
            {
                "path": member.path,
                "byte_count": member.byte_count,
                "sha256": member.sha256,
            }
            for member in members
        ],
    }
    manifest_path = destination / "extraction_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _selection_digest(salt: str, identity: str) -> bytes:
    return hashlib.sha256(f"{salt}\0{identity}".encode()).digest()


def _safe_member_path(name: str) -> PurePosixPath:
    normalized = name.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts:
        raise PreparationError(f"unsafe ZIP member path: {name}")
    if any(part in {"", ".", ".."} for part in path.parts):
        raise PreparationError(f"unsafe ZIP member path: {name}")
    if ":" in path.parts[0]:
        raise PreparationError(f"drive-qualified ZIP member path is not allowed: {name}")
    return path


def _assert_within(root: Path, candidate: Path) -> None:
    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PreparationError(f"archive member escaped extraction root: {candidate}")


def _is_symlink(info: zipfile.ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_IFMT(mode) == stat.S_IFLNK
