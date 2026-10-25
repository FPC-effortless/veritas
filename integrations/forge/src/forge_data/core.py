"""Small fail-closed data release boundary for authentic chronological episode exports.

Never imputes missing labels, invents observations, or certifies that input data is real.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import os
import shutil
import tempfile
from pathlib import Path

SCHEMA = "forge.temporal.v0.1"
SPLITS = ("train", "validation", "test")


class ForgeError(ValueError):
    """Invalid data or unsupported release contract."""


def canonical(obj: object) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")


def hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _nonempty(obj: dict, field: str) -> str:
    value = obj.get(field)
    if not isinstance(value, str) or not value.strip():
        raise ForgeError(f"{field} must be a non-empty string")
    return value


def _timestamp(value: object, name: str) -> str:
    if not isinstance(value, str):
        raise ForgeError(f"{name} must be an offset-aware timestamp")
    try:
        moment = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ForgeError(f"{name} is not a valid timestamp") from exc
    if moment.utcoffset() is None:
        raise ForgeError(f"{name} must carry an explicit UTC offset")
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _seconds(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ForgeError(f"{name} must be a finite nonnegative number")
    v = float(value)
    if not math.isfinite(v) or v < 0:
        raise ForgeError(f"{name} must be a finite nonnegative number")
    return v


def _payload(value: object, name: str) -> dict:
    if not isinstance(value, dict):
        raise ForgeError(f"{name} must be an object")
    canonical(value)
    return value


def _outcome(row: dict, temporal: str) -> dict:
    obj = row.get("outcome")
    if obj is None:
        return {"status": "unknown", "verified": False, "available_at": None}
    if not isinstance(obj, dict):
        raise ForgeError("outcome must be an object or null")
    status = _nonempty(obj, "status")
    if status == "unknown":
        if obj.get("verified", False) is not False:
            raise ForgeError("unknown outcomes cannot be verified")
        if obj.get("value") is not None:
            raise ForgeError("unknown outcomes cannot carry an observed value")
    verified = obj.get("verified")
    if not isinstance(verified, bool):
        raise ForgeError("outcome.verified must be boolean")
    at = obj.get("available_at")
    if status != "unknown" and at is None:
        raise ForgeError("known outcome requires availability timestamp")
    parsed = (_timestamp(at, "outcome.available_at") if temporal == "absolute"
              else _seconds(at, "outcome.available_at")) if at is not None else None
    return {"status": status, "verified": verified, "available_at": parsed,
            "value": obj.get("value")}


def normalize(row: dict, *, adapter: str, source_id: str) -> dict:
    if not isinstance(row, dict):
        raise ForgeError("source row must be an object")
    episode_id = _nonempty(row, "episode_id")
    subject_id = _nonempty(row, "subject_id")
    record_id = _nonempty(row, "record_id")
    observation = _payload(row.get("observation"), "observation")
    action = row.get("action")
    if action is not None and not isinstance(action, dict):
        raise ForgeError("action must be an object or null")
    if adapter == "operations-jsonl":
        temporal = "absolute"
        observed_at = _timestamp(row.get("observed_at"), "observed_at")
        available_at = _timestamp(row.get("available_at"), "available_at")
        if available_at < observed_at:
            raise ForgeError("available_at cannot precede observed_at")
        action_at = _timestamp(action.get("performed_at"), "action.performed_at") if action else None
        if action and action_at < observed_at:
            raise ForgeError("action cannot precede observation")
    elif adapter == "robot-jsonl":
        temporal = "relative_seconds"
        observed_at = _seconds(row.get("time_seconds"), "time_seconds")
        available_at = _seconds(row.get("available_seconds"), "available_seconds")
        if available_at < observed_at:
            raise ForgeError("available_seconds cannot precede time_seconds")
        action_at = _seconds(action.get("time_seconds"), "action.time_seconds") if action else None
        if action and action_at < observed_at:
            raise ForgeError("action cannot precede observation")
        frame = row.get("frame_index")
        if isinstance(frame, bool) or not isinstance(frame, int) or frame < 0:
            raise ForgeError("robot row requires nonnegative frame_index")
    else:
        raise ForgeError(f"unsupported adapter: {adapter}")
    outcome = _outcome(row, temporal)
    if outcome["available_at"] is not None and outcome["available_at"] < observed_at:
        raise ForgeError("outcome availability cannot precede observation")
    if action_at is not None and outcome["available_at"] is not None and outcome["available_at"] < action_at:
        raise ForgeError("outcome availability cannot precede recorded action")
    return {
        "schema": SCHEMA, "adapter": adapter, "source_id": source_id,
        "episode_id": episode_id, "subject_id": subject_id, "record_id": record_id,
        "temporal_basis": temporal, "observed_at": observed_at,
        "available_at": available_at, "observation": observation,
        "action": ({"performed_at": action_at, "payload": _payload(action.get("payload"), "action.payload")}
                   if action is not None else None), "outcome": outcome,
        "frame_index": row["frame_index"] if adapter == "robot-jsonl" else None,
    }


def _spec(spec: dict) -> dict:
    if not isinstance(spec, dict):
        raise ForgeError("spec must be an object")
    for field in ("dataset_id", "source_id", "source_version", "license_id", "provenance_uri"):
        _nonempty(spec, field)
    if spec.get("ai_use_allowed") is not True or spec.get("redistribution_allowed") is not True:
        raise ForgeError("explicit source AI-use and redistribution permission required")
    if spec.get("privacy_reviewed") is not True:
        raise ForgeError("privacy_reviewed must be true after source-specific review")
    if spec.get("adapter") not in ("robot-jsonl", "operations-jsonl"):
        raise ForgeError("adapter must be robot-jsonl or operations-jsonl")
    if not isinstance(spec.get("split_salt"), str) or not spec["split_salt"]:
        raise ForgeError("split_salt is required")
    return spec


def _assign(groups: set[str], salt: str) -> dict[str, str]:
    ordered = sorted(groups, key=lambda group: (hash_bytes((salt + "\0" + group).encode()), group))
    n = len(ordered)
    if n == 0:
        raise ForgeError("no valid source groups")
    if n < 3:
        counts = (n, 0, 0)
    else:
        test = max(1, round(n * 0.1))
        valid = max(1, round(n * 0.1))
        counts = (n - test - valid, valid, test)
        if counts[0] < 1:
            raise ForgeError("insufficient independent groups for split allocation")
    result = {}
    pos = 0
    for split, count in zip(SPLITS, counts):
        for group in ordered[pos:pos + count]:
            result[group] = split
        pos += count
    return result


def point_in_time(record: dict, cutoff: str | float) -> dict | None:
    """Give a temporal observation view without future action or outcome leakage."""
    t = _timestamp(cutoff, "cutoff") if record["temporal_basis"] == "absolute" else _seconds(cutoff, "cutoff")
    if record["available_at"] > t:
        return None
    view = {k: record[k] for k in ("schema", "episode_id", "subject_id", "source_id",
                                    "record_id", "observed_at", "available_at", "observation")}
    action = record["action"]
    view["action"] = action if action and action["performed_at"] <= t else None
    outcome = record["outcome"]
    view["outcome"] = outcome if outcome["available_at"] is not None and outcome["available_at"] <= t else None
    return view


def _filehash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def release(input_path: Path, spec_path: Path, output_dir: Path) -> dict:
    """All-or-nothing deterministic release. Never overwrite an existing output."""
    spec = _spec(json.loads(spec_path.read_text(encoding="utf-8")))
    input_bytes_hash = _filehash(input_path)
    records = []
    seen = set()
    with input_path.open("r", encoding="utf-8") as source:
        for index, line in enumerate(source, 1):
            try:
                row = json.loads(line)
                item = normalize(row, adapter=spec["adapter"], source_id=spec["source_id"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ForgeError(f"line {index}: {exc}") from exc
            identity = (item["source_id"], item["record_id"])
            if identity in seen:
                raise ForgeError(f"duplicate source record id on line {index}")
            seen.add(identity)
            records.append(item)
    if not records:
        raise ForgeError("empty source file")
    by_episode = {}
    for row in records:
        key = (row["source_id"], row["episode_id"])
        previous = by_episode.setdefault(key, row["subject_id"])
        if previous != row["subject_id"]:
            raise ForgeError(f"episode {key!r} changes subject identity")
    groups = {r["source_id"] + "\0" + r["subject_id"] for r in records}
    assignments = _assign(groups, spec["split_salt"])
    records.sort(key=lambda r: (r["source_id"], r["episode_id"],
                                r["observed_at"], r["record_id"]))
    by_split = {k: [] for k in SPLITS}
    for record in records:
        group = record["source_id"] + "\0" + record["subject_id"]
        by_split[assignments[group]].append(record)
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise ForgeError("release output already exists; immutable release required")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".forge-stage-", dir=output_dir.parent))
    try:
        hashes = {}
        for split in SPLITS:
            name = split + ".jsonl"
            contents = b"".join(canonical(row) for row in by_split[split])
            (stage / name).write_bytes(contents)
            hashes[name] = hash_bytes(contents)
        manifest = {
            "schema": SCHEMA, "dataset_id": spec["dataset_id"], "source_id": spec["source_id"],
            "source_version": spec["source_version"], "adapter": spec["adapter"],
            "license_id": spec["license_id"], "provenance_uri": spec["provenance_uri"],
            "rights_declared": {"ai_use_allowed": True, "redistribution_allowed": True,
                                "privacy_reviewed": True},
            "source_sha256": input_bytes_hash, "source_spec_sha256": _filehash(spec_path),
            "split_method": "source+subject-sha256-order-v1", "split_salt": spec["split_salt"],
            "records": {k: len(by_split[k]) for k in SPLITS},
            "groups": {k: len({r["subject_id"] for r in by_split[k]}) for k in SPLITS},
            "file_sha256": hashes,
            "qualification": "schema-and-split-integrity-only; not source authenticity or real-world skill",
        }
        (stage / "manifest.json").write_bytes(canonical(manifest))
        os.replace(stage, output_dir)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return manifest


def verify_release(output_dir: Path) -> dict:
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA:
        raise ForgeError("unsupported release schema")
    groups_map = {}
    records = set()
    for split in SPLITS:
        filename = split + ".jsonl"
        if filename not in manifest["file_sha256"]:
            raise ForgeError("missing declared split")
        path = output_dir / filename
        if _filehash(path) != manifest["file_sha256"][filename]:
            raise ForgeError(f"split file hash mismatch: {filename}")
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        if len(rows) != manifest["records"][split]:
            raise ForgeError(f"record count mismatch: {filename}")
        for row in rows:
            group = (row["source_id"], row["subject_id"])
            record_id = (row["source_id"], row["record_id"])
            if group in groups_map and groups_map[group] != split:
                raise ForgeError("group leaked across splits")
            groups_map[group] = split
            if record_id in records:
                raise ForgeError("source record duplicated across splits")
            records.add(record_id)
    return {"valid": True, "dataset_id": manifest["dataset_id"], "records": len(records)}
