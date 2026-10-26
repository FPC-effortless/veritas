"""Capture a small public NYC 311 API snapshot with transparent *acquisition* evidence.

This tool CANNOT prove the snapshot matches historical time-of-knowledge,
publisher revisions, privacy clearance, license scope, case outcome accuracy,
or eligibility for real TAC-OSM training. Captures are SOURCE CANDIDATES ONLY.

Source: NYC Open Data erm2-nwe9. No API secrets or free-text/geolocation fields.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SOURCE_BASE = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
PUBLISHER_PAGE = "https://data.cityofnewyork.us/Social-Services/311-Service-Requests-from-2020-to-Present/erm2-nwe9"
SAFE_COLUMNS = (
    "unique_key", "created_date", "closed_date", "agency", "complaint_type", "status"
)
MAX_BYTES = 3_000_000
CAPTURE_SCHEMA = "forge.public-api-snapshot.v0.1"


class SnapshotError(ValueError):
    """Capture does not support a source-qualification claim."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_utc(value: object, name: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise SnapshotError(f"{name}: UTC-Z instant required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.utcoffset() is None:
            raise ValueError()
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise SnapshotError(f"{name}: invalid timestamp") from exc


def _source_url(limit: int) -> str:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise SnapshotError("limited public source capture must request 1..100 rows")
    query = urlencode({
        "$select": ",".join(SAFE_COLUMNS),
        "$order": "created_date DESC,unique_key DESC",
        "$limit": str(limit),
    })
    return SOURCE_BASE + "?" + query


def _check_rows(raw: bytes, limit: int) -> list[dict]:
    if not raw or len(raw) > MAX_BYTES:
        raise SnapshotError("source response is empty or exceeds public capture bound")
    def no_constant(s):
        raise SnapshotError(f"nonfinite JSON source value {s}")
    try:
        parsed = json.loads(raw.decode("utf-8"), parse_constant=no_constant)
    except (ValueError, UnicodeDecodeError) as exc:
        raise SnapshotError("source response not valid JSON") from exc
    if not isinstance(parsed, list) or not 0 < len(parsed) <= limit:
        raise SnapshotError("source response row count/schema unexpected")
    seen = set()
    for i, row in enumerate(parsed):
        if not isinstance(row, dict) or not {"unique_key", "created_date"} <= set(row):
            raise SnapshotError(f"source row {i}: missing core publisher fields")
        if not set(row) <= set(SAFE_COLUMNS):
            raise SnapshotError(f"source row {i}: unexpected or sensitive fields")
        rid = row["unique_key"]
        if not isinstance(rid, str) or not rid.strip() or rid in seen:
            raise SnapshotError(f"source row {i}: duplicate/invalid source identity")
        if not isinstance(row["created_date"], str) or not row["created_date"]:
            raise SnapshotError(f"source row {i}: missing recorded date text")
        for key, value in row.items():
            if not isinstance(value, str):
                raise SnapshotError(f"source row {i}: unsupported field value {key}")
        seen.add(rid)
    return parsed


def make_snapshot(output_dir: Path, *, limit: int = 25, fetcher=None, clock=None) -> dict:
    """Download public SELECT-only bytes, save immutable raw + acquisition receipt.

    fetcher(request, byte_limit) returns (status_code, content_type, http_date, raw).
    For production use default urllib fetcher; tests inject only constructed bytes.
    """
    if output_dir.exists():
        raise SnapshotError("do not overwrite an existing source capture")
    url = _source_url(limit)
    fetcher = fetcher or _fetch_public
    clock = clock or _utc_now
    start = clock()
    _parse_utc(start, "acquisition_start_utc")
    status, content_type, server_date, raw = fetcher(Request(url, headers={
        "User-Agent": "ForgeTemporalSourceAudit/0.1 (scientific-source-qualification)"
    }), MAX_BYTES)
    end = clock()
    if _parse_utc(end, "acquisition_end_utc") < _parse_utc(start, "acquisition_start_utc"):
        raise SnapshotError("non-monotonic acquisition clock")
    if status != 200 or not isinstance(content_type, str) or "json" not in content_type.lower():
        raise SnapshotError("NYC311 API did not return HTTP 200 JSON")
    if not isinstance(raw, bytes):
        raise SnapshotError("source response must be raw bytes")
    records = _check_rows(raw, limit)
    receipt = {
        "schema": CAPTURE_SCHEMA,
        "dataset_id": "NYC311/erm2-nwe9",
        "publisher_page": PUBLISHER_PAGE,
        "request_url": url,
        "method": "GET",
        "http_status": status,
        "http_content_type": content_type,
        "http_date_header_unverified": server_date if isinstance(server_date, str) else None,
        "acquisition_start_utc": start,
        "acquisition_end_utc": end,
        "source_bytes_sha256": hashlib.sha256(raw).hexdigest(),
        "source_bytes": len(raw),
        "records_observed": len(records),
        "exposed_fields": list(SAFE_COLUMNS),
        "acquisition_evidence": "PUBLIC_API_CAPTURE_CANDIDATE",
        "historical_asof_fields_qualified": False,
        "source_license_and_privacy_independently_reviewed": False,
        "publisher_row_revision_history_verified": False,
        "source_outcomes_independently_verified": False,
        "allowed_for_model_fit_or_heldout_scoring": False,
        "notes": (
            "Rows can be retrospectively corrected. Acquisition timestamp is not "
            "the historical availability of case status/agency/closure. "
            "Do not backdate late-known fields or fabricate interventions."
        ),
    }
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".nyc311-capture-", dir=output_dir.parent))
    try:
        (stage / "publisher-response.json").write_bytes(raw)
        (stage / "acquisition-receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(stage, output_dir)
    finally:
        if stage.exists():
            import shutil
            shutil.rmtree(stage)
    return receipt


def _fetch_public(request: Request, byte_limit: int):
    with urlopen(request, timeout=30) as resp:
        raw = resp.read(byte_limit + 1)
        return (
            resp.status,
            resp.headers.get("Content-Type", ""),
            resp.headers.get("Date"),
            raw,
        )


def inspect_capture(directory: Path) -> dict:
    """Verify local capture identity; never promote its data/evidence authority."""
    receipt = json.loads((directory / "acquisition-receipt.json").read_text(encoding="utf-8"))
    raw = (directory / "publisher-response.json").read_bytes()
    if receipt.get("schema") != CAPTURE_SCHEMA:
        raise SnapshotError("unsupported source capture schema")
    if receipt.get("publisher_page") != PUBLISHER_PAGE or receipt.get("dataset_id") != "NYC311/erm2-nwe9":
        raise SnapshotError("unexpected publisher reference")
    limit = int(dict(__import__("urllib.parse").parse_qsl(
        __import__("urllib.parse").urlsplit(receipt.get("request_url", "")).query
    )).get("$limit", "0"))
    if receipt.get("request_url") != _source_url(limit):
        raise SnapshotError("source query not the approved public minimal-field query")
    if receipt.get("source_bytes_sha256") != hashlib.sha256(raw).hexdigest():
        raise SnapshotError("source capture bytes differ from committed receipt hash")
    if receipt.get("source_bytes") != len(raw):
        raise SnapshotError("source byte count mismatch")
    rows = _check_rows(raw, limit)
    if receipt.get("records_observed") != len(rows):
        raise SnapshotError("source row count mismatch")
    if _parse_utc(receipt.get("acquisition_end_utc"), "acquisition_end_utc") < _parse_utc(
        receipt.get("acquisition_start_utc"), "acquisition_start_utc"
    ):
        raise SnapshotError("invalid acquisition clock order")
    for forbidden_promotion in (
        "historical_asof_fields_qualified",
        "source_license_and_privacy_independently_reviewed",
        "publisher_row_revision_history_verified",
        "source_outcomes_independently_verified",
        "allowed_for_model_fit_or_heldout_scoring",
    ):
        if receipt.get(forbidden_promotion) is not False:
            raise SnapshotError(f"capture cannot self-promote {forbidden_promotion}")
    return {
        "capture_integrity": "LOCAL_BYTES_AND_RECEIPT_MATCH",
        "rows": len(rows),
        "sha256": receipt["source_bytes_sha256"],
        "source_authority": "UNVERIFIED",
        "historical_asof": "NOT_QUALIFIED",
        "fit_or_scoring": "PROHIBITED",
    }
