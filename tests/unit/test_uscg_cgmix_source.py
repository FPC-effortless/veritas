from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from investigation_world.foundry.public_investigation_corpus import (
    compile_structured_investigation_corpus,
    load_structured_source_profile,
)
from investigation_world.foundry.uscg_cgmix_source import (
    discover_uscg_iir_records,
    parse_uscg_soap_response,
    write_uscg_iir_staging,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE_PATH = REPO_ROOT / "datasets/public_investigations/profiles/uscg_cgmix_iir_v1.json"


def test_parse_uscg_soap_xml_string_response() -> None:
    payload = b"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <getIIRIncidentSearchXMLStringResponse xmlns="https://cgmix.uscg.mil/xml/">
      <getIIRIncidentSearchXMLStringResult>
        &lt;NewDataSet&gt;&lt;Table&gt;&lt;ActivityId&gt;42&lt;/ActivityId&gt;
        &lt;CasesId&gt;7&lt;/CasesId&gt;&lt;Title&gt;Grounding&lt;/Title&gt;
        &lt;StartDtTm&gt;2025-01-02T03:04:05&lt;/StartDtTm&gt;
        &lt;CloseDtTm&gt;2025-02-03T00:00:00&lt;/CloseDtTm&gt;
        &lt;/Table&gt;&lt;/NewDataSet&gt;
      </getIIRIncidentSearchXMLStringResult>
    </getIIRIncidentSearchXMLStringResponse>
  </soap:Body>
</soap:Envelope>
"""

    rows = parse_uscg_soap_response(payload, "getIIRIncidentSearchXMLString")

    assert rows == [
        {
            "ActivityId": "42",
            "CasesId": "7",
            "Title": "Grounding",
            "StartDtTm": "2025-01-02T03:04:05",
            "CloseDtTm": "2025-02-03T00:00:00",
        }
    ]


def _fake_fetcher(
    operation: str,
    parameters: dict[str, str],
    timeout_seconds: float,
) -> list[dict[str, str]]:
    assert timeout_seconds > 0
    if operation == "getIIRIncidentSearchXMLString":
        return [
            {
                "ActivityId": "1002",
                "CasesId": "502",
                "Title": "Second casualty",
                "StartDtTm": "2025-06-01T10:00:00",
                "CloseDtTm": "2025-07-01T10:00:00",
            },
            {
                "ActivityId": "1001",
                "CasesId": "501",
                "Title": "First casualty",
                "StartDtTm": "2025-05-01T09:00:00",
                "CloseDtTm": "2025-06-01T09:00:00",
            },
        ]
    assert parameters == {"ActivityId": "1001"}
    if operation == "getIIRIncidentBriefXMLString":
        return [{"IncidentBrief": "A towing vessel grounded in restricted visibility."}]
    if operation == "getIIRInvolvedVesselsXMLString":
        return [{"Name": "EXAMPLE", "VesselRoleLookupName": "Involved"}]
    if operation == "getIIRInvolvedFacilitiesXMLString":
        return []
    if operation == "getIIRPersonalCasualtySummaryXMLString":
        return [{"CasualtyStatusLookupName": "Injured", "TotalPeopleAtRisk": "2"}]
    if operation == "getIIRVesselDamageSummaryXMLString":
        return [{"VesselDamageInDollars": "100000"}]
    if operation == "getIIRWaterSegmentsXMLString":
        return [{"WaterwayName": "TEST RIVER", "Latitude": "45", "Longitude": "-70"}]
    if operation == "getIIRResponseResourcesXMLString":
        return [{"KindLookupName": "Tug", "ResourceName": "ASSIST"}]
    if operation == "getIIRIncidentSummaryXMLString":
        return [
            {
                "IsSeriousMarineIncident": "true",
                "UnitedStatesMarineCasualtyClassificationLookupName": "Grounding",
                "TypeLookupName": "Marine Casualty Investigation",
            }
        ]
    if operation == "getIIRReferralForEnforcementXMLString":
        return [{"ActivitySubTypeDesc": "Civil Penalty"}]
    if operation == "getIIRReferralForEnforcementActionXMLString":
        return [{"FinalAgencyActionLookupName": "Closed"}]
    raise AssertionError(f"unexpected operation: {operation}")


def test_uscg_discovery_enriches_scoped_case_and_seals_labels(tmp_path: Path) -> None:
    records = discover_uscg_iir_records(
        maximum_cases=1,
        timeout_seconds=1,
        fetcher=_fake_fetcher,
    )

    assert len(records) == 1
    assert records[0]["ActivityId"] == "1001"
    assert records[0]["IncidentBrief"].startswith("A towing vessel")
    assert records[0]["IncidentSummary"][0]["IsSeriousMarineIncident"] == "true"

    staging = tmp_path / "uscg.json"
    write_uscg_iir_staging(records, staging)
    profile = load_structured_source_profile(PROFILE_PATH)
    corpus = compile_structured_investigation_corpus(
        profile,
        staging,
        dataset_id="uscg-test-v1",
        version="1.0.0",
        as_of=date(2026, 8, 28),
    )

    public = corpus.cases[0].public_projection()
    verifier = corpus.cases[0].verifier_projection()
    public_text = json.dumps(public, sort_keys=True)
    assert "1001" not in public_text
    assert "SeriousMarineIncident" not in public_text
    assert "Civil Penalty" not in public_text
    assert public["evidence"]["incident_brief"].startswith("A towing vessel")
    assert verifier["verifier"]["source_activity_id"] == "1001"
    assert verifier["verifier"]["incident_summary"][0]["IsSeriousMarineIncident"] == "true"
