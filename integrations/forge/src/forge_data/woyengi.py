"""Untrusted Woyengi predictive projection -> Forge operations-row CANDIDATE.

This converter does NOT authenticate a Woyengi host, legal source rights, identity
or publisher data. It cannot independently attest source availability, model
learning, verifier independence or use rights. No inference, network or release.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timezone
from typing import Any

from .core import ForgeError, normalize

_EXPORT_FIELDS = {
    "kind",
    "schemaVersion",
    "status",
    "subject",
    "predicate",
    "validAt",
    "recordedAt",
    "predictionCutoff",
    "selectedClaimId",
    "conflictingClaimIds",
    "observations",
    "qualification",
    "publisherAuthenticity",
    "independentRewardVerification",
    "actionAuthority",
}
_OBSERVATION_FIELDS = {
    "claimId",
    "validFrom",
    "knownFrom",
    "sourceAvailableAt",
    "featureHash",
    "features",
}
_SHA = __import__("re").compile(r"^[a-f0-9]{64}$")
_FORBIDDEN = {
    "future",
    "label",
    "oracle",
    "reward",
    "gold",
    "target",
    "outcome",
    "verified",
    "acceptance",
    "authority",
    "secret",
    "token",
}


def _when(value: object, label: str) -> datetime:
    if (
        not isinstance(value, str)
        or not value.endswith(("Z", "z"))
        and not __import__("re").search(r"[+-]\d{2}:\d{2}$", value)
    ):
        raise ForgeError(f"{label}: timezone required")
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00").replace("z", "+00:00"))
        if instant.utcoffset() is None:
            raise ValueError()
        return instant.astimezone(timezone.utc)
    except ValueError as exc:
        raise ForgeError(f"{label}: invalid timestamp") from exc


def _dict(value: Any, label: str) -> dict:
    if not isinstance(value, dict):
        raise ForgeError(f"{label}: object required")
    return value


def _keys(value: dict, fields: set, label: str) -> None:
    if set(value) != fields:
        raise ForgeError(f"{label}: required-only fields mismatch")


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ForgeError(f"{label}: nonempty text required")
    return value


def _safe_payload(value: object, depth: int = 0) -> None:
    if depth > 12:
        raise ForgeError("Woyengi nested feature depth exceeded")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ForgeError("Woyengi feature key invalid")
            words = set(__import__("re").sub(r"[^a-z0-9]+", "_", key.lower()).split("_"))
            if words.intersection(_FORBIDDEN):
                raise ForgeError("Woyengi future, reward, or authority feature forbidden")
            _safe_payload(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _safe_payload(child, depth + 1)
    elif value is not None and type(value) not in (str, float, int, bool):
        raise ForgeError("Woyengi feature has unsupported type")
    elif type(value) is float and not math.isfinite(value):
        raise ForgeError("Woyengi nonfinite feature")


def convert_export_candidate(source: dict, *, source_id: str = "woyengi-unattested") -> dict:
    """Return candidate operations rows, never an independently validated release.

    'observed_at' maps Woyengi claim.validFrom (when that fact was valid),
    NOT a physical sensor's observation time. 'available_at' uses the full
    as-of projection cutoff conservatively: selected/conflict state may
    depend on later-known claims. Earlier Forge point_in_time reads return
    None instead of leaking selected/conflict hindsight.
    """
    d = _dict(source, "Woyengi predictive read export")
    _keys(d, _EXPORT_FIELDS, "Woyengi predictive read export")
    if (
        d.get("kind") != "PREDICTIVE_READ_EXPORT"
        or type(d.get("schemaVersion")) is not int
        or d["schemaVersion"] != 1
        or d.get("status") != "ADVISORY_ONLY"
        or d.get("qualification") != "STRUCTURAL_EXPORT_ONLY"
        or d.get("publisherAuthenticity") != "NOT_ATTESTED_BY_THIS_EXPORTER"
        or d.get("independentRewardVerification") != "NOT_PERFORMED"
        or d.get("actionAuthority") != "NOT_GRANTED"
    ):
        raise ForgeError("Woyengi authority or structural contract incompatible")
    subject = _text(d["subject"], "subject")
    predicate = _text(d["predicate"], "predicate")
    _text(source_id, "source_id")
    cutoff = _when(d["predictionCutoff"], "predictionCutoff")
    if _when(d["recordedAt"], "recordedAt") > cutoff or _when(d["validAt"], "validAt") > cutoff:
        raise ForgeError("Woyengi future projection access")
    rows = d["observations"]
    conflicts = d["conflictingClaimIds"]
    if not isinstance(rows, list) or not rows or not isinstance(conflicts, list):
        raise ForgeError("Woyengi candidates or conflicts missing")
    selected = _text(d["selectedClaimId"], "selectedClaimId")
    refs = set()
    for item in rows:
        item = _dict(item, "Woyengi observation")
        _keys(item, _OBSERVATION_FIELDS, "Woyengi observation")
        claim_id = _text(item["claimId"], "claimId")
        if claim_id in refs:
            raise ForgeError("duplicate Woyengi claim")
        refs.add(claim_id)
        valid_from = _when(item["validFrom"], "validFrom")
        if valid_from > _when(d["validAt"], "validAt"):
            raise ForgeError("Woyengi claim not yet valid at projection")
        if _when(item["knownFrom"], "knownFrom") > _when(d["recordedAt"], "recordedAt"):
            raise ForgeError("Woyengi future-known claim")
        if _when(item["sourceAvailableAt"], "sourceAvailableAt") > cutoff:
            raise ForgeError("Woyengi future-available claim")
        if not isinstance(item["featureHash"], str) or not _SHA.fullmatch(item["featureHash"]):
            raise ForgeError("Woyengi declared derived hash malformed")
        _safe_payload(_dict(item["features"], "Woyengi features"))
        if not item["features"]:
            raise ForgeError("Woyengi features empty")
    if selected not in refs or selected in conflicts or len(set(conflicts)) != len(conflicts):
        raise ForgeError("Woyengi selected/conflict mismatch")
    if any(not isinstance(x, str) or x not in refs for x in conflicts):
        raise ForgeError("Woyengi unregistered conflict")
    suffix = hashlib.sha256(
        (subject + "\0" + predicate + "\0" + d["predictionCutoff"]).encode()
    ).hexdigest()[:24]
    prepared = []
    for item in rows:
        claim_id = item["claimId"]
        record = {
            "episode_id": subject + "/" + predicate,
            "subject_id": subject,
            "record_id": "projection:" + suffix + "/" + claim_id,
            "observed_at": item["validFrom"],
            # Snapshot-level knowledge is not valid before the selection cutoff.
            "available_at": d["predictionCutoff"],
            "observation": {
                "kind": "woyengi_bitemporal_claim_projection",
                "claim_id": claim_id,
                "predicate": predicate,
                "valid_from": item["validFrom"],
                "known_from": item["knownFrom"],
                "original_source_available_at_claim": item["sourceAvailableAt"],
                "derived_feature_hash_claim": item["featureHash"],
                "selected_at_projection": claim_id == selected,
                "conflicted_at_projection": claim_id in conflicts,
                "features": item["features"],
            },
            "action": None,
            "outcome": {"status": "unknown", "verified": False},
        }
        prepared.append(normalize(record, adapter="operations-jsonl", source_id=source_id))
    return {
        "conversion": "STRUCTURAL_ONLY",
        "publisher_source_verified": False,
        "source_legal_permission_verified": False,
        "woyengi_host_authenticated": False,
        "independent_outcome_verified": False,
        "recorded_semantics": (
            "claim.validFrom is fact validity; full snapshot available only as-of predictionCutoff"
        ),
        "rows": prepared,
    }
