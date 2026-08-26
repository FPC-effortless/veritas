from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from investigation_world.projectworld.models import ProjectEvidenceRecord, ProjectStateValue
from investigation_world.projectworld.sources import (
    FusedSourceField,
    FusionTarget,
    NormalizedSourceRecord,
    TranscriptChunk,
    fuse_records,
)


def _first(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    lower = {str(key).casefold(): value for key, value in row.items()}
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
        candidate = lower.get(key.casefold())
        if candidate not in (None, ""):
            return candidate
    return default


def _number(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    try:
        return float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return default


def _date(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for candidate in (text, text.replace("Z", "+00:00")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            pass
    return None


def normalize_ifc_element(
    row: dict[str, Any],
    *,
    source_id: str,
    model_id: str,
    authority_rank: int = 85,
) -> list[NormalizedSourceRecord]:
    """Normalize a parsed IFC element row from GNI/buildingSMART/IFC-Bench exports."""
    guid = str(_first(row, "GlobalId", "global_id", "guid", "id", default="UNKNOWN"))
    canonical_id = f"{model_id}:{guid}"
    records: list[NormalizedSourceRecord] = []
    mappings = {
        "ifc_class": _first(row, "ifc_class", "IfcClass", "type", "entity"),
        "name": _first(row, "Name", "name"),
        "level": _first(row, "Storey", "storey", "level"),
        "system": _first(row, "System", "system", "system_name"),
        "material": _first(row, "Material", "material"),
        "quantity": _first(row, "Quantity", "quantity", "volume", "area", "length"),
    }
    for field_name, value in mappings.items():
        if value in (None, ""):
            continue
        records.append(
            NormalizedSourceRecord(
                source_id=source_id,
                canonical_type=FusionTarget.DESIGN,
                canonical_id=canonical_id,
                field_name=field_name,
                value=value,
                authority_rank=authority_rank,
                provenance={"model_id": model_id, "ifc_guid": guid},
            )
        )
    return records


def normalize_osha_incident(
    row: dict[str, Any],
    *,
    source_id: str = "osha-severe-injury",
) -> list[NormalizedSourceRecord]:
    incident_id = str(
        _first(
            row,
            "InspectionNr",
            "inspection_number",
            "event_id",
            "id",
            default=f"OSHA-{abs(hash(str(sorted(row.items()))))}",
        )
    )
    observed = _date(_first(row, "EventDate", "event_date", "date"))
    narrative = _first(row, "Final Narrative", "narrative", "description", default="")
    event_type = _first(row, "Event", "event", "event_type", default="UNKNOWN")
    source = _first(row, "Source", "source", "source_title", default="UNKNOWN")
    nature = _first(row, "Nature", "nature", default="UNKNOWN")
    return [
        NormalizedSourceRecord(
            source_id=source_id,
            canonical_type=FusionTarget.SAFETY_EVENT,
            canonical_id=incident_id,
            field_name="event_type",
            value=event_type,
            observed_at=observed,
            authority_rank=95,
            provenance={"narrative": narrative},
        ),
        NormalizedSourceRecord(
            source_id=source_id,
            canonical_type=FusionTarget.SAFETY_EVENT,
            canonical_id=incident_id,
            field_name="hazard_source",
            value=source,
            observed_at=observed,
            authority_rank=95,
        ),
        NormalizedSourceRecord(
            source_id=source_id,
            canonical_type=FusionTarget.SAFETY_EVENT,
            canonical_id=incident_id,
            field_name="injury_nature",
            value=nature,
            observed_at=observed,
            authority_rank=95,
        ),
    ]


def normalize_usaspending_award(
    row: dict[str, Any],
    *,
    source_id: str = "usaspending-contracts",
) -> list[NormalizedSourceRecord]:
    award_id = str(
        _first(
            row,
            "Award ID",
            "award_id",
            "generated_unique_award_id",
            "piid",
            default=f"AWARD-{abs(hash(str(sorted(row.items()))))}",
        )
    )
    amount = _number(
        _first(
            row,
            "Award Amount",
            "award_amount",
            "total_obligation",
            "federal_action_obligation",
        )
    )
    recipient = _first(row, "Recipient Name", "recipient_name", "recipient", default="UNKNOWN")
    description = _first(row, "Award Description", "description", "award_description", default="")
    observed = _date(_first(row, "Start Date", "start_date", "action_date"))
    return [
        NormalizedSourceRecord(
            source_id=source_id,
            canonical_type=FusionTarget.CONTRACT,
            canonical_id=award_id,
            field_name="amount",
            value=amount,
            observed_at=observed,
            authority_rank=80,
            provenance={"description": description},
        ),
        NormalizedSourceRecord(
            source_id=source_id,
            canonical_type=FusionTarget.CONTRACT,
            canonical_id=award_id,
            field_name="recipient",
            value=recipient,
            observed_at=observed,
            authority_rank=80,
        ),
    ]


def normalize_noaa_hourly(
    row: dict[str, Any],
    *,
    site_id: str,
    source_id: str = "noaa-ghcnh",
) -> list[NormalizedSourceRecord]:
    observed = _date(_first(row, "DATE", "date", "timestamp"))
    station = str(_first(row, "STATION", "station", default="UNKNOWN"))
    variables = {
        "temperature": _first(row, "TMP", "temperature", "temp"),
        "wind": _first(row, "WND", "wind", "wind_speed"),
        "precipitation": _first(row, "AA1", "precipitation", "precip"),
        "visibility": _first(row, "VIS", "visibility"),
    }
    records: list[NormalizedSourceRecord] = []
    suffix = observed.isoformat() if observed is not None else station
    for field_name, value in variables.items():
        if value in (None, ""):
            continue
        records.append(
            NormalizedSourceRecord(
                source_id=source_id,
                canonical_type=FusionTarget.WEATHER_EVENT,
                canonical_id=f"{site_id}:{suffix}",
                field_name=field_name,
                value=value,
                observed_at=observed,
                authority_rank=95,
                provenance={"site_id": site_id, "station": station},
            )
        )
    return records


def normalize_site_context(
    row: dict[str, Any],
    *,
    site_id: str,
    source_id: str,
    authority_rank: int,
) -> list[NormalizedSourceRecord]:
    records: list[NormalizedSourceRecord] = []
    for field_name in (
        "latitude",
        "longitude",
        "elevation",
        "slope",
        "access_class",
        "road_type",
    ):
        value = _first(row, field_name)
        if value in (None, ""):
            continue
        records.append(
            NormalizedSourceRecord(
                source_id=source_id,
                canonical_type=FusionTarget.SITE,
                canonical_id=site_id,
                field_name=field_name,
                value=value,
                authority_rank=authority_rank,
            )
        )
    return records


def fuse_source_batches(
    *batches: Iterable[NormalizedSourceRecord],
) -> list[FusedSourceField]:
    records = [item for batch in batches for item in batch]
    return fuse_records(records)


def fused_fields_to_state(fields: Iterable[FusedSourceField]) -> list[ProjectStateValue]:
    states: list[ProjectStateValue] = []
    for item in fields:
        states.append(
            ProjectStateValue(
                object_type=item.canonical_type.value,
                object_id=item.canonical_id,
                field_name=item.field_name,
                value=item.value,
                namespace=item.canonical_type.value,
                source_ids=[
                    str(entry["source_id"])
                    for entry in item.provenance
                    if entry.get("source_id") is not None
                ],
            )
        )
    return states


def transcript_chunks_to_evidence(
    chunks: Iterable[TranscriptChunk],
    *,
    namespace: str = "evidence",
) -> list[ProjectEvidenceRecord]:
    """Expose authorized transcript chunks as searchable evidence, retaining exact provenance."""
    return [
        ProjectEvidenceRecord(
            evidence_id=chunk.chunk_id,
            evidence_type="procedural_transcript",
            title=f"Procedural transcript chunk {chunk.sequence}",
            text=chunk.text,
            namespace=namespace,
            structured_payload={
                "topics": chunk.topics,
                "sequence": chunk.sequence,
                "token_estimate": chunk.token_estimate,
            },
            source_ids=[chunk.source_id],
            authoritative=False,
        )
        for chunk in chunks
    ]
