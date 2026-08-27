from collections import Counter

from investigation_world.qualification.cluster_split import repartition_candidate_by_near_duplicates
from investigation_world.qualification.models import (
    PolicyClass,
    QualificationSplit,
    QualificationThresholds,
)
from investigation_world.qualification.protocol import qualify_candidate
from investigation_world.qualification.sre import SRECausalClass, compile_sre_candidate, execute_sre_policy_suite
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


def test_statuspage_adapter_does_not_call_fix_deployment_a_regression():
    payload = {
        "incidents": [
            {
                "id": "fix-deploy",
                "name": "Intermittent API errors",
                "status": "resolved",
                "created_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-01-01T02:00:00Z",
                "incident_updates": [
                    {"created_at": "2026-01-01T00:10:00Z", "body": "Investigating intermittent API errors."},
                    {"created_at": "2026-01-01T01:00:00Z", "body": "Errors were transient and automatically recovered."},
                    {"created_at": "2026-01-01T02:00:00Z", "body": "We deployed a defensive fix and resolved the incident."},
                ],
            }
        ]
    }

    incident = parse_statuspage_incidents("example", payload, early_update_count=1)[0]

    assert incident.causal_class == SRECausalClass.TRANSIENT
    assert incident.metadata["explicit_causal_signal"] is True
    assert incident.metadata["causal_label_rule"] == "explicit-transient"


def test_statuspage_adapter_can_reject_unlabelled_fallback_cases():
    payload = {
        "incidents": [
            {
                "id": "unknown-cause",
                "name": "Elevated errors",
                "status": "resolved",
                "created_at": "2026-01-01T00:00:00Z",
                "resolved_at": "2026-01-01T02:00:00Z",
                "incident_updates": [
                    {"created_at": "2026-01-01T00:10:00Z", "body": "Investigating elevated errors."},
                    {"created_at": "2026-01-01T02:00:00Z", "body": "The incident has been resolved."},
                ],
            }
        ]
    }

    assert parse_statuspage_incidents(
        "example",
        payload,
        early_update_count=1,
        require_explicit_causal_label=True,
    ) == []


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


def test_stratified_duplicate_safe_split_protects_train_and_private_causal_coverage():
    incidents = []
    for provider in ("one", "two", "three", "four", "five"):
        incidents.extend(parse_statuspage_incidents(provider, _payload(provider, 24)))
    candidate, _ = compile_sre_candidate(incidents, version="sre-test-stratified")

    candidate, mapping = repartition_candidate_by_near_duplicates(
        candidate,
        stratum_metadata_key="causal_class",
        minimum_private_scenarios_per_stratum=5,
        minimum_train_scenarios_per_stratum=3,
    )

    private_counts = Counter(
        str(scenario.metadata["causal_class"])
        for scenario in candidate.scenarios
        if mapping[scenario.scenario_id] == QualificationSplit.PRIVATE_TEST
    )
    train_counts = Counter(
        str(scenario.metadata["causal_class"])
        for scenario in candidate.scenarios
        if mapping[scenario.scenario_id] == QualificationSplit.TRAIN
    )

    assert set(private_counts) == {item.value for item in SRECausalClass}
    assert min(private_counts.values()) >= 5
    assert set(train_counts) == {item.value for item in SRECausalClass}
    assert min(train_counts.values()) >= 3


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
