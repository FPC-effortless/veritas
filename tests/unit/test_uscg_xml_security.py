from __future__ import annotations

import pytest
from defusedxml.common import EntitiesForbidden

from investigation_world.foundry.uscg_cgmix_source import parse_uscg_soap_response


def test_uscg_parser_rejects_xml_entity_declarations() -> None:
    payload = b"""<?xml version="1.0"?>
<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <getIIRIncidentSearchXMLStringResponse xmlns="https://cgmix.uscg.mil/xml/">
      <getIIRIncidentSearchXMLStringResult>&xxe;</getIIRIncidentSearchXMLStringResult>
    </getIIRIncidentSearchXMLStringResponse>
  </soap:Body>
</soap:Envelope>
"""

    with pytest.raises(EntitiesForbidden):
        parse_uscg_soap_response(payload, "getIIRIncidentSearchXMLString")
