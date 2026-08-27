import json

import pytest

from investigation_world.commercial.sre_release import load_sealed_sre_release
from investigation_world.foundry.models import stable_hash
from investigation_world.qualification import (
    EvidenceItem,
    EvidenceManifest,
    PrivateReleaseManifest,
    QualificationCandidate,
    QualificationGate,
    QualificationReport,
    QualificationScenario,
    QualificationSplit,
)


def _write_release(tmp_path):
    evidence = EvidenceManifest(
        items=[
            EvidenceItem(
                evidence_id="INCIDENT-1",
                source_group_id="provider:1",
                source_uri="https://status.example/incidents/1",
                content_sha256="a" * 64,
                metadata={"provider": "provider", "incident_id": "1"},
            )
        ]
    )
    labels = ["regression", "infrastructure", "capacity", "transient"]
    scenarios = [
        QualificationScenario(
            scenario_id=f"SRE-{index}",
            source_group_id=f"provider:{index}",
            split=QualificationSplit.PRIVATE_TEST,
            normalized_text=f"public incident evidence {index}",
            public_digest=stable_hash(f"public incident evidence {index}"),
            private_digest=stable_hash(["private", label]),
            metadata={"provider": "provider", "causal_class": label},
        )
        for index, label in enumerate(labels, start=1)
    ]
    candidate = QualificationCandidate(
        candidate_id="SRE-CAND-TEST",
        domain="sre_incident_response",
        version="sre-v4",
        scenarios=scenarios,
        evidence_manifest=evidence,
    )
    panel_payload = [
        [scenario.scenario_id, scenario.source_group_id, scenario.public_digest]
        for scenario in sorted(scenarios, key=lambda item: item.scenario_id)
    ]
    panel_id = f"QPANEL-{stable_hash(panel_payload)[:24].upper()}"
    report = QualificationReport(
        report_id="QREPORT-TEST",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        evidence_manifest_id=evidence.manifest_id,
        panel_id=panel_id,
        gates=[QualificationGate(name="sealed", passed=True)],
        policy_means={},
        releaseable=True,
    )
    release = PrivateReleaseManifest(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        qualification_report_id=report.report_id,
        evidence_manifest_id=evidence.manifest_id,
        panel_id=panel_id,
        train_scenario_ids=[],
        dev_scenario_ids=[],
        private_test_scenario_ids=sorted(scenario.scenario_id for scenario in scenarios),
    )
    path = tmp_path / "qualification.json"
    path.write_text(
        json.dumps(
            {
                "status": "benchmark_candidate",
                "candidate": candidate.model_dump(mode="json"),
                "qualification": report.model_dump(mode="json"),
                "private_release_manifest": release.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    return path, candidate, report, release


def test_load_sealed_release_consumes_exact_candidate_panel(tmp_path):
    path, candidate, report, release = _write_release(tmp_path)

    sealed = load_sealed_sre_release(
        path,
        expected_candidate_id=candidate.candidate_id,
        expected_evidence_manifest_id=candidate.evidence_manifest.manifest_id,
        expected_report_id=report.report_id,
        expected_panel_id=report.panel_id,
        expected_private_release_manifest_id=release.manifest_id,
    )

    assert sealed.candidate.candidate_id == candidate.candidate_id
    assert sealed.qualification.panel_id == report.panel_id
    assert sealed.private_release_manifest.manifest_id == release.manifest_id
    assert {case.causal_class.value for case in sealed.cases} == {
        "regression",
        "infrastructure",
        "capacity",
        "transient",
    }


def test_load_sealed_release_rejects_expected_panel_mismatch(tmp_path):
    path, _, _, _ = _write_release(tmp_path)

    with pytest.raises(RuntimeError, match="panel_id mismatch"):
        load_sealed_sre_release(path, expected_panel_id="QPANEL-WRONG")
