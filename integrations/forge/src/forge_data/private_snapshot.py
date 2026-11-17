"""Operator-private byte snapshots, NOT redistributable temporal releases.

This API never changes source rights. No export/network API is provided.
Filesystem ownership and operator trust remain outside this integrity boundary.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Any

from .core import ForgeError, canonical

SCHEMA = "forge.private-snapshot.v1"
LIMIT = 64 * 1024 * 1024
MANIFEST_LIMIT = 1024 * 1024
SPEC_FIELDS = {
    "snapshot_id",
    "source_version",
    "ai_use_allowed",
    "redistribution_allowed",
    "privacy_reviewed",
    "visibility",
    "purpose",
    "excluded_claims",
}
MANIFEST_FIELDS = {"schema", "specification", "files", "qualification", "export_policy"}
QUALIFICATION = "BYTE_INTEGRITY_ONLY_NOT_SCIENTIFIC_QUALIFICATION"
EXPORT_POLICY = "NO_REDISTRIBUTION"
_HEX_SHA256 = re.compile(r"[a-f0-9]{64}\Z")


def _spec(value: object) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != SPEC_FIELDS:
        raise ForgeError("exact private snapshot specification required")
    if (
        not isinstance(value["ai_use_allowed"], bool)
        or value["ai_use_allowed"] is not True
        or not isinstance(value["redistribution_allowed"], bool)
        or value["redistribution_allowed"] is not False
        or not isinstance(value["privacy_reviewed"], bool)
        or value["privacy_reviewed"] is not True
        or value["visibility"] != "operator_private"
    ):
        raise ForgeError(
            "private snapshot requires reviewed AI-use and explicit no-redistribution"
        )
    for field in ("snapshot_id", "source_version", "purpose", "excluded_claims"):
        item = value[field]
        if (
            not isinstance(item, str)
            or not item.strip()
            or "\x00" in item
            or len(item) > 1024
        ):
            raise ForgeError("bounded explicit private scope required")
    return dict(value)


def _no_symlinks(path: str | os.PathLike[str]) -> Path:
    candidate = Path(path).absolute()
    if any(item.is_symlink() for item in (candidate, *candidate.parents)):
        raise ForgeError("symlink root/ancestor unsupported")
    return candidate


def _validate_name(name: object) -> str:
    if (
        not isinstance(name, str)
        or not name
        or len(name) > 1024
        or "\\" in name
        or "\x00" in name
        or Path(name).is_absolute()
        or any(part in ("", ".", "..") for part in name.split("/"))
    ):
        raise ForgeError("relative regular file required")
    return name


def _validate_roster(files: object) -> list[str]:
    if not isinstance(files, list) or not 1 <= len(files) <= 128:
        raise ForgeError("unique bounded file roster required")
    names = [_validate_name(item) for item in files]
    if len(set(names)) != len(names) or "manifest.json" in names:
        raise ForgeError("unique bounded file roster required")
    ordered = sorted(names)
    name_set = set(names)
    for name in ordered:
        parts = name.split("/")
        if any("/".join(parts[:index]) in name_set for index in range(1, len(parts))):
            raise ForgeError("file roster contains a file/directory path collision")
    return ordered


def _path(root: str | os.PathLike[str], name: str) -> Path:
    name = _validate_name(name)
    source_root = _no_symlinks(root).resolve(strict=True)
    if not source_root.is_dir():
        raise ForgeError("private snapshot source root must be a directory")
    candidate = source_root.joinpath(*name.split("/"))
    current = candidate
    while current != source_root:
        if current.is_symlink():
            raise ForgeError("symlink unsupported")
        current = current.parent
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(source_root) or not candidate.is_file():
        raise ForgeError("file missing or escapes source")
    return candidate


def _read(path: Path, limit: int = LIMIT) -> bytes:
    with path.open("rb") as stream:
        content = stream.read(limit + 1)
    if len(content) > limit:
        raise ForgeError("private file exceeds bound")
    return content


def freeze_private(
    root: str | os.PathLike[str],
    files: object,
    spec: object,
    destination: str | os.PathLike[str],
) -> dict[str, Any]:
    """Copy an explicit bounded file roster into an immutable private snapshot.

    The caller's scientific split map is retained. No split independence, data
    adequacy, provenance authenticity, source rights, or scientific qualification
    is inferred by this operation.
    """
    specification = _spec(spec)
    names = _validate_roster(files)
    sources = {name: _path(root, name) for name in names}

    target = _no_symlinks(destination)
    if target.exists():
        raise ForgeError("private snapshot destination already exists")

    target.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".forge-private-", dir=target.parent))
    os.chmod(stage, 0o700)
    try:
        entries: dict[str, dict[str, str | int]] = {}
        total = 0
        for name, source in sources.items():
            content = _read(source)
            total += len(content)
            if total > LIMIT:
                raise ForgeError("snapshot exceeds total bound")

            output = stage.joinpath(*name.split("/"))
            output.parent.mkdir(parents=True, exist_ok=True)
            for parent in output.parents:
                if parent == stage.parent:
                    break
                os.chmod(parent, 0o700)
            output.write_bytes(content)
            os.chmod(output, 0o600)
            entries[name] = {
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
            }

        manifest = {
            "schema": SCHEMA,
            "specification": specification,
            "files": entries,
            "qualification": QUALIFICATION,
            "export_policy": EXPORT_POLICY,
        }
        manifest_path = stage / "manifest.json"
        manifest_path.write_bytes(canonical(manifest))
        os.chmod(manifest_path, 0o600)
        os.replace(stage, target)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ForgeError("duplicate private manifest JSON key")
        result[key] = value
    return result


def _constant(value: str) -> None:
    raise ForgeError(f"nonfinite private manifest number: {value}")


def _parse_manifest(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw, object_pairs_hook=_pairs, parse_constant=_constant)
        if not isinstance(value, dict) or canonical(value) != raw:
            raise ForgeError("private manifest must be canonical JSON")
        return value
    except ForgeError:
        raise
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ForgeError("invalid private manifest JSON") from exc


def _expected_directories(names: list[str]) -> set[str]:
    directories: set[str] = set()
    for name in names:
        parts = name.split("/")[:-1]
        for index in range(1, len(parts) + 1):
            directories.add("/".join(parts[:index]))
    return directories


def verify_private(
    root: str | os.PathLike[str],
    manifest_sha256: str,
) -> dict[str, Any]:
    """Verify exact manifest bytes, roster, filesystem tree, modes, and contents."""
    snapshot = _no_symlinks(root)
    if not snapshot.is_dir():
        raise ForgeError("private snapshot root must be a directory")

    raw = _read(_path(snapshot, "manifest.json"), MANIFEST_LIMIT)
    if (
        not isinstance(manifest_sha256, str)
        or _HEX_SHA256.fullmatch(manifest_sha256) is None
        or hashlib.sha256(raw).hexdigest() != manifest_sha256
    ):
        raise ForgeError("private manifest pin mismatch")

    manifest = _parse_manifest(raw)
    if set(manifest) != MANIFEST_FIELDS:
        raise ForgeError("invalid private snapshot manifest fields")
    if (
        manifest["schema"] != SCHEMA
        or manifest["qualification"] != QUALIFICATION
        or manifest["export_policy"] != EXPORT_POLICY
    ):
        raise ForgeError("invalid private snapshot schema/policy")

    _spec(manifest["specification"])
    file_entries = manifest["files"]
    if not isinstance(file_entries, dict):
        raise ForgeError("invalid private file roster")
    names = _validate_roster(list(file_entries))
    expected_files = set(names) | {"manifest.json"}
    expected_directories = _expected_directories(names)

    observed_files: set[str] = set()
    observed_directories: set[str] = set()
    for path in snapshot.rglob("*"):
        if path.is_symlink():
            raise ForgeError("symlink unsupported in private snapshot")
        relative = path.relative_to(snapshot).as_posix()
        if path.is_dir():
            observed_directories.add(relative)
        elif path.is_file():
            observed_files.add(relative)
        else:
            raise ForgeError("special filesystem entry unsupported in private snapshot")

    if observed_files != expected_files or observed_directories != expected_directories:
        raise ForgeError("extra/missing private snapshot files or directories")

    if os.name == "posix":
        for path in (snapshot, *snapshot.rglob("*")):
            mode = stat.S_IMODE(path.lstat().st_mode)
            expected_mode = 0o700 if path.is_dir() else 0o600
            if mode != expected_mode:
                raise ForgeError("private snapshot permissions changed")

    total = 0
    for name, entry in file_entries.items():
        if (
            not isinstance(entry, dict)
            or set(entry) != {"sha256", "bytes"}
            or not isinstance(entry["sha256"], str)
            or _HEX_SHA256.fullmatch(entry["sha256"]) is None
            or not isinstance(entry["bytes"], int)
            or isinstance(entry["bytes"], bool)
            or entry["bytes"] < 0
            or entry["bytes"] > LIMIT
        ):
            raise ForgeError("invalid private file entry")
        content = _read(_path(snapshot, name))
        total += len(content)
        if (
            len(content) != entry["bytes"]
            or hashlib.sha256(content).hexdigest() != entry["sha256"]
        ):
            raise ForgeError("private snapshot content mismatch")
    if total > LIMIT:
        raise ForgeError("private snapshot exceeds bound")

    return {
        "valid": True,
        "schema": SCHEMA,
        "manifest_sha256": manifest_sha256,
        "files": len(file_entries),
        "redistribution_allowed": False,
        "qualification": QUALIFICATION,
    }
