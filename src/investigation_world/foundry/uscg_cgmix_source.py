from __future__ import annotations

import html
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

from defusedxml import ElementTree as DefusedET  # type: ignore[import-untyped]

_ENDPOINT = "https://cgmix.uscg.mil/xml/IIRData.asmx"
_HOST = "cgmix.uscg.mil"
_NAMESPACE = "https://cgmix.uscg.mil/xml/"
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024

_SEARCH_OPERATION = "getIIRIncidentSearchXMLString"
_PUBLIC_OPERATIONS = {
    "getIIRIncidentBriefXMLString": "IncidentBrief",
    "getIIRInvolvedVesselsXMLString": "InvolvedVessels",
    "getIIRInvolvedFacilitiesXMLString": "InvolvedFacilities",
    "getIIRPersonalCasualtySummaryXMLString": "PersonalCasualties",
    "getIIRVesselDamageSummaryXMLString": "VesselDamage",
    "getIIRWaterSegmentsXMLString": "Waterways",
    "getIIRResponseResourcesXMLString": "ResponseResources",
}
_VERIFIER_OPERATIONS = {
    "getIIRIncidentSummaryXMLString": "IncidentSummary",
    "getIIRReferralForEnforcementXMLString": "EnforcementReferrals",
    "getIIRReferralForEnforcementActionXMLString": "EnforcementActions",
}
_ALLOWED_OPERATIONS = {
    _SEARCH_OPERATION,
    *_PUBLIC_OPERATIONS,
    *_VERIFIER_OPERATIONS,
}

UscgFetcher = Callable[[str, dict[str, str], float], list[dict[str, str]]]


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _require_operation(operation: str) -> None:
    if operation not in _ALLOWED_OPERATIONS:
        raise ValueError(f"unsupported USCG IIR operation: {operation}")


def _soap_envelope(operation: str, parameters: dict[str, str]) -> bytes:
    _require_operation(operation)
    body = ET.Element(f"{{{_NAMESPACE}}}{operation}")
    for key, value in parameters.items():
        child = ET.SubElement(body, f"{{{_NAMESPACE}}}{key}")
        child.text = value
    envelope = ET.Element(
        "{http://schemas.xmlsoap.org/soap/envelope/}Envelope",
    )
    soap_body = ET.SubElement(
        envelope,
        "{http://schemas.xmlsoap.org/soap/envelope/}Body",
    )
    soap_body.append(body)
    return ET.tostring(envelope, encoding="utf-8", xml_declaration=True)


def _dataset_rows(xml_text: str) -> list[dict[str, str]]:
    if not xml_text.strip():
        return []
    root = DefusedET.fromstring(xml_text)
    rows: list[dict[str, str]] = []
    for element in root.iter():
        children = list(element)
        if not children:
            continue
        if all(not list(child) for child in children):
            row = {
                _local_name(child.tag): (child.text or "").strip()
                for child in children
            }
            if row:
                rows.append(row)
    return rows


def parse_uscg_soap_response(payload: bytes, operation: str) -> list[dict[str, str]]:
    _require_operation(operation)
    root = DefusedET.fromstring(payload)
    expected = f"{operation}Result"
    result_text: str | None = None
    for element in root.iter():
        if _local_name(element.tag) == expected:
            result_text = element.text or ""
            break
    if result_text is None:
        raise ValueError(f"USCG SOAP response is missing {expected}")
    inner_xml = html.unescape(result_text)
    return _dataset_rows(inner_xml)


def fetch_uscg_iir_operation(
    operation: str,
    parameters: dict[str, str],
    timeout_seconds: float = 30.0,
) -> list[dict[str, str]]:
    _require_operation(operation)
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    request = urllib.request.Request(
        _ENDPOINT,
        data=_soap_envelope(operation, parameters),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{_NAMESPACE}{operation}"',
            "User-Agent": "VeritasInvestigationCorpus/1.0",
        },
        method="POST",
    )
    # B310 is mitigated by a fixed HTTPS endpoint and redirect host validation.
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:  # nosec B310
        final_url = response.geturl()
        parsed = urllib.parse.urlparse(final_url)
        if parsed.scheme.casefold() != "https" or parsed.hostname != _HOST:
            raise ValueError(f"USCG SOAP redirect is not authorized: {final_url}")
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise ValueError("USCG SOAP response exceeded the safety cap")
    return parse_uscg_soap_response(payload, operation)


def _activity_id(row: dict[str, str]) -> str:
    value = row.get("ActivityId", "").strip()
    if not value or not value.isdigit():
        raise ValueError(f"USCG search row has invalid ActivityId: {value!r}")
    return value


def _first_text(rows: list[dict[str, str]], field: str) -> str:
    for row in rows:
        value = row.get(field, "").strip()
        if value:
            return value
    return ""


def _fetch_section(
    fetcher: UscgFetcher,
    operation: str,
    activity_id: str,
    timeout_seconds: float,
) -> list[dict[str, str]]:
    return fetcher(
        operation,
        {"ActivityId": activity_id},
        timeout_seconds,
    )


def assemble_uscg_iir_record(
    search_row: dict[str, str],
    *,
    fetcher: UscgFetcher = fetch_uscg_iir_operation,
    timeout_seconds: float = 30.0,
) -> dict[str, Any]:
    activity_id = _activity_id(search_row)
    record: dict[str, Any] = {
        "ActivityId": activity_id,
        "CasesId": search_row.get("CasesId", "").strip(),
        "Title": search_row.get("Title", "").strip(),
        "StartDtTm": search_row.get("StartDtTm", "").strip(),
        "CloseDtTm": search_row.get("CloseDtTm", "").strip(),
    }
    if not record["Title"] or not record["StartDtTm"]:
        raise ValueError(f"USCG search row {activity_id} lacks title or start date")

    for operation, field in _PUBLIC_OPERATIONS.items():
        rows = _fetch_section(fetcher, operation, activity_id, timeout_seconds)
        if field == "IncidentBrief":
            record[field] = _first_text(rows, "IncidentBrief")
        else:
            record[field] = rows

    for operation, field in _VERIFIER_OPERATIONS.items():
        record[field] = _fetch_section(fetcher, operation, activity_id, timeout_seconds)
    return record


def discover_uscg_iir_records(
    *,
    activity_id: int = 0,
    vessel_service: str = "",
    vessel_name: str = "",
    organization_name: str = "",
    involved_facility: str = "",
    keyword: str = "",
    maximum_cases: int = 25,
    timeout_seconds: float = 30.0,
    fetcher: UscgFetcher = fetch_uscg_iir_operation,
) -> list[dict[str, Any]]:
    if activity_id < 0:
        raise ValueError("activity_id may not be negative")
    if maximum_cases < 1 or maximum_cases > 500:
        raise ValueError("maximum_cases must be between 1 and 500")
    search_rows = fetcher(
        _SEARCH_OPERATION,
        {
            "ActivityId": str(activity_id),
            "VesselService": vessel_service,
            "VesselName": vessel_name,
            "OrgName": organization_name,
            "InvolvedFacility": involved_facility,
            "KeyWord": keyword,
        },
        timeout_seconds,
    )
    deduplicated: dict[str, dict[str, str]] = {}
    for row in search_rows:
        deduplicated[_activity_id(row)] = row
    selected = [
        deduplicated[key]
        for key in sorted(deduplicated, key=int)[:maximum_cases]
    ]
    return [
        assemble_uscg_iir_record(
            row,
            fetcher=fetcher,
            timeout_seconds=timeout_seconds,
        )
        for row in selected
    ]


def write_uscg_iir_staging(records: list[dict[str, Any]], destination: Path) -> dict[str, Any]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, indent=2, sort_keys=True) + "\n"
    destination.write_text(payload, encoding="utf-8")
    return {
        "records": len(records),
        "byte_count": len(payload.encode("utf-8")),
        "destination": str(destination),
    }
