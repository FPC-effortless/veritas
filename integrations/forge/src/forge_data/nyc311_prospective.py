"""Bounded prospective NYC311 *candidate* cohort and fixed-ID observation capture.

This module makes no historical data-availability, independent outcome,
legal/privacy, protected evaluation or TRAINING qualification claims.
It never interprets case status as physical work completion.
No scheduler, automated enrollment into FIT, model training or scorer.

Publisher source is always queried via allowlisted public NYC311 SoQL fields.
The cohort's membership freezes on the FIRST observed open-status snapshot;
a follow-up MUST query the same IDs, including missing/changed identities.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from urllib.parse import urlencode
from urllib.request import Request

from .nyc311_snapshot import (
    MAX_BYTES, SOURCE_BASE, SnapshotError, _fetch_public, _parse_utc, _utc_now,
)

ENROL_COLUMNS = ("unique_key", "created_date", "agency", "complaint_type", "status")
FOLLOW_COLUMNS = ("unique_key", "status")
ID = re.compile(r"^[0-9]{1,24}$")
MAX_CANDIDATES = 100
MIN_FOLLOWUP = timedelta(days=7)
SCHEMA = "forge.nyc311-prospective-candidate.v0.1"


def _request_url(kind: str, ids: tuple[str, ...] = (), limit: int = MAX_CANDIDATES) -> str:
    if kind == "enroll":
        if type(limit) is not int or not 1 <= limit <= MAX_CANDIDATES:
            raise SnapshotError("candidate enrollment limit must be 1..100")
        # Only the five minimal allowed fields; never capture free-text, address,
        # personal identifiers or closure/label fields at enrollment.
        params = {
            "$select": ",".join(ENROL_COLUMNS),
            "$where": "status='Open'",
            "$order": "created_date DESC,unique_key DESC",
            "$limit": str(limit),
        }
    elif kind == "followup":
        if (not ids or len(ids) > MAX_CANDIDATES or len(set(ids)) != len(ids)
                or any(not isinstance(x, str) or not ID.fullmatch(x) for x in ids)):
            raise SnapshotError("followup must query 1..100 distinct numeric registered case IDs")
        # Escaping is deliberate even though IDs are strictly numeric. No
        # latest-N query or membership replacement may enter follow-up.
        values = ",".join(f"'{x}'" for x in ids)
        params = {"$select": ",".join(FOLLOW_COLUMNS),
                  "$where": f"unique_key in({values})", "$order": "unique_key ASC"}
    else:
        raise SnapshotError("unsupported prospective source operation")
    return SOURCE_BASE + "?" + urlencode(params)


def _raw_rows(raw: bytes, *, mode: str, ids: tuple[str, ...] = (), limit=100) -> list[dict]:
    if not isinstance(raw, bytes) or not raw or len(raw) > MAX_BYTES:
        raise SnapshotError("publisher response absent or exceeds bounded source bytes")
    def reject_constant(value):
        raise SnapshotError(f"non-JSON numeric constant {value}")
    try:
        rows = json.loads(raw.decode("utf-8"), parse_constant=reject_constant)
    except (UnicodeDecodeError, ValueError) as exc:
        raise SnapshotError("publisher data must be valid UTF8 JSON") from exc
    if not isinstance(rows, list) or (mode == "enroll" and not 0 < len(rows) <= limit):
        raise SnapshotError("missing/out-of-range initial eligible candidate rows")
    if mode == "followup" and len(rows) > len(ids):
        raise SnapshotError("more fixed-ID followup rows than registered")
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise SnapshotError("publisher row object required")
        allowed = ENROL_COLUMNS if mode == "enroll" else FOLLOW_COLUMNS
        mandatory = ("unique_key", "created_date", "status") if mode == "enroll" else ("unique_key", "status")
        if not set(mandatory).issubset(row) or not set(row) <= set(allowed):
            raise SnapshotError("missing required fields or non-allowlisted publisher columns")
        if any(not isinstance(v, str) or not v.strip() for v in row.values()):
            raise SnapshotError("publisher row contains unsupported/empty field")
        uid = row["unique_key"]
        if not ID.fullmatch(uid) or uid in seen:
            raise SnapshotError("non-numeric or duplicate publisher case identity")
        seen.add(uid)
        if mode == "enroll" and row["status"] != "Open":
            raise SnapshotError("only source-observed open cases can enter the candidate cohort")
        if mode == "followup" and uid not in ids:
            raise SnapshotError("unexpected/injected case identity in fixed-ID followup")
    return rows


def _capture(url: str, *, fetcher, clock):
    start = clock()
    _parse_utc(start, "acquisition_start_utc")
    status, content_type, http_date, raw = fetcher(Request(url, headers={
        "User-Agent": "ForgeProspectiveSourceAudit/0.1 (public snapshot, no fit)"
    }), MAX_BYTES)
    end = clock()
    if _parse_utc(end, "acquisition_end_utc") < _parse_utc(start, "acquisition_start_utc"):
        raise SnapshotError("source acquisition clock reversed")
    if status != 200 or not isinstance(content_type, str) or "json" not in content_type.lower():
        raise SnapshotError("publisher did not return HTTP 200 JSON")
    if not isinstance(raw, bytes) or len(raw) > MAX_BYTES:
        raise SnapshotError("invalid or oversized bounded HTTP response")
    return raw, {
        "request_url": url,
        "method": "GET",
        "http_status": status,
        "http_content_type": content_type,
        "publisher_http_date_unverified": http_date if isinstance(http_date, str) else None,
        "acquisition_start_utc": start,
        "acquisition_end_utc": end,
        "original_response_sha256": hashlib.sha256(raw).hexdigest(),
        "original_response_bytes": len(raw),
    }


def _atomic_write(directory: Path, files: dict[str, bytes]):
    if directory.exists():
        raise SnapshotError("source snapshot destination already exists; no overwrite")
    directory.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=".nyc311-prospective-", dir=directory.parent))
    try:
        for name, body in files.items():
            (stage / name).write_bytes(body)
        os.replace(stage, directory)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _json(data: dict) -> bytes:
    return (json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")


def enroll_candidate(output_dir: Path, *, limit=MAX_CANDIDATES, fetcher=None, clock=None) -> dict:
    """Freeze an acquisition-time cohort candidate; never authorize model fit."""
    if output_dir.exists():
        raise SnapshotError("existing candidate enrollment cannot be overwritten")
    url = _request_url("enroll", limit=limit)
    raw, capture = _capture(url, fetcher=fetcher or _fetch_public, clock=clock or _utc_now)
    rows = _raw_rows(raw, mode="enroll", limit=limit)
    ids = tuple(sorted(row["unique_key"] for row in rows))
    id_bytes = ("\n".join(ids) + "\n").encode("ascii")
    manifest = {
        "schema": SCHEMA,
        "dataset_id": "NYC311/erm2-nwe9",
        "cohort_kind": "CANDIDATE_FIRST_OBSERVED_OPEN_NOT_REGISTERED",
        "capture": capture,
        "eligible_publisher_status_at_acquisition": "Open",
        "enrolled_case_count": len(ids),
        "case_id_list_sha256": hashlib.sha256(id_bytes).hexdigest(),
        "case_ids": list(ids),  # local restricted artifact, not public CI log
        "followup_method": "fixed_enrolled_id_list_only",
        "min_followup_days": 7,
        "historical_asof_qualified": False,
        "publisher_field_revision_history_qualified": False,
        "publisher_reported_closure_independently_verified": False,
        "source_rights_privacy_approved": False,
        "fit_or_report_scoring_authorized": False,
        "scientific_evidence_tier": "PUBLIC_SOURCE_COHORT_CANDIDATE_ONLY",
    }
    _atomic_write(output_dir, {
        "enrollment-source.json": raw, "candidate-manifest.json": _json(manifest)
    })
    return {k: v for k, v in manifest.items() if k != "case_ids"}


def inspect_candidate(root: Path) -> dict:
    """Check exact local bytes and frozen IDs; refuse user-promoted qualifications."""
    manifest = json.loads((root / "candidate-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema") != SCHEMA or manifest.get("dataset_id") != "NYC311/erm2-nwe9":
        raise SnapshotError("unknown prospective source candidate")
    ids = manifest.get("case_ids")
    if not isinstance(ids, list):
        raise SnapshotError("candidate ID list missing")
    id_tuple = tuple(ids)
    if (not ids or len(ids) > MAX_CANDIDATES or len(set(ids)) != len(ids)
            or any(not isinstance(x, str) or not ID.fullmatch(x) for x in ids)
            or tuple(sorted(ids)) != id_tuple):
        raise SnapshotError("invalid or changed frozen candidate membership")
    expected = hashlib.sha256(("\n".join(ids) + "\n").encode("ascii")).hexdigest()
    if manifest.get("case_id_list_sha256") != expected or manifest.get("enrolled_case_count") != len(ids):
        raise SnapshotError("candidate identity list digest/count mismatch")
    c = manifest.get("capture")
    if not isinstance(c, dict):
        raise SnapshotError("publisher capture metadata missing")
    url = _request_url("enroll", limit=int(dict(__import__("urllib.parse").parse_qsl(
        __import__("urllib.parse").urlsplit(c.get("request_url", "")).query
    )).get("$limit", "0")))
    if url != c.get("request_url"):
        raise SnapshotError("capture URL is not a strict open-only publisher query")
    data = (root / "enrollment-source.json").read_bytes()
    if hashlib.sha256(data).hexdigest() != c.get("original_response_sha256"):
        raise SnapshotError("publisher original bytes hash mismatch")
    rows = _raw_rows(data, mode="enroll", limit=MAX_CANDIDATES)
    if tuple(sorted(row["unique_key"] for row in rows)) != id_tuple:
        raise SnapshotError("frozen membership and source rows differ")
    if _parse_utc(c.get("acquisition_end_utc"), "acquisition_end_utc") < _parse_utc(
        c.get("acquisition_start_utc"), "acquisition_start_utc"
    ):
        raise SnapshotError("capture timestamp order invalid")
    for flag in ("historical_asof_qualified", "publisher_field_revision_history_qualified",
                 "publisher_reported_closure_independently_verified",
                 "source_rights_privacy_approved", "fit_or_report_scoring_authorized"):
        if manifest.get(flag) is not False:
            raise SnapshotError(f"candidate may not self-promote: {flag}")
    if manifest.get("scientific_evidence_tier") != "PUBLIC_SOURCE_COHORT_CANDIDATE_ONLY":
        raise SnapshotError("candidate source scientific status invalid")
    return {
        "case_ids": id_tuple, "capture": c,
        "cohort_sha256": expected, "case_count": len(id_tuple),
    }


def followup_fixed_ids(candidate_dir: Path, output_dir: Path, *,
                       fetcher=None, clock=None) -> dict:
    """Capture ONLY original frozen IDs, >=7 days later. NO labels or fit."""
    frozen = inspect_candidate(candidate_dir)
    if output_dir.exists():
        raise SnapshotError("no overwriting source followup captures")
    ids = frozen["case_ids"]
    clock = clock or _utc_now
    # Check elapsed wall time *before* making any network call.
    start = clock()
    cutoff = _parse_utc(start, "followup acquisition start")
    enrolled_at = _parse_utc(frozen["capture"]["acquisition_end_utc"], "enrollment end")
    if cutoff < enrolled_at + MIN_FOLLOWUP:
        raise SnapshotError("7-day followup not yet due; do not query future labels")
    second = iter([start, clock()])
    raw, capture = _capture(_request_url("followup", ids), fetcher=fetcher or _fetch_public,
                            clock=lambda: next(second))
    rows = _raw_rows(raw, mode="followup", ids=ids)
    present = set(row["unique_key"] for row in rows)
    # Missing cases and status corrections are information, not negatives.
    missing = sorted(set(ids) - present)
    receipt = {
        "schema": "forge.nyc311-fixed-id-followup.v0.1",
        "cohort_sha256": frozen["cohort_sha256"],
        "capture": capture,
        "present_case_count": len(present),
        "missing_case_count": len(missing),
        "missing_case_ids": missing,
        "actual_status_labels_verified": False,
        "historical_asof_qualified": False,
        "fit_or_scoring_authorized": False,
        "outcome_status": "PUBLISHER_SNAPSHOT_UNVERIFIED_NO_LABELS",
    }
    _atomic_write(output_dir, {"followup-source.json": raw,
                               "followup-receipt.json": _json(receipt)})
    return {k: v for k, v in receipt.items() if k != "missing_case_ids"}
