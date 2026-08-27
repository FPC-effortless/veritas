from investigation_world.qualification.sre import SRECausalClass
from investigation_world.qualification.sre_sources import parse_statuspage_incidents


def _incident(private_body: str) -> dict:
    return {
        "incidents": [
            {
                "id": "infra-1",
                "name": "Service degradation",
                "status": "resolved",
                "created_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-01-01T02:00:00Z",
                "incident_updates": [
                    {
                        "created_at": "2026-01-01T00:10:00Z",
                        "body": "We are investigating degraded service availability.",
                    },
                    {
                        "created_at": "2026-01-01T02:00:00Z",
                        "body": private_body,
                    },
                ],
            }
        ]
    }


def test_cloud_provider_network_interruption_is_explicit_infrastructure():
    incidents = parse_statuspage_incidents(
        "newrelic",
        _incident("Services recovered following resolution of the cloud provider network interruption."),
        early_update_count=1,
        require_explicit_causal_label=True,
    )

    assert len(incidents) == 1
    assert incidents[0].causal_class == SRECausalClass.INFRASTRUCTURE
    assert incidents[0].metadata["causal_label_rule"] == "explicit-infrastructure"


def test_network_connectivity_issues_are_explicit_infrastructure():
    incidents = parse_statuspage_incidents(
        "newrelic",
        _incident("A provider interruption resulted in intermittent network connectivity issues."),
        early_update_count=1,
        require_explicit_causal_label=True,
    )

    assert len(incidents) == 1
    assert incidents[0].causal_class == SRECausalClass.INFRASTRUCTURE
