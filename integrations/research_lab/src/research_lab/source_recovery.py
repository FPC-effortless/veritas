"""Recover exact archived source without importing models or opening binary data."""

from __future__ import annotations

import ast
import json
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from trainlab.runner import digest, write_json

from .core import LabError, name


def _safe_path(value):
    if not isinstance(value, str) or "\\" in value or "\x00" in value:
        raise LabError("invalid archive path")
    path = PurePosixPath(value)
    if path.is_absolute() or not path.parts or any(p in (".", "..") for p in path.parts):
        raise LabError("archive path escapes source root")
    if value not in (str(path), str(path) + "/"):
        raise LabError("archive paths must be canonical")
    return path


def _recover(entry, archives, destination):
    archive_path = archives / _safe_path(entry["archive"])
    if (
        not re.fullmatch(r"[a-f0-9]{64}", entry["archive_sha256"])
        or digest(archive_path) != entry["archive_sha256"]
    ):
        raise LabError("archive identity mismatch")
    prefix = entry["prefix"]
    if prefix:
        _safe_path(prefix)
    if prefix and not prefix.endswith("/"):
        raise LabError("source prefix must end in slash")
    target = destination / entry["id"]
    if target.is_symlink() or destination.is_symlink():
        raise LabError("recovery root may not be a symlink")
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        paths = [x.filename for x in infos]
        normalized = [str(_safe_path(x)) for x in paths]
        if (
            len(infos) > 10000
            or len(paths) != len(set(paths))
            or len(normalized) != len(set(normalized))
            or sum(x.file_size for x in infos) > 2 * 1024**3
        ):
            raise LabError("archive exceeds bounds or has duplicate members")
        for info in infos:
            _safe_path(info.filename)
            if stat.S_ISLNK(info.external_attr >> 16):
                raise LabError("archive symlinks are unsupported")
        selected = [
            x
            for x in infos
            if x.filename.startswith(prefix)
            and not x.is_dir()
            and (
                x.filename.endswith((".py", ".js"))
                or PurePosixPath(x.filename).name
                in {
                    "PROTOCOL.json",
                    "SOURCE_PROVENANCE.json",
                    "SOURCE_MANIFEST.json",
                    "AGENTS.md",
                    "SKILL.md",
                }
            )
        ]
        required = {prefix + str(_safe_path(x)) for x in entry["required"]}
        if not required <= {x.filename for x in selected}:
            raise LabError("required original source or protocol missing")
        if sum(x.file_size for x in selected) > 128 * 1024**2:
            raise LabError("source closure exceeds 128 MiB")
        manifest = {}
        python_count = 0
        javascript_count = 0
        destination.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination) as temporary:
            stage = Path(temporary) / "source"
            stage.mkdir()
            for info in selected:
                if info.file_size > 4 * 1024**2:
                    raise LabError("source member exceeds 4 MiB")
                relative = info.filename[len(prefix) :]
                relative_path = _safe_path(relative)
                path = stage.joinpath(*relative_path.parts)
                if not path.resolve().is_relative_to(stage.resolve()):
                    raise LabError("source extraction escaped staging")
                path.parent.mkdir(parents=True, exist_ok=True)
                data = archive.read(info)
                path.write_bytes(data)
                if path.suffix == ".py":
                    ast.parse(data, filename=relative)
                    python_count += 1
                elif path.suffix == ".js":
                    javascript_count += 1
                manifest[relative] = digest(path)
            provenance = {
                "archive_sha256": entry["archive_sha256"],
                "prefix": prefix,
                "library_file_id": entry["library_file_id"],
                "files": manifest,
            }
            write_json(stage / "RECOVERY_MANIFEST.json", provenance)
            if target.exists():
                actual = {
                    p.relative_to(target).as_posix(): digest(p)
                    for p in target.rglob("*")
                    if p.is_file()
                }
                expected = {
                    p.relative_to(stage).as_posix(): digest(p)
                    for p in stage.rglob("*")
                    if p.is_file()
                }
                if actual != expected or any(p.is_symlink() for p in target.rglob("*")):
                    raise LabError(
                        "existing recovered source changed; preserve it under a new identity"
                    )
            else:
                stage.rename(target)
    return {
        "status": "SOURCE_RECOVERED",
        "source_files": len(manifest),
        "python_files": python_count,
        "javascript_files": javascript_count,
        "manifest_sha256": digest(target / "RECOVERY_MANIFEST.json"),
        "source_checks": {
            "archive_hash": "PASS",
            "required_files": "PASS",
            "python_syntax": "PASS",
            "javascript_syntax": "UNVERIFIED" if javascript_count else "NOT_APPLICABLE",
        },
        "training_admission": "NOT_ADMITTED; NEW_PROTOCOL_AND_SOURCE_GATES_REQUIRED",
        "fitted_models": 0,
        "checkpoint_replay": "NOT_PERFORMED",
    }


def recover_sources(catalog, archives, destination):
    if (
        not isinstance(catalog, dict)
        or set(catalog) != {"schema", "lanes"}
        or catalog["schema"] != "research_lab.source_catalog.v1"
    ):
        raise LabError("unsupported source catalog")
    if not isinstance(catalog["lanes"], list) or not 1 <= len(catalog["lanes"]) <= 128:
        raise LabError("bounded source lanes required")
    ids = set()
    results = []
    for entry in catalog["lanes"]:
        if not isinstance(entry, dict):
            raise LabError("invalid source lane")
        name(entry.get("id"))
        if entry["id"] in ids:
            raise LabError("duplicate source lane")
        ids.add(entry["id"])
        if entry.get("archive") is None:
            if (
                set(entry) != {"id", "archive", "reason"}
                or not isinstance(entry["reason"], str)
                or not entry["reason"].strip()
            ):
                raise LabError("missing source needs an explicit reason")
            result = {"status": "SOURCE_MISSING", "reason": entry["reason"], "fitted_models": 0}
        else:
            if set(entry) != {
                "id",
                "archive",
                "archive_sha256",
                "library_file_id",
                "prefix",
                "required",
                "next_test",
            }:
                raise LabError("invalid recovered-source fields")
            if not isinstance(entry["required"], list) or not 1 <= len(entry["required"]) <= 128:
                raise LabError("required entrypoints missing")
            try:
                result = _recover(entry, Path(archives), Path(destination))
            except (LabError, OSError, ValueError, SyntaxError, zipfile.BadZipFile) as exc:
                result = {"status": "BLOCKED", "reason": str(exc), "fitted_models": 0}
        results.append({"id": entry["id"], **result})
    return {
        "schema": "research_lab.source_recovery.v1",
        "lanes": results,
        "fitted_models": 0,
        "scope": "SOURCE_RECOVERY_AND_PYTHON_SYNTAX_ONLY; NO_IMPORT_NO_BINARY_DATA_NO_TRAINING",
    }


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("archives", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    from trainlab.runner import read_json

    report = recover_sources(read_json(args.catalog), args.archives, args.destination)
    write_json(args.report, report)
    print(
        json.dumps(
            {
                "lanes": len(report["lanes"]),
                "recovered": sum(x["status"] == "SOURCE_RECOVERED" for x in report["lanes"]),
                "fitted_models": 0,
            }
        )
    )
    return 1 if any(x["status"] == "BLOCKED" for x in report["lanes"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
