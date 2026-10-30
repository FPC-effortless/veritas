"""Pinned local release snapshots for trainer inputs; no qualification authority.

The caller selects reviewed observation fields. Neither an allowlist nor a hash
can establish source authenticity, label truth, or semantic absence of leakage.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
from pathlib import Path

from .core import (
    SCHEMA,
    SPLITS,
    ForgeError,
    _assign,
    _seconds,
    _timestamp,
    canonical,
    hash_bytes,
    normalize,
    point_in_time,
)

MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024
MANIFEST_FIELDS = {
    "schema",
    "dataset_id",
    "source_id",
    "source_version",
    "adapter",
    "license_id",
    "provenance_uri",
    "rights_declared",
    "source_sha256",
    "source_spec_sha256",
    "split_method",
    "split_salt",
    "records",
    "groups",
    "file_sha256",
    "qualification",
}


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ForgeError("duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise ForgeError("nonfinite JSON number")


def _json(data: bytes):
    try:
        value = json.loads(data, object_pairs_hook=_pairs, parse_constant=_constant)
        canonical(value)  # Also rejects overflowing finite-looking JSON numbers.
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise ForgeError("invalid release JSON") from exc


def _read(root: Path, filename: str, limit: int) -> bytes:
    path = root / filename
    if path.is_symlink() or not path.is_file():
        raise ForgeError("release requires regular files, without symlinks")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ForgeError("release file exceeds supported size")
    return data


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _normalized(row: dict, manifest: dict) -> None:
    if not isinstance(row, dict):
        raise ForgeError("release row must be an object")
    try:
        for key in ("source_id", "subject_id", "episode_id", "record_id"):
            if not isinstance(row[key], str) or not row[key].strip() or "\0" in row[key]:
                raise ForgeError("invalid release identity")
        source = dict(row)
        if manifest["adapter"] == "robot-jsonl":
            source.update(time_seconds=row["observed_at"], available_seconds=row["available_at"])
            if row["action"] is not None:
                source["action"] = {
                    "time_seconds": row["action"]["performed_at"],
                    "available_seconds": row["action"]["available_at"],
                    "payload": row["action"]["payload"],
                }
        expected = normalize(source, adapter=manifest["adapter"], source_id=manifest["source_id"])
        # core represents an originally absent outcome without a value key.
        if "value" not in row["outcome"] and row["outcome"]["status"] == "unknown":
            expected["outcome"].pop("value", None)
        if canonical(expected) != canonical(row):
            raise ForgeError("noncanonical row or release identity mismatch")
        if row["observation"].get("kind") == "woyengi_bitemporal_claim_projection":
            raise ForgeError("unattested Woyengi candidates are not dataset releases")
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ForgeError("invalid normalized release row") from exc


class Dataset:
    """Read an exact, bounded snapshot once; subsequent reads use verified bytes.

    Each split is at most 64 MiB. This deliberately bounded in-memory reader is
    for the existing incubated release format; larger sources need streaming.
    The manifest pin must come from the caller's frozen experiment protocol.
    """

    def __init__(self, directory: Path, *, manifest_sha256: str):
        root = Path(directory)
        if root.is_symlink() or any(parent.is_symlink() for parent in root.absolute().parents):
            raise ForgeError("symlink release paths are unsupported")
        data = _read(root, "manifest.json", MAX_MANIFEST_BYTES)
        if not _hash(manifest_sha256) or hash_bytes(data) != manifest_sha256:
            raise ForgeError("manifest pin mismatch")
        manifest = _json(data)
        if not isinstance(manifest, dict) or set(manifest) != MANIFEST_FIELDS:
            raise ForgeError("unsupported manifest fields")
        if manifest["schema"] != SCHEMA or manifest["adapter"] not in (
            "operations-jsonl",
            "robot-jsonl",
        ):
            raise ForgeError("unsupported release schema or adapter")
        for key in (
            "dataset_id",
            "source_id",
            "source_version",
            "license_id",
            "provenance_uri",
            "split_salt",
        ):
            if (
                not isinstance(manifest[key], str)
                or not manifest[key].strip()
                or "\0" in manifest[key]
            ):
                raise ForgeError("invalid manifest identity")
        if manifest["split_method"] != "source+subject-sha256-order-v1":
            raise ForgeError("unsupported split method")
        if manifest["rights_declared"] != {
            "ai_use_allowed": True,
            "redistribution_allowed": True,
            "privacy_reviewed": True,
        } or any(type(v) is not bool for v in manifest["rights_declared"].values()):
            raise ForgeError("missing operator rights declarations")
        if (
            manifest["qualification"]
            != "schema-and-split-integrity-only; not source authenticity or real-world skill"
        ):
            raise ForgeError("manifest cannot confer qualification")
        if not _hash(manifest["source_sha256"]) or not _hash(manifest["source_spec_sha256"]):
            raise ForgeError("invalid source digest")
        for key in ("records", "groups"):
            counts = manifest[key]
            if (
                not isinstance(counts, dict)
                or set(counts) != set(SPLITS)
                or any(type(v) is not int or v < 0 for v in counts.values())
            ):
                raise ForgeError("invalid declared split counts")
        hashes = manifest["file_sha256"]
        if (
            not isinstance(hashes, dict)
            or set(hashes) != {f"{split}.jsonl" for split in SPLITS}
            or not all(_hash(v) for v in hashes.values())
        ):
            raise ForgeError("invalid split digest declarations")
        by_split = {}
        groups, identities, episodes = {}, set(), {}
        for split in SPLITS:
            name = split + ".jsonl"
            content = _read(root, name, MAX_FILE_BYTES)
            if hash_bytes(content) != hashes[name]:
                raise ForgeError("split digest mismatch")
            rows = [_json(line) for line in content.splitlines()]
            if len(rows) != manifest["records"][split]:
                raise ForgeError("record count mismatch")
            split_groups = set()
            previous = None
            for row in rows:
                _normalized(row, manifest)
                group = row["source_id"] + "\0" + row["subject_id"]
                identity = (row["source_id"], row["record_id"])
                episode = (row["source_id"], row["episode_id"])
                if identity in identities or groups.setdefault(group, split) != split:
                    raise ForgeError("duplicate record or subject split leakage")
                if episodes.setdefault(episode, group) != group:
                    raise ForgeError("episode changes subject identity")
                order = (row["source_id"], row["episode_id"], row["observed_at"], row["record_id"])
                if previous is not None and order < previous:
                    raise ForgeError("release rows are not deterministically ordered")
                previous = order
                identities.add(identity)
                split_groups.add(group)
            if len(split_groups) != manifest["groups"][split]:
                raise ForgeError("group count mismatch")
            by_split[split] = rows
        if not identities or _assign(set(groups), manifest["split_salt"]) != groups:
            raise ForgeError("empty release or inconsistent subject assignment")
        self._manifest = manifest
        self._rows = by_split
        self.manifest_sha256 = manifest_sha256

    def summary(self) -> dict:
        return {
            "manifest_sha256": self.manifest_sha256,
            "records": sum(self._manifest["records"].values()),
            "split_records": dict(self._manifest["records"]),
            "split_groups": dict(self._manifest["groups"]),
            "integrity": "PASS",
            "qualification": "NOT_QUALIFIED",
            "rights": "OPERATOR_DECLARED_ONLY",
        }

    def examples(
        self,
        split: str,
        *,
        cutoff: str | float,
        feature_fields: list[str],
        target_cutoff: str | float | None = None,
        allow_test: bool = False,
    ) -> list[dict]:
        """Select features as-of cutoff, optionally labels at a later, separate clock.

        TEST opt-in is a local guard, never permission to open a protected panel.
        Returned targets retain source verification flags, not Forge attestation.
        """
        if split not in SPLITS or (split == "test" and allow_test is not True):
            raise ForgeError("select train/validation, or explicitly authorize local test access")
        if (
            not isinstance(feature_fields, list)
            or not feature_fields
            or any(not isinstance(key, str) or not key for key in feature_fields)
            or len(set(feature_fields)) != len(feature_fields)
        ):
            raise ForgeError("select distinct observation feature fields")
        # Validate cutoffs even for empty partitions using an existing row.
        sample = next(row for rows in self._rows.values() for row in rows)
        try:
            parse = _timestamp if sample["temporal_basis"] == "absolute" else _seconds
            cutoff = parse(cutoff, "cutoff")
            if target_cutoff is not None:
                target_cutoff = parse(target_cutoff, "target cutoff")
                if target_cutoff < cutoff:
                    raise ForgeError("target cutoff precedes feature cutoff")
        except OverflowError as exc:
            raise ForgeError("cutoff is outside the supported temporal range") from exc
        result = []
        for row in self._rows[split]:
            view = point_in_time(row, cutoff)
            if view is None:
                continue
            if any(key not in view["observation"] for key in feature_fields):
                raise ForgeError("selected observation field is missing")
            label_view = point_in_time(row, target_cutoff) if target_cutoff is not None else view
            outcome = label_view["outcome"]
            target = outcome if outcome and outcome["status"] != "unknown" else None
            result.append(
                {
                    "record_id": row["record_id"],
                    "episode_id": row["episode_id"],
                    "subject_id": row["subject_id"],
                    "features": {
                        key: copy.deepcopy(view["observation"][key]) for key in feature_fields
                    },
                    "target": copy.deepcopy(target),
                }
            )
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Pinned local Forge datasets for trainers")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inspect", "export"):
        command = commands.add_parser(name)
        command.add_argument("--release", type=Path, required=True)
        command.add_argument("--manifest-sha256", required=True)
        if name == "export":
            command.add_argument("--split", choices=SPLITS, required=True)
            command.add_argument("--cutoff", required=True)
            command.add_argument("--target-cutoff")
            command.add_argument("--feature", action="append", required=True)
            command.add_argument("--allow-test", action="store_true")
    args = parser.parse_args()
    try:
        dataset = Dataset(args.release, manifest_sha256=args.manifest_sha256)
        if args.command == "inspect":
            print(json.dumps(dataset.summary(), sort_keys=True))
        else:
            parse = float if dataset._manifest["adapter"] == "robot-jsonl" else str
            examples = dataset.examples(
                args.split,
                cutoff=parse(args.cutoff),
                feature_fields=args.feature,
                target_cutoff=parse(args.target_cutoff) if args.target_cutoff is not None else None,
                allow_test=args.allow_test,
            )
            for example in examples:
                print(canonical(example).decode("utf-8"), end="")
    except (ForgeError, OSError, ValueError) as exc:
        parser.exit(2, f"forge dataset: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
