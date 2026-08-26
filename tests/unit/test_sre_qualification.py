from investigation_world.qualification.models import PolicyClass, QualificationThresholds
from investigation_world.qualification.protocol import qualify_candidate
from investigation_world.qualification.sre import compile_sre_candidate, execute_sre_policy_suite
from investigation_world.qualification.sre_sources import parse_statuspage_incidents


def _payload(provider: str, count: int = 20) -> dict:
    incidents = []
    causes = [
        ("Deployment introduced an application regression; rollback completed.", "deploy regression rollback"),
        ("Database network connectivity failed in one region; infrastructure restored.", "network database region"),
        ("Traffic exceeded available capacity and saturated workers; capacity added.", "traffic capacity saturation"),
        ("Intermittent transient errors recovered without a persistent fault.", "transient intermittent recovered"),
    ]
    for index in range(count):
        private, early_hint = causes[index % len(causes)]
        incidents.append(
            {
                "id": f"{provider}-{index}",
                "name": f"Service incident {index}",
                "status": "resolved",
                "impact": "major" if index % 3 == 0 else "minor",
                "created_at": f"2026-01-{(index % 27) + 1:02d}T00:00:00Z",
                "started_at": f"2026-01-{(index % 27) + 1:02d}T00:00:00Z",
                "resolved_at": f"2026-01-{(index % 27) + 1:02d}T04:00:00Z",
                "shortlink": f"https://status.example/{provider}/{index}",
                "incident_updates": [
                    {"created_at": "2026-01-01T00:10:00Z", "body": f"Investigating elevated errors {early_hint}."},
                    {"created_at": "2026-01-01T00:30:00Z", "body": "Mitigation is in progress."},
                    {"created_at": "2026-01-01T03:00:00Z", "body": private},
                ],
            }
        )
    return {"incidents": incidents}


def test_statuspage_adapter_keeps_early_evidence_public_and_resolution_private():
    incidents = parse_statuspage_incidents("github", _payload("github", 1))
    incident = incidents[0]

    assert len(incident.early_updates) == 2
    assert len(incident.resolution_updates) == 1
    assert "rollback completed" not in incident.public_text
    assert "rollback completed" in incident.private_text


def test_sre_candidate_is_source_disjoint_and_runs_all_policy_classes():
    incidents = []
    for provider in ("github", "atlassian", "cloudflare", "datadog", "digitalocean"):
        incidents.extend(parse_statuspage_incidents(provider, _payload(provider, 20)))
    candidate, cases = compile_sre_candidate(incidents)
    evaluations = execute_sre_policy_suite(cases, random_seed=7)

    assert len(candidate.scenarios) == 100
    assert len({item.source_group_id for item in candidate.scenarios}) == 100
    assert {item.policy_class for item in evaluations} == set(PolicyClass)
    panels = [{outcome.scenario_id for outcome in item.outcomes} for item in evaluations]
    assert all(panel == panels[0] for panel in panels)


def test_sre_candidate_flows_through_generic_qualification_protocol():
    incidents = []
    for provider in ("github", "atlassian", "cloudflare", "datadog", "digitalocean"):
        incidents.extend(parse_statuspage_incidents(provider, _payload(provider, 40)))
    candidate, cases = compile_sre_candidate(incidents)
    evaluations = execute_sre_policy_suite(cases, random_seed=11)
    report = qualify_candidate(
        candidate,
        evaluations,
        thresholds=QualificationThresholds(
            minimum_private_test_scenarios=30,
            maximum_competent_reward=0.99,
            minimum_oracle_competent_gap=0.0,
            maximum_random_reward=0.60,
            maximum_exploit_reward=0.0,
        ),
    )

    assert report.policy_means[PolicyClass.ORACLE] == 1.0
    assert report.policy_means[PolicyClass.EXPLOIT] == 0.0
    assert next(g for g in report.gates if g.name == "source_disjoint").passed
    assert next(g for g in report.gates if g.name == "private_leakage").passed
