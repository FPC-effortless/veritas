"""Audit declared field constraints and pinned media on a bounded Forge view."""

from __future__ import annotations

import argparse
import csv
import io
import json
import stat
import struct
import wave
import zlib
from pathlib import Path

from .core import ForgeError, canonical, hash_bytes
from .dataset import _hash, _json
from .diagnostics import MAX_BYTES, _require, _text
from .quality_diagnostics import _bound, _load

MEDIA_LIMIT = 4 * 1024**2
IMAGE_LIMIT = 4 * 1024**2
NUMERIC = {"integer", "number"}
FORMATS = {"utf8", "json", "csv", "png", "wav"}
TYPES = {
    "number": (int, float),
    "integer": (int,),
    "string": (str,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
    "file": (dict,),
}


def _regular(path):
    return not any(p.is_symlink() for p in (path, *path.absolute().parents)) and path.is_file()


def _matches(kind, value):
    return type(value) in TYPES[kind]


def _rules(path, pin, fields):
    _require(_hash(pin) and _regular(path), "rules require a pinned regular file")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    _require(len(data) <= MAX_BYTES and hash_bytes(data) == pin, "rule size/hash mismatch")
    rules = _json(data)
    _bound(rules)
    _require(
        type(rules) is dict
        and set(rules) == {"schema", "fields"}
        and rules["schema"] == "forge.semantic-rules.v1"
        and type(rules["fields"]) is dict
        and rules["fields"]
        and set(rules["fields"]) <= set(fields),
        "invalid semantic rule document",
    )
    for field, rule in rules["fields"].items():
        _require(
            type(rule) is dict
            and "type" in rule
            and type(rule["type"]) is str
            and rule["type"] in TYPES
            and set(rule)
            <= {"type", "required", "nullable", "min", "max", "enum", "unit", "format"},
            "invalid field rule",
        )
        kind = rule["type"]
        _require(
            all(type(rule.get(k, False)) is bool for k in ("required", "nullable")),
            "required and nullable must be Boolean",
        )
        for key in ("min", "max"):
            if key in rule:
                _require(kind in NUMERIC and _matches(kind, rule[key]), "invalid numeric bound")
        if "min" in rule and "max" in rule:
            _require(rule["min"] <= rule["max"], "inverted numeric bounds")
        if "enum" in rule:
            values = rule["enum"]
            _require(
                kind != "file"
                and type(values) is list
                and 0 < len(values) <= 128
                and all(_matches(kind, v) for v in values)
                and len({canonical(v) for v in values}) == len(values),
                "invalid enum",
            )
        if "unit" in rule:
            unit = rule["unit"]
            _require(
                kind in NUMERIC
                and type(unit) is dict
                and set(unit) == {"field", "symbol"}
                and _text(unit["field"])
                and _text(unit["symbol"])
                and unit["field"] in fields
                and unit["field"] != field,
                "unit must name a separate declared observation field",
            )
        _require(
            ("format" not in rule and kind != "file")
            or (kind == "file" and type(rule.get("format")) is str and rule["format"] in FORMATS),
            "file rule must declare a supported format",
        )
    return rules["fields"]


def _png(data):
    # Bounded structural and scanline checks for noninterlaced 8-bit PNG.
    _require(data.startswith(b"\x89PNG\r\n\x1a\n"), "invalid PNG signature")
    pos, stride, height, profile = 8, 0, 0, False
    blocks = []
    closed_data = False
    while pos + 12 <= len(data):
        size, kind = struct.unpack_from(">I4s", data, pos)
        end = pos + 12 + size
        _require(
            end <= len(data) and kind.isalpha() and not kind[2:3].islower(), "invalid PNG chunk"
        )
        payload = data[pos + 8 : end - 4]
        _require(
            zlib.crc32(kind + payload) == struct.unpack_from(">I", data, end - 4)[0],
            "invalid PNG CRC",
        )
        if pos == 8:
            _require(kind == b"IHDR" and size == 13, "invalid PNG header")
            width, height, bits, color, compression, filters, interlace = struct.unpack(
                ">IIBBBBB", payload
            )
            depths = {0: (1, 2, 4, 8, 16), 2: (8, 16), 3: (1, 2, 4, 8), 4: (8, 16), 6: (8, 16)}
            _require(
                0 < width < 2**31
                and 0 < height < 2**31
                and bits in depths.get(color, ())
                and compression == filters == 0
                and interlace in (0, 1),
                "invalid PNG dimensions or profile",
            )
            stride = 1 + width * {0: 1, 2: 3, 4: 2, 6: 4}.get(color, 0)
            profile = bits == 8 and color != 3 and interlace == 0 and stride * height <= IMAGE_LIMIT
        elif kind == b"IDAT":
            _require(not closed_data, "nonconsecutive PNG data")
            blocks.append(payload)
        elif kind == b"IEND":
            _require(size == 0 and end == len(data) and blocks, "invalid PNG ending")
            if not profile:
                return False
            limit = stride * height
            decoder = zlib.decompressobj()
            scanlines = decoder.decompress(b"".join(blocks), limit + 1)
            _require(
                len(scanlines) == limit
                and decoder.eof
                and not decoder.unused_data
                and all(scanlines[i] <= 4 for i in range(0, limit, stride)),
                "invalid PNG scanlines",
            )
            return True
        else:
            _require(kind != b"IHDR", "duplicate PNG header")
            if kind == b"PLTE":
                _require(not blocks and 0 < size <= 768 and size % 3 == 0, "invalid PNG palette")
            elif not kind[0:1].islower():
                profile = False
            closed_data = bool(blocks)
        pos = end
    raise ForgeError("incomplete PNG")


def _check_media(kind, data):
    _require(data, "empty media")
    if kind == "png":
        return _png(data)
    if kind == "wav":
        _require(
            len(data) >= 12
            and data[:4] == b"RIFF"
            and data[8:12] == b"WAVE"
            and int.from_bytes(data[4:8], "little") == len(data) - 8,
            "invalid WAV envelope",
        )
        with wave.open(io.BytesIO(data), "rb") as audio:
            frames = audio.getnframes()
            frame_size = audio.getnchannels() * audio.getsampwidth()
            _require(
                frames > 0
                and frame_size > 0
                and audio.getframerate() > 0
                and frames * frame_size <= len(data)
                and len(audio.readframes(frames)) == frames * frame_size,
                "invalid or truncated PCM WAV data",
            )
    elif kind == "json":
        _bound(_json(data.decode("utf-8")))
    else:
        text = data.decode("utf-8-sig")
        _require(bool(text.strip()) and "\0" not in text, "invalid or empty text")
        if kind == "csv":
            rows = csv.reader(io.StringIO(text, newline=""), strict=True)
            headers = next(rows, [])
            _require(
                bool(headers)
                and all(h.strip() for h in headers)
                and len(set(headers)) == len(headers),
                "invalid CSV header",
            )
            for row in rows:
                _require(len(row) == len(headers), "ragged CSV row")
    return True


def _file_key(value):
    if type(value) is not dict or set(value) != {"path", "sha256"} or not _hash(value["sha256"]):
        return None
    path = value["path"]
    if (
        not _text(path)
        or len(path) > 512
        or "\\" in path
        or ":" in path
        or any(part in ("", ".", "..") for part in path.split("/"))
    ):
        return None
    return path, value["sha256"]


class _MediaScan:
    def __init__(self, root, budget):
        self.root = root
        self.budget = budget
        self.bytes_read = 0
        self.results = {}

    def check(self, kind, key):
        if not self.root:
            return "MEDIA_ROOT_UNAVAILABLE", "unavailable"
        cache_key = (kind, *key)
        if cache_key not in self.results:
            self.results[cache_key] = self._inspect(kind, *key)
        return self.results[cache_key]

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
            if not _check_media(kind, data):
                return "MEDIA_PROFILE_UNSUPPORTED", "unavailable"
        except (
            ForgeError,
            ValueError,
            UnicodeError,
            EOFError,
            wave.Error,
            csv.Error,
            struct.error,
            zlib.error,
        ):
            return "MEDIA_FORMAT", "failed"
        return None, "checked"


def _checks(features, field, rule, enum, media):
    if field not in features or features[field] is None:
        if field not in features:
            reason = "MISSING_REQUIRED" if rule.get("required", True) else None
        else:
            reason = None if rule.get("nullable", False) else "NULL_VALUE"
        yield "presence", reason, "failed" if reason else "checked"
        return
    yield "presence", None, "checked"
    value, kind = features[field], rule["type"]
    if not _matches(kind, value):
        yield "type", "WRONG_TYPE", "failed"
        return
    yield "type", None, "checked"
    if "min" in rule or "max" in rule:
        below = "min" in rule and value < rule["min"]
        above = "max" in rule and value > rule["max"]
        yield (
            "range",
            "OUT_OF_RANGE" if below or above else None,
            "failed" if below or above else "checked",
        )
    if enum is not None:
        allowed = canonical(value) in enum
        yield "enum", None if allowed else "OUTSIDE_ENUM", "checked" if allowed else "failed"
    if "unit" in rule:
        unit = rule["unit"]
        recorded = features.get(unit["field"])
        if recorded is None:
            yield "unit", "UNIT_MISSING", "failed"
        elif recorded != unit["symbol"]:
            yield "unit", "UNIT_MISMATCH", "failed"
        else:
            yield "unit", None, "checked"
    if kind == "file":
        key = _file_key(value)
        reason, outcome = media.check(rule["format"], key) if key else ("MEDIA_PATH", "failed")
        yield "media", reason, outcome


def audit(
    path,
    rules_path,
    *,
    sha256,
    rules_sha256,
    media_root=None,
    max_rows=10000,
    max_findings=100,
    max_media_bytes=32 * 1024**2,
):
    """Check an input-order prefix against an externally pinned rule set."""
    _require(
        all(
            type(value) is int and 0 <= value <= limit
            for value, limit in (
                (max_rows, 100000),
                (max_findings, 1000),
                (max_media_bytes, 128 * 1024**2),
            )
        ),
        "invalid audit budget",
    )
    path = Path(path)
    _require(_regular(path), "view requires a regular file")
    document = _load(path, sha256)
    rules = _rules(Path(rules_path), rules_sha256, document["feature_fields"])
    root = Path(media_root).absolute() if media_root is not None else None
    if root is not None:
        _require(
            root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents)),
            "media root must be a directory without symlinks",
        )
    media = _MediaScan(root, max_media_bytes)
    enums = {
        name: {canonical(value) for value in rule["enum"]} if "enum" in rule else None
        for name, rule in rules.items()
    }
    findings, unavailable, total = [], {}, 0
    rows = document["rows"][:max_rows]
    coverage = {name: {"checks": {}} for name in rules}
    for index, row in enumerate(rows):
        for field, rule in rules.items():
            for name, reason, outcome in _checks(row["features"], field, rule, enums[field], media):
                counts = coverage[field]["checks"].setdefault(
                    name, {"checked": 0, "failed": 0, "unavailable": 0}
                )
                counts[outcome] += 1
                if outcome == "unavailable":
                    unavailable[reason] = unavailable.get(reason, 0) + 1
                if outcome == "failed":
                    total += 1
                    if len(findings) < max_findings:
                        findings.append(
                            {
                                "row": {"id": row["id"], "split": row["split"], "index": index},
                                "field": field,
                                "check": name,
                                "reason": reason,
                            }
                        )
    partial = len(rows) != len(document["rows"])
    status = (
        "FAILED"
        if total
        else "NOT_RUN"
        if not rows
        else "INCONCLUSIVE"
        if partial or unavailable
        else "TESTED"
    )
    return {
        "schema": "forge.semantic-audit.v1",
        "status": status,
        "input_sha256": sha256,
        "rules_sha256": rules_sha256,
        "coverage": coverage,
        "scope": {
            "scanned_rows": len(rows),
            "total_rows": len(document["rows"]),
            "selection": "INPUT_ORDER_PREFIX",
            "rules": rules,
            "fields_without_rules": sorted(set(document["feature_fields"]) - rules.keys()),
        },
        "media": {
            "unique_checks": len(media.results),
            "bytes_read": media.bytes_read,
            "max_bytes": max_media_bytes,
            "unavailable_by_reason": unavailable,
        },
        "findings": findings,
        "findings_total": total,
        "findings_omitted": total - len(findings),
        "scientific_qualification": "NOT_QUALIFIED",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--rules", type=Path, required=True)
    parser.add_argument("--rules-sha256", required=True)
    parser.add_argument("--media-root", type=Path)
    parser.add_argument("--max-rows", type=int, default=10000)
    parser.add_argument("--max-findings", type=int, default=100)
    parser.add_argument("--max-media-bytes", type=int, default=32 * 1024**2)
    args = parser.parse_args()
    try:
        report = audit(
            args.input,
            args.rules,
            sha256=args.sha256,
            rules_sha256=args.rules_sha256,
            media_root=args.media_root,
            max_rows=args.max_rows,
            max_findings=args.max_findings,
            max_media_bytes=args.max_media_bytes,
        )
    except (ForgeError, OSError) as exc:
        parser.exit(2, f"forge semantic audit: {exc}\n")
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
