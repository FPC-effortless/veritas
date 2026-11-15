"""Inspect exact runtime files without importing them; never authorize execution.

A local byte/mode snapshot is not immutable custody, loader closure, sandboxing,
rights clearance or permission to import native code. Call only on trusted local
paths. Policy and roots must come from the operator, not candidate code.
"""

from __future__ import annotations

import hashlib
import os
import stat
from pathlib import Path, PurePosixPath

from .prediction_artifacts import _bytes, _hash, _require, _text
from .runner import LabError

MAX_FILES = 20000
MAX_ENTRIES = 40000
MAX_BYTES = 2 * 1024**3
ENVIRONMENT = {
    "TORCH_DEVICE_BACKEND_AUTOLOAD": "0",
    "OMP_NUM_THREADS": "1",
    "MKL_NUM_THREADS": "1",
    "OPENBLAS_NUM_THREADS": "1",
    "PYTHONDONTWRITEBYTECODE": "1",
}
FLAGS = ["-I", "-S", "-B"]


def _path(path):
    value = Path(path)
    _require(value.is_absolute(), "absolute runtime path required")
    _require(
        not any(p.is_symlink() for p in (value, *value.parents)),
        "runtime paths and ancestors must not be symlinks",
    )
    try:
        resolved = value.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise LabError("runtime path missing or unresolvable") from exc
    _require(value == resolved, "canonical runtime path required")
    return value


def _file(path, expected, remaining):
    _require(
        type(expected) is dict
        and set(expected) == {"sha256", "bytes", "mode"}
        and _hash(expected["sha256"])
        and type(expected["bytes"]) is int
        and 0 <= expected["bytes"] <= remaining
        and type(expected["mode"]) is int
        and 0 <= expected["mode"] <= 0o777,
        "bounded exact file identity required",
    )
    path = _path(path)
    before = path.lstat()
    _require(
        stat.S_ISREG(before.st_mode)
        and before.st_size == expected["bytes"]
        and stat.S_IMODE(before.st_mode) == expected["mode"],
        "runtime file kind, size or mode changed",
    )
    hasher = hashlib.sha256()
    count = 0
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        _require(
            (opened.st_dev, opened.st_ino) == (before.st_dev, before.st_ino),
            "runtime file replaced before read",
        )
        while block := stream.read(min(1024**2, expected["bytes"] - count + 1)):
            count += len(block)
            _require(count <= expected["bytes"], "runtime file grew during read")
            hasher.update(block)
        after = os.fstat(stream.fileno())
    last = path.lstat()
    keys = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns", "st_mode")
    _require(
        all(getattr(before, k) == getattr(after, k) == getattr(last, k) for k in keys),
        "runtime file changed during observation",
    )
    _require(
        count == expected["bytes"] and hasher.hexdigest() == expected["sha256"],
        "runtime file bytes changed",
    )
    return count


def inspect_runtime(root, interpreter, policy, *, policy_sha256):
    """Check a bounded operator-pinned layout; do not launch or import any code.

    Includes every regular file under root and rejects links/special files. Empty
    directories are not bound. Native dependencies outside this tree are unknown.
    Flags/environment are checked proposed values, not observed process behavior.
    """
    _require(
        _hash(policy_sha256) and hashlib.sha256(_bytes(policy)).hexdigest() == policy_sha256,
        "runtime policy identity changed",
    )
    _require(
        type(policy) is dict
        and set(policy)
        == {"schema", "root", "interpreter", "files", "flags", "environment", "sys_path"}
        and policy["schema"] == "trainlab.runtime-preflight.v1",
        "invalid runtime policy",
    )
    root, interpreter = _path(root), _path(interpreter)
    _require(root.is_dir() and policy["root"] == str(root), "runtime root changed")
    pin = policy["interpreter"]
    _require(
        type(pin) is dict and set(pin) == {"path", "identity"} and pin["path"] == str(interpreter),
        "interpreter binding changed",
    )
    _require(
        policy["flags"] == FLAGS and policy["environment"] == ENVIRONMENT,
        "isolated startup flags and explicit backend autoload disable required",
    )
    paths = policy["sys_path"]
    _require(
        type(paths) is list
        and len(paths) == 3
        and len(set(paths)) == 3
        and paths[-1] == str(root)
        and all(_text(p) for p in paths),
        "three distinct explicit import roots required",
    )
    for p in paths:
        _require(_path(p).is_dir(), "import roots must be existing canonical directories")
    files = policy["files"]
    _require(
        type(files) is dict and 1 <= len(files) <= MAX_FILES, "bounded runtime inventory required"
    )
    for name in files:
        _require(
            type(name) is str
            and name
            and "\\" not in name
            and "\0" not in name
            and not PurePosixPath(name).is_absolute()
            and all(c not in ("", ".", "..") for c in name.split("/")),
            "safe relative runtime member required",
        )
    found = set()
    visited = 0

    def walk_error(error):
        raise LabError("runtime inventory traversal incomplete") from error

    for directory, dirs, names in os.walk(root, followlinks=False, onerror=walk_error):
        visited += len(dirs) + len(names)
        _require(visited <= MAX_ENTRIES, "runtime traversal exceeds entry bound")
        for name in dirs + names:
            p = Path(directory) / name
            mode = p.lstat().st_mode
            _require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), "link or special runtime member")
            if stat.S_ISREG(mode):
                found.add(p.relative_to(root).as_posix())
                _require(len(found) <= MAX_FILES, "runtime inventory exceeds bound")
    _require(found == set(files), "runtime inventory has extra or missing files")
    total = _file(interpreter, pin["identity"], MAX_BYTES)
    for name in sorted(files):
        total += _file(root / name, files[name], MAX_BYTES - total)
    return {
        "schema": "trainlab.runtime-preflight-report.v1",
        "policy_sha256": policy_sha256,
        "status": "STATIC_LAYOUT_MATCH",
        "files": len(files),
        "observed_bytes": total,
        "native_execution_admitted": False,
        "runtime_viability": "UNTESTED",
        "isolation": "NOT_DEMONSTRATED",
        "scientific_qualification": "NOT_QUALIFIED",
        "external_import_root_contents": "UNVERIFIED",
        "inventory_atomicity": "NON_ATOMIC_SEQUENTIAL_OBSERVATION",
        "scope": "Enumerated file bytes/modes observed non-atomically; "
        "later additions may be missed. "
        "Paths, environment and flags are proposed. "
        "No import, loader closure, immutable custody, rights, authorization or containment proof.",
    }


def require_native_admission(report):
    """A static receipt cannot authorize native execution, regardless of caller flags."""
    raise LabError(
        "Native admission unavailable: static runtime preflight is not execution authority"
    )
