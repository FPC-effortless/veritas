"""Offline run-store backup/restore and aggregate operational health."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from .runner import (
    MAX_ACTIVE_RUNS,
    LabError,
    _relative,
    contained_file,
    digest,
    read_json,
    validate_record,
    verify_run,
    write_json,
)

MAX_BACKUP_BYTES = 2 * 1024 * 1024 * 1024
MAX_BACKUP_FILES = 8192


@contextmanager
def _pinned_archive(path, expected_sha256, max_bytes):
    # Keep one inode open across verification and extraction: replacing the
    # pathname cannot silently substitute a different, unpinned archive.
    with path.open("rb") as source:
        metadata = os.fstat(source.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > max_bytes + 16 * 1024 * 1024:
            raise LabError("backup must be a bounded regular file")

        def check():
            source.seek(0)
            hasher = hashlib.sha256()
            for block in iter(lambda: source.read(65536), b""):
                hasher.update(block)
            if hasher.hexdigest() != expected_sha256:
                raise LabError("backup SHA256 mismatch or archive changed during restore")
            source.seek(0)

        check()
        yield source
        check()


def recover_run(directory: Path, *, confirm_no_running_jobs: bool = False) -> dict:
    """Offline operator recovery; never infer liveness or resume training."""
    if confirm_no_running_jobs is not True:
        raise LabError("stop all jobs and explicitly confirm offline recovery")
    record = read_json(contained_file(directory, "run.json"))
    validate_record(record)
    if record["status"] != "running" or record["id"] != directory.name:
        raise LabError("only an unfinished run in its original directory can be recovered")
    record.update(
        status="interrupted",
        finished_at=datetime.now(timezone.utc).isoformat(),
        elapsed_seconds=None,
        metrics={},
        artifacts={},
        files={},
        error="Recovered offline after operator confirmed all jobs were stopped; not resumed.",
    )
    for name in ("experiment.json", "stdout.log", "stderr.log", "output/metrics.json"):
        try:
            record["files"][name] = digest(contained_file(directory, name))
        except (LabError, OSError):
            pass
    if "experiment.json" not in record["files"]:
        raise LabError("cannot recover without the saved experiment")
    write_json(directory / "run.json", record)
    return record


def _records(root: Path):
    if not root.is_dir() or root.is_symlink():
        raise LabError("run store must be an existing regular directory")
    for directory in sorted(root.iterdir()):
        if not directory.is_dir() or directory.is_symlink():
            raise LabError("run store contains an unsupported entry")
        record = read_json(contained_file(root, directory.name + "/run.json"))
        validate_record(record)
        if record["id"] != directory.name:
            raise LabError("run directory identity mismatch")
        yield directory, record


def store_health(root: Path) -> dict:
    """Aggregate health only. This is not full integrity or scientific verification."""
    counts = {"runs": 0, "unfinished": 0, "invalid": 0}
    try:
        if not root.exists():
            return {"status": "degraded", **counts, "reason": "run store unavailable"}
        # Read individually so corrupt metadata is visible without exposing paths.
        for directory in root.iterdir():
            counts["runs"] += 1
            if counts["runs"] > MAX_ACTIVE_RUNS:
                return {
                    "status": "degraded",
                    **counts,
                    "reason": "active run store capacity exceeded",
                }
            try:
                record = read_json(contained_file(root, directory.name + "/run.json"))
                validate_record(record)
                if record["id"] != directory.name:
                    raise LabError("identity mismatch")
                counts["unfinished"] += record["status"] == "running"
            except (LabError, OSError):
                counts["invalid"] += 1
        free = shutil.disk_usage(root).free
        return {
            "status": "degraded" if counts["invalid"] or free < 64 * 1024 * 1024 else "ok",
            **counts,
            "free_bytes": free,
        }
    except OSError:
        return {"status": "degraded", **counts, "reason": "run store unavailable"}


def backup_runs(root: Path, destination: Path, *, max_bytes: int = MAX_BACKUP_BYTES) -> dict:
    """Back up finalized verified records only; recipes/source inputs are separate."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise LabError("backup size limit must be positive")
    if destination.exists() or destination.is_symlink():
        raise LabError("backup destination already exists")
    root = root.absolute()
    paths = []
    runs = 0
    for directory, record in _records(root):
        if not verify_run(directory)["valid"]:
            raise LabError("run integrity verification failed")
        names = {"run.json", *record["files"], *("output/" + name for name in record["artifacts"])}
        for name in sorted(names):
            paths.append((contained_file(directory, name), directory.name + "/" + name))
        runs += 1
    if len(paths) > MAX_BACKUP_FILES or sum(path.stat().st_size for path, _ in paths) > max_bytes:
        raise LabError("backup exceeds supported file or byte limit")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix=".backup-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            manifest = {"schema": "trainlab.backup.v1", "runs": runs, "files": {}}
            with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_STORED) as archive:
                total = 0
                for path, name in paths:
                    hasher = hashlib.sha256()
                    with path.open("rb") as source, archive.open(name, "w") as output:
                        while block := source.read(65536):
                            total += len(block)
                            if total > max_bytes:
                                raise LabError("backup changed or exceeds byte limit")
                            output.write(block)
                            hasher.update(block)
                    manifest["files"][name] = hasher.hexdigest()
                archive.writestr("backup-manifest.json", json.dumps(manifest, sort_keys=True))
            stream.flush()
            os.fsync(stream.fileno())
        # Verify the captured bytes, not merely the source before copying.
        with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".backup-check-") as check:
            restore_runs(
                temporary,
                Path(check) / "runs",
                expected_sha256=digest(temporary),
                max_bytes=max_bytes,
            )
        # Hard-link publication refuses an existing destination even under races.
        os.link(temporary, destination)
        return {
            "archive": str(destination),
            "sha256": digest(destination),
            "runs": runs,
            "scope": "FINALIZED_RUN_RECORDS_ONLY",
            "qualification": "NOT_QUALIFIED",
        }
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def restore_runs(
    archive_path: Path,
    destination: Path,
    *,
    expected_sha256: str,
    max_bytes: int = MAX_BACKUP_BYTES,
) -> dict:
    """Restore offline to a new store, checking a separately retained archive pin."""
    if type(max_bytes) is not int or max_bytes <= 0:
        raise LabError("restore size limit must be positive")
    if destination.exists() or destination.is_symlink():
        raise LabError("restore destination already exists")
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".restore-") as temporary:
        stage = Path(temporary) / "runs"
        stage.mkdir(mode=0o700)
        try:
            with (
                _pinned_archive(archive_path, expected_sha256, max_bytes) as source_archive,
                zipfile.ZipFile(source_archive) as archive,
            ):
                entries = archive.infolist()
                names = [entry.filename for entry in entries]
                if (
                    len(entries) > MAX_BACKUP_FILES + 1
                    or len(set(names)) != len(names)
                    or sum(entry.file_size for entry in entries) > max_bytes + 2 * 1024 * 1024
                ):
                    raise LabError("unsafe or oversized backup")
                manifest_entry = archive.getinfo("backup-manifest.json")
                if manifest_entry.file_size > 2 * 1024 * 1024:
                    raise LabError("backup manifest too large")
                manifest = json.loads(archive.read(manifest_entry))
                if (
                    not isinstance(manifest, dict)
                    or manifest.get("schema") != "trainlab.backup.v1"
                    or not isinstance(manifest.get("files"), dict)
                    or set(manifest["files"]) != set(names) - {"backup-manifest.json"}
                ):
                    raise LabError("invalid backup manifest")
                total = 0
                for entry in entries:
                    if entry.filename == "backup-manifest.json":
                        continue
                    _relative(entry.filename)
                    mode = entry.external_attr >> 16
                    if (
                        entry.is_dir()
                        or stat.S_ISLNK(mode)
                        or (stat.S_IFMT(mode) not in (0, stat.S_IFREG))
                    ):
                        raise LabError("backup contains unsupported entries")
                    target = stage / entry.filename
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    hasher = hashlib.sha256()
                    with archive.open(entry) as source, target.open("xb") as output:
                        os.chmod(target, 0o600)
                        while block := source.read(65536):
                            total += len(block)
                            if total > max_bytes:
                                raise LabError("restore exceeds byte limit")
                            output.write(block)
                            hasher.update(block)
                        output.flush()
                        os.fsync(output.fileno())
                    if hasher.hexdigest() != manifest["files"][entry.filename]:
                        raise LabError("backup file hash mismatch")
            records = list(_records(stage))
            if len(records) != manifest.get("runs"):
                raise LabError("backup run count mismatch")
            if any(not verify_run(directory)["valid"] for directory, _ in records):
                raise LabError("restored run verification failed")
        except (ValueError, KeyError, zipfile.BadZipFile, RuntimeError) as error:
            raise LabError("invalid or corrupt backup") from error
        # Destination is exclusively created only AFTER all bytes validate.
        # Restore is an offline operation; do not point a server at it mid-restore.
        destination.mkdir(mode=0o700)
        try:
            for directory in stage.iterdir():
                directory.rename(destination / directory.name)
        except OSError:
            shutil.rmtree(destination)
            raise
    return {"runs": len(records), "integrity": "PASS", "qualification": "NOT_QUALIFIED"}
