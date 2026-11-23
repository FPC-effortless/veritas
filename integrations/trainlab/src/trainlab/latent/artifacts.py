"""Bound local numerical inputs and deterministic saved-output evidence.

This is an operator-side evidence format, not a private-data sanitizer. Array
loading never enables pickle; bundles contain only explicitly selected inputs.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import io
import json
import math
import platform
import re
import sys
import zipfile
from pathlib import Path

import numpy as np

from ..runner import LabError, _constant, _pairs, contained_file, digest, write_json
from . import SCHEMA

MAX_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,78}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


def require(condition, message):
    if not condition:
        raise LabError(message)


def canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, TypeError, OverflowError, RecursionError) as exc:
        raise LabError("finite bounded JSON data required") from exc


def sha(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def plan_identity(plan):
    content = copy.deepcopy(plan)
    content.get("identities", {}).pop("configuration", None)
    return sha(content)


def validate_plan(plan):
    required = {"schema", "title", "identities", "artifacts", "jobs", "budget"}
    require(
        type(plan) is dict
        and required <= set(plan)
        and set(plan) <= required | {"figures", "provenance", "adapter"}
        and plan["schema"] == SCHEMA,
        "invalid latent plan schema",
    )
    require(
        isinstance(plan["title"], str) and 0 < len(plan["title"]) <= 300, "bounded title required"
    )
    identities = plan["identities"]
    require(
        type(identities) is dict
        and set(identities) == {"model", "dataset", "code", "configuration"}
        and all(isinstance(v, str) and HASH.fullmatch(v) for v in identities.values()),
        "four SHA256 identities required",
    )
    require(identities["configuration"] == plan_identity(plan), "plan configuration hash mismatch")
    budget = plan["budget"]
    require(
        type(budget) is dict
        and set(budget) == {"max_calls", "max_seconds"}
        and type(budget["max_calls"]) is int
        and 1 <= budget["max_calls"] <= 10000
        and type(budget["max_seconds"]) in (int, float)
        and np.isfinite(budget["max_seconds"])
        and 0 < budget["max_seconds"] <= 86400,
        "bounded call and time budget required",
    )
    artifacts = plan["artifacts"]
    require(type(artifacts) is dict and len(artifacts) <= 256, "bounded artifact map required")
    for name, item in artifacts.items():
        require(
            NAME.fullmatch(name)
            and type(item) is dict
            and set(item) == {"path", "sha256", "kind"}
            and isinstance(item["sha256"], str)
            and HASH.fullmatch(item["sha256"])
            and item["kind"] in ("npy", "npz", "json", "opaque"),
            "invalid artifact declaration",
        )
    jobs = plan["jobs"]
    require(type(jobs) is list and 1 <= len(jobs) <= 128, "1..128 jobs required")
    seen = set()
    for job in jobs:
        require(
            type(job) is dict
            and {"id", "operation"} <= set(job)
            and set(job) <= {"id", "operation", "args", "kwargs", "role", "unit", "scope"}
            and isinstance(job["id"], str)
            and NAME.fullmatch(job["id"])
            and job["id"] not in seen
            and isinstance(job["operation"], str)
            and NAME.fullmatch(job["operation"]),
            "invalid or duplicate diagnostic job",
        )
        require(
            type(job.get("args", [])) is list and type(job.get("kwargs", {})) is dict,
            "job args and kwargs must be explicit lists/objects",
        )
        require(
            job.get("role", "exploratory") in ("primary", "secondary", "exploratory", "control"),
            "invalid analysis role",
        )
        _references(job.get("args", []), artifacts, seen)
        _references(job.get("kwargs", {}), artifacts, seen)
        seen.add(job["id"])
    require(
        type(plan.get("figures", [])) is list and len(plan.get("figures", [])) <= 64,
        "bounded figure list required",
    )
    figure_ids = set()
    for figure in plan.get("figures", []):
        require(
            type(figure) is dict
            and {"id", "kind", "data"} <= set(figure)
            and isinstance(figure["id"], str)
            and NAME.fullmatch(figure["id"])
            and figure["id"] not in figure_ids,
            "invalid or duplicate figure declaration",
        )
        figure_ids.add(figure["id"])
        _references(figure, artifacts, seen)
    if "adapter" in plan:
        item = plan["adapter"]
        require(
            type(item) is dict
            and set(item) == {"path", "sha256", "factory"}
            and isinstance(item["sha256"], str)
            and HASH.fullmatch(item["sha256"])
            and isinstance(item["factory"], str)
            and item["factory"].isidentifier()
            and not item["factory"].startswith("_"),
            "invalid trusted adapter declaration",
        )
    require(len(canonical(plan)) <= 16 * 1024 * 1024, "plan too large")
    return plan


def _references(value, artifacts, earlier, depth=0):
    require(depth <= 32, "reference nesting exceeds bound")
    if isinstance(value, list):
        for item in value:
            _references(item, artifacts, earlier, depth + 1)
    elif isinstance(value, dict):
        if "literal" in value:
            require(set(value) == {"literal"}, "literal wrapper takes exactly one field")
            require(
                len(canonical(value["literal"])) <= 16 * 1024 * 1024, "literal exceeds size bound"
            )
            return
        if "bytes_hex" in value:
            require(
                set(value) == {"bytes_hex"}
                and isinstance(value["bytes_hex"], str)
                and len(value["bytes_hex"]) <= 131072
                and len(value["bytes_hex"]) % 2 == 0
                and re.fullmatch("[0-9a-fA-F]*", value["bytes_hex"]) is not None,
                "bounded hex byte literal required",
            )
            return
        if "artifact" in value:
            require(
                set(value) <= {"artifact", "key", "path"} and value["artifact"] in artifacts,
                "unknown artifact reference",
            )
        elif "result" in value:
            require(
                set(value) <= {"result", "path"} and value["result"] in earlier,
                "results must reference an earlier job",
            )
        elif "capability" in value:
            require(
                set(value) <= {"capability", "normalize", "context"}
                and isinstance(value["capability"], str)
                and NAME.fullmatch(value["capability"])
                and type(value.get("normalize", False)) is bool,
                "invalid callback capability reference",
            )
            _references(value.get("context", {}), artifacts, earlier, depth + 1)
        else:
            for item in value.values():
                _references(item, artifacts, earlier, depth + 1)
        if "path" in value and ("artifact" in value or "result" in value):
            require(
                type(value["path"]) is list
                and len(value["path"]) <= 32
                and all(type(k) in (str, int) for k in value["path"]),
                "invalid result path",
            )


def freeze(plan, directory, destination):
    """Pin declared input bytes and configuration without executing anything."""
    plan = copy.deepcopy(plan)
    root, destination = Path(directory).resolve(), Path(destination)
    require(not destination.exists(), "refusing to overwrite frozen plan")
    require(destination.parent.resolve() == root, "plan must live beside its declared input root")
    for item in plan["artifacts"].values():
        item["sha256"] = digest(contained_file(root, item["path"]))
    if "adapter" in plan:
        plan["adapter"]["sha256"] = digest(contained_file(root, plan["adapter"]["path"]))
    plan["identities"]["configuration"] = plan_identity(plan)
    validate_plan(plan)
    write_json(destination, plan)
    return plan


def _array(array):
    require(
        isinstance(array, np.ndarray)
        and array.dtype.kind in "biufUS"
        and array.ndim <= 8
        and array.nbytes <= MAX_BYTES,
        "unsupported or oversized array",
    )
    if array.dtype.kind in "f":
        require(np.isfinite(array).all(), "nonfinite array")
    return array.copy()


def _array_header(stream):
    version = np.lib.format.read_magic(stream)
    require(version in ((1, 0), (2, 0)), "unsupported NPY format version")
    reader = (
        np.lib.format.read_array_header_1_0
        if version == (1, 0)
        else np.lib.format.read_array_header_2_0
    )
    shape, _fortran, dtype = reader(stream, max_header_size=10000)
    require(
        len(shape) <= 8
        and dtype.kind in "biufUS"
        and math.prod(shape) * dtype.itemsize <= MAX_BYTES,
        "unsupported or oversized declared array",
    )


def pinned_bytes(directory, item, *, maximum=MAX_BYTES):
    """Read once, then authenticate the same bounded bytes that will be parsed."""
    path = contained_file(Path(directory), item["path"])
    with path.open("rb") as stream:
        payload = stream.read(maximum + 1)
    require(
        len(payload) <= maximum and hashlib.sha256(payload).hexdigest() == item["sha256"],
        "input artifact hash/size mismatch",
    )
    return payload


def pinned_json(directory, item):
    payload = pinned_bytes(directory, item, maximum=16 * 1024 * 1024)
    try:
        return json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise LabError("invalid JSON document") from exc


def load_inputs(plan, directory):
    result, total = {}, 0
    for name, item in plan["artifacts"].items():
        payload = pinned_bytes(
            directory, item, maximum=16 * 1024 * 1024 if item["kind"] == "json" else MAX_BYTES
        )
        if item["kind"] == "opaque":
            data = {"kind": "opaque", "sha256": item["sha256"], "bytes": len(payload)}
            total += len(payload)
        elif item["kind"] == "json":
            try:
                data = json.loads(payload, object_pairs_hook=_pairs, parse_constant=_constant)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise LabError("invalid JSON document") from exc
            total += len(canonical(data))
        elif item["kind"] == "npy":
            _array_header(io.BytesIO(payload))
            data = _array(np.load(io.BytesIO(payload), allow_pickle=False))
            total += data.nbytes
        else:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                members = archive.infolist()
                require(
                    len(members) <= 256
                    and len({m.filename for m in members}) == len(members)
                    and all(
                        m.filename.endswith(".npy") and NAME.fullmatch(m.filename[:-4])
                        for m in members
                    )
                    and sum(m.file_size for m in members) <= MAX_BYTES,
                    "unsafe or oversized numerical archive",
                )
                for member in members:
                    with archive.open(member) as stream:
                        _array_header(stream)
            with np.load(io.BytesIO(payload), allow_pickle=False) as archive:
                data = {key: _array(archive[key]) for key in archive.files}
            total += sum(value.nbytes for value in data.values())
        require(total <= MAX_TOTAL_BYTES, "total input budget exceeded")
        result[name] = data
    return result


def select(value, path):
    for key in path:
        try:
            value = value[key]
        except (KeyError, IndexError, TypeError) as exc:
            raise LabError("missing result/reference path") from exc
    return value


def resolve(value, inputs, results, *, callback=None):
    if isinstance(value, list):
        return [resolve(item, inputs, results, callback=callback) for item in value]
    if isinstance(value, dict):
        if "literal" in value:
            return copy.deepcopy(value["literal"])
        if "bytes_hex" in value:
            return bytes.fromhex(value["bytes_hex"])
        if "artifact" in value:
            result = inputs[value["artifact"]]
            if "key" in value:
                result = select(result, [value["key"]])
            return copy.deepcopy(select(result, value.get("path", [])))
        if "result" in value:
            require(value["result"] in results, "dependency did not produce a result")
            return copy.deepcopy(select(results[value["result"]], value.get("path", [])))
        if "capability" in value:
            require(callback is not None, "native callbacks are unavailable during offline replay")
            context = resolve(value.get("context", {}), inputs, results, callback=callback)
            return callback(value["capability"], value.get("normalize", False), context)
        return {
            key: resolve(item, inputs, results, callback=callback) for key, item in value.items()
        }
    return value


def encode_result(value, root, name):
    """Persist finite results and arrays with deterministic bytes, without pickle."""
    root = Path(root)
    require(isinstance(name, str) and NAME.fullmatch(name), "bounded result name required")
    arrays = []

    def encode(item, depth=0):
        require(depth <= 32, "result nesting exceeds bound")
        if isinstance(item, np.ndarray):
            array = _array(item)
            filename = f"{name}.array-{len(arrays):04d}.npy"
            stream = io.BytesIO()
            np.save(stream, array, allow_pickle=False)
            data = stream.getvalue()
            path = root / filename
            require(not path.exists(), "refusing to overwrite numerical result")
            path.write_bytes(data)
            arrays.append(filename)
            return {
                "$array": filename,
                "shape": list(array.shape),
                "dtype": array.dtype.str,
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        if isinstance(item, np.generic):
            return encode(item.item(), depth + 1)
        if isinstance(item, bytes):
            require(len(item) <= 65536, "result byte literal exceeds bound")
            return {"$bytes": item.hex()}
        if isinstance(item, (tuple, list)):
            return [encode(entry, depth + 1) for entry in item]
        if isinstance(item, dict):
            require(all(isinstance(key, str) for key in item), "result keys must be strings")
            # Array filenames follow canonical key order, including after a
            # saved JSON object has been reloaded with sorted keys.
            mapping = {key: encode(item[key], depth + 1) for key in sorted(item)}
            return (
                {"$mapping": mapping} if set(item) & {"$array", "$bytes", "$mapping"} else mapping
            )
        require(
            item is None or type(item) in (str, bool, int, float),
            "diagnostics must return finite JSON values and numeric/string arrays",
        )
        canonical(item)
        return item

    result = encode(value)
    require(len(canonical(result)) <= 16 * 1024 * 1024, "result JSON exceeds size bound")
    write_json(root / f"{name}.json", {"value": result})
    return result


def decode_result(value, root):
    if isinstance(value, dict) and set(value) == {"$mapping"}:
        require(type(value["$mapping"]) is dict, "invalid escaped result mapping")
        return {key: decode_result(item, root) for key, item in value["$mapping"].items()}
    if isinstance(value, dict) and set(value) == {"$bytes"}:
        return bytes.fromhex(value["$bytes"])
    if isinstance(value, dict) and "$array" in value:
        payload = pinned_bytes(root, {"path": value["$array"], "sha256": value["sha256"]})
        _array_header(io.BytesIO(payload))
        result = _array(np.load(io.BytesIO(payload), allow_pickle=False))
        require(
            list(result.shape) == value["shape"] and result.dtype.str == value["dtype"],
            "saved array metadata mismatch",
        )
        return result
    if isinstance(value, dict):
        return {key: decode_result(item, root) for key, item in value.items()}
    if isinstance(value, list):
        return [decode_result(item, root) for item in value]
    return value


def implementation_identity():
    root = Path(__file__).parent
    files = {
        p.relative_to(root.parent).as_posix(): digest(p) for p in sorted(root.parent.rglob("*.py"))
    }
    files.update(
        {
            p.relative_to(root.parent).as_posix(): digest(p)
            for p in sorted((root / "static").glob("*"))
        }
    )
    versions = {}
    for distribution in ("numpy", "scipy", "scikit-learn", "torch", "matplotlib", "reportlab"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = None
    return {
        "sha256": sha(files),
        "files": files,
        "python": platform.python_version(),
        "numpy": np.__version__,
        "dependencies": versions,
        "platform": sys.platform,
        "machine": platform.machine(),
        "scope": "TrainLab Python source, templates and package versions; not an OS attestation",
    }


def inventory(root):
    root = Path(root)
    rows = []
    for path in sorted(root.rglob("*")):
        require(not path.is_symlink(), "evidence bundles cannot contain symlinks")
        if path.is_file() and path.relative_to(root).as_posix() not in {
            "bundle.json",
            "SHA256SUMS",
        }:
            rows.append(
                {
                    "path": path.relative_to(root).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": digest(path),
                }
            )
    return rows


def seal_bundle(root, *, plan_sha256, implementation, state):
    root = Path(root)
    document = {
        "schema": "trainlab.latent-bundle.v1",
        "plan_sha256": plan_sha256,
        "implementation": implementation,
        "state": state,
        "files": inventory(root),
        "scientific_qualification": "NOT_QUALIFIED",
    }
    write_json(root / "bundle.json", document)
    (root / "SHA256SUMS").write_text(
        "".join(f"{row['sha256']}  {row['path']}\n" for row in document["files"]), encoding="utf-8"
    )
    return digest(root / "bundle.json")


def verify_bundle(root, expected_sha256):
    root = Path(root)
    require(
        isinstance(expected_sha256, str) and HASH.fullmatch(expected_sha256),
        "external bundle SHA256 required",
    )
    doc = pinned_json(root, {"path": "bundle.json", "sha256": expected_sha256})
    require(doc.get("schema") == "trainlab.latent-bundle.v1", "invalid bundle schema")
    require(inventory(root) == doc["files"], "evidence inventory/hash mismatch")
    checksum = "".join(f"{row['sha256']}  {row['path']}\n" for row in doc["files"])
    require(
        contained_file(root, "SHA256SUMS").read_text(encoding="utf-8") == checksum,
        "checksum list mismatch",
    )
    return doc
