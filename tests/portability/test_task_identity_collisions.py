from __future__ import annotations

from investigation_world.commercial.sre_release import SealedSRERelease
from investigation_world.foundry.models import stable_hash
from investigation_world.portability.sre_private import build_sre_private_portable_tasks
from investigation_world.qualification import (
    EvidenceItem,
    EvidenceManifest,
    PrivateReleaseManifest,
    QualificationCandidate,
    QualificationGate,
    QualificationReport,
    QualificationScenario,
    QualificationSplit,
    SRECausalClass,
    SREQualificationCase,
)


def _release_with_duplicate_public_digests() -> SealedSRERelease:
    evidence = EvidenceManifest(
        items=[
            EvidenceItem(
                evidence_id="identity-fixture",
                source_group_id="source",
                source_uri="fixture://identity",
                content_sha256="f" * 64,
            )
        ]
    )
    scenarios = [
        QualificationScenario(
            scenario_id="private-case-a",
            source_group_id="source-a",
            split=QualificationSplit.PRIVATE_TEST,
            normalized_text="Same buyer-visible early evidence.",
            public_digest="1" * 64,
            private_digest="a" * 64,
            metadata={"provider": "fixture", "causal_class": "capacity"},
        ),
        QualificationScenario(
            scenario_id="private-case-b",
            source_group_id="source-b",
            split=QualificationSplit.PRIVATE_TEST,
            normalized_text="Same buyer-visible early evidence.",
            public_digest="1" * 64,
            private_digest="b" * 64,
            metadata={"provider": "fixture", "causal_class": "transient"},
        ),
    ]
    candidate = QualificationCandidate(
        candidate_id="SRE-CAND-IDENTITY-FIXTURE",
        domain="sre",
        version="sre-v4-fixture",
        scenarios=scenarios,
        evidence_manifest=evidence,
    )
    panel_payload = [
        [scenario.scenario_id, scenario.source_group_id, scenario.public_digest]
        for scenario in sorted(scenarios, key=lambda item: item.scenario_id)
    ]
    panel_id = f"QPANEL-{stable_hash(panel_payload)[:24].upper()}"
    report = QualificationReport(
        report_id="QREPORT-IDENTITY-FIXTURE",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        evidence_manifest_id=evidence.manifest_id,
        panel_id=panel_id,
        gates=[QualificationGate(name="fixture", passed=True)],
        policy_means={},
        releaseable=True,
    )
    private_release = PrivateReleaseManifest(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        qualification_report_id=report.report_id,
        evidence_manifest_id=evidence.manifest_id,
        panel_id=panel_id,
        train_scenario_ids=[],
        dev_scenario_ids=[],
        private_test_scenario_ids=[scenario.scenario_id for scenario in scenarios],
    )
    cases = [
        SREQualificationCase(
            scenario=scenario,
            public_text=scenario.normalized_text,
            causal_class=SRECausalClass(str(scenario.metadata["causal_class"])),
            provider="fixture",
        )
        for scenario in scenarios
    ]
    return SealedSRERelease(
        candidate=candidate,
        qualification=report,
        private_release_manifest=private_release,
        cases=cases,
    )


def test_duplicate_public_digests_get_unique_opaque_portable_ids() -> None:
    release = _release_with_duplicate_public_digests()

    first = build_sre_private_portable_tasks(release)
    second = build_sre_private_portable_tasks(release)

    assert [task.task_id for task in first] == [task.task_id for task in second]
    assert len({task.task_id for task in first}) == 2
    assert len({task.seed for task in first}) == 2

    serialized = "\n".join(task.model_dump_json() for task in first)
    assert "private-case-a" not in serialized
    assert "private-case-b" not in serialized
