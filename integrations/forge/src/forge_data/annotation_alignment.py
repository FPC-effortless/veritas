"""Check declared annotation coordinates against bounded, pinned media."""

from __future__ import annotations

import argparse
import json
import stat
import struct
import zlib
from collections import Counter
from pathlib import Path

from .core import ForgeError, hash_bytes
from .dataset import _hash, _json
from .diagnostics import MAX_BYTES, _require, _text
from .quality_diagnostics import _bound, _load
from .semantic_audit import MEDIA_LIMIT, _file_key, _MediaScan, _png, _regular, _wav


class _AlignmentMedia(_MediaScan):
    """Retain only checked dimensions; preserve the audited media read boundary."""

    def __init__(self, root, budget):
        super().__init__(root, budget)
        self.dimensions = {}

    def _inspect(self, kind, relative, pin):
        path = self.root / relative
        try:
            if any(p.is_symlink() for p in (path, *path.parents)):
                return "MEDIA_PATH", "failed"
            info = path.stat()
            if not stat.S_ISREG(info.st_mode):
                return "MEDIA_PATH", "failed"
            if info.st_size > MEDIA_LIMIT:
                return "MEDIA_FILE_LIMIT", "unavailable"
            if info.st_size > self.budget - self.bytes_read:
                return "MEDIA_BUDGET", "unavailable"
            with path.open("rb") as stream:
                data = stream.read(info.st_size)
            self.bytes_read += len(data)
            if (
                len(data) != info.st_size
                or path.stat().st_size != len(data)
                or hash_bytes(data) != pin
            ):
                return "MEDIA_HASH", "failed"
        except FileNotFoundError:
            return "MEDIA_MISSING", "failed"
        except OSError:
            return "MEDIA_READ", "unavailable"
        try:
            if not (_png(data) if kind == "png" else _wav(data)):
                return "MEDIA_PROFILE_UNSUPPORTED", "unavailable"
            dimensions = struct.unpack_from(">II", data, 16) if kind == "png" else (_frames(data),)
        except (ForgeError, ValueError, struct.error, zlib.error):
            return "MEDIA_FORMAT", "failed"
        self.dimensions[(kind, relative, pin)] = dimensions
        return None, "checked"


def _frames(data):
    """Read frame count after the shared PCM parser validates chunk order and alignment."""
    position = 12
    while position < len(data):
        kind, size = struct.unpack_from("<4sI", data, position)
        if kind == b"fmt ":
            alignment = struct.unpack_from("<H", data, position + 20)[0]
        if kind == b"data":
            return size // alignment
        position += 8 + size + size % 2
    raise ForgeError("validated PCM data chunk missing")


def _rules(path, pin, fields):
    _require(_hash(pin) and _regular(path), "rules require a pinned regular file")
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    _require(len(raw) <= MAX_BYTES and hash_bytes(raw) == pin, "rule size/hash mismatch")
    document = _json(raw)
    _bound(document)
    _require(
        type(document) is dict
        and set(document) == {"schema", "rules"}
        and document["schema"] == "forge.annotation-alignment-rules.v1"
        and type(document["rules"]) is list
        and 1 <= len(document["rules"]) <= 16,
        "invalid alignment rules",
    )
    rules = {}
    for rule in document["rules"]:
        _require(
            type(rule) is dict
            and set(rule) == {"media", "annotations", "format"}
            and all(_text(rule[k]) for k in rule)
            and {rule["media"], rule["annotations"]} <= fields
            and rule["media"] != rule["annotations"]
            and rule["annotations"] not in rules
            and rule["format"] in ("png", "wav"),
            "invalid or duplicate alignment rule",
        )
        rules[rule["annotations"]] = rule
    return rules


def _coordinates(value, axes):
    return (
        type(value) is list
        and len(value) == 2 * axes
        and all(type(v) is int and 0 <= v < 2**32 for v in value)
        and all(value[i] < value[i + axes] for i in range(axes))
    )


def audit(
    view,
    rules_path,
    *,
    sha256,
    rules_sha256,
    media_root,
    max_rows=10000,
    max_findings=100,
    max_media_bytes=32 * 1024**2,
):
    """Score a bounded prefix of train/validation records under pinned rules."""
    _require(
        all(
            type(value) is int and 0 <= value <= limit
            for value, limit in (
                (max_rows, 100000),
                (max_findings, 1000),
                (max_media_bytes, 128 * 1024**2),
            )
        ),
        "invalid alignment budget",
    )
    path = Path(view)
    _require(_regular(path), "view requires a regular file")
    document = _load(path, sha256)
    fields = set(document["feature_fields"])
    rules = _rules(Path(rules_path), rules_sha256, fields)
    root = Path(media_root).absolute()
    _require(
        root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
        "media root must be a directory without symlinks",
    )
    media = _AlignmentMedia(root, max_media_bytes)
    findings, unavailable = [], Counter()
    coverage = {
        name: {"rows": 0, "annotation_count": 0, "coordinates_checked": 0} for name in rules
    }
    total = 0
    rows = document["rows"][:max_rows]

    def finding(reason, row, field, index=None):
        nonlocal total
        total += 1
        if len(findings) < max_findings:
            findings.append(
                {
                    "row_id": row["id"],
                    "split": row["split"],
                    "field": field,
                    "annotation_index": index,
                    "reason": reason,
                }
            )

    for row in rows:
        values = row["features"]
        for field, rule in rules.items():
            cov = coverage[field]
            cov["rows"] += 1
            annotations = values.get(field)
            if type(annotations) is not list or len(annotations) > 512:
                finding("INVALID_ANNOTATION_LIST", row, field)
                continue
            kind = rule["format"]
            key = _file_key(values.get(rule["media"]))
            reason, outcome = media.check(kind, key) if key else ("MEDIA_PATH", "failed")
            if outcome == "failed":
                finding(reason, row, field)
            elif outcome == "unavailable":
                unavailable[reason] += 1
            dimensions = media.dimensions.get((kind, *key)) if key else None
            axes = 2 if kind == "png" else 1
            for index, item in enumerate(annotations):
                cov["annotation_count"] += 1
                if not _coordinates(item, axes):
                    finding("INVALID_COORDINATES", row, field, index)
                elif dimensions is not None:
                    cov["coordinates_checked"] += 1
                    if any(
                        endpoint > edge
                        for endpoint, edge in zip(item[axes:], dimensions, strict=True)
                    ):
                        finding("OUTSIDE_MEDIA", row, field, index)
    status = (
        "FAILED"
        if total
        else "NOT_RUN"
        if not rows
        else "INCONCLUSIVE"
        if len(rows) < len(document["rows"]) or unavailable
        else "TESTED"
    )
    return {
        "schema": "forge.annotation-alignment.v1",
        "status": status,
        "input_sha256": sha256,
        "rules_sha256": rules_sha256,
        "coverage": coverage,
        "scanned_rows": len(rows),
        "expected_rows": len(document["rows"]),
        "unavailable": dict(unavailable),
        "bytes_read": media.bytes_read,
        "findings": findings,
        "findings_total": total,
        "findings_omitted": total - len(findings),
        "scientific_qualification": "NOT_QUALIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--rules-sha256", required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--max-findings", type=int, default=100)
    parser.add_argument("--max-media-bytes", type=int, default=32 * 1024**2)
    args = vars(parser.parse_args())
    try:
        print(json.dumps(audit(args.pop("view"), args.pop("rules"), **args), sort_keys=True))
    except (ForgeError, OSError) as exc:
        parser.exit(2, f"alignment audit: {exc}\n")


if __name__ == "__main__":
    main()
