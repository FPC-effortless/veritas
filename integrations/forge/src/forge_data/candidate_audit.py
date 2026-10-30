"""Read-only, redacted software audit of an UNATTESTED Woyengi source candidate.

Never creates a dataset release, calls a model, accesses a network service,
or establishes host authentication, rights, source truth or scientific skill.
"""
from __future__ import annotations

import json
from pathlib import Path

from .core import ForgeError, point_in_time
from .woyengi import convert_export_candidate

MAX_CANDIDATE_BYTES = 1024 * 1024


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ForgeError("duplicate JSON keys in Woyengi candidate")
        result[key] = value
    return result


def _no_nonfinite(token: str) -> object:
    raise ForgeError("nonfinite JSON numbers are forbidden")


def audit_woyengi_candidate(path: Path, *, as_of: str) -> dict:
    """Validate a small local export and return only non-identifying counts.

    The source converter's structural checks are necessary but not evidence
    that the producer was trusted. No candidate content is persisted or echoed.
    """
    with path.open("rb") as handle:
        raw = handle.read(MAX_CANDIDATE_BYTES + 1)
    if len(raw) > MAX_CANDIDATE_BYTES:
        raise ForgeError("Woyengi candidate exceeds local audit size limit")
    try:
        candidate = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_unique_pairs,
            parse_constant=_no_nonfinite,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ForgeError("invalid Woyengi candidate JSON") from exc
    converted = convert_export_candidate(candidate)
    rows = converted["rows"]
    # Even for an invalid time, exercise point_in_time instead of silently
    # returning zero rows: that function validates the offset-aware cutoff.
    visible = [row for row in rows if point_in_time(row, as_of) is not None]
    return {
        "schema": "forge.woyengi.candidate_audit.v1",
        "qualification": "STRUCTURAL_ONLY",
        "publisher_authenticity": "NOT_VERIFIED",
        "source_rights": "NOT_VERIFIED",
        "woyengi_host_authentication": "NOT_VERIFIED",
        "independent_outcomes": "NOT_VERIFIED",
        "model_training_release": "PROHIBITED",
        "model_inference": "NOT_PERFORMED",
        "device_offline_qualification": "NOT_RUN",
        "records_total": len(rows),
        "records_visible_as_of": len(visible),
        "records_not_yet_available": len(rows) - len(visible),
    }
