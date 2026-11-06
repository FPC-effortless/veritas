from __future__ import annotations

from investigation_world.commercial.sre_release import SealedSRERelease
from investigation_world.portability.identity import portable_run_id, portable_task_id
from investigation_world.portability.models import (
    PortableCapability,
    PortableEnvironmentManifest,
    PortableReleaseIdentity,
    PortableResetContract,
    PortableSplit,
    PortableTask,
    PortableTasksetManifest,
    PortableVerifierContract,
    PortableVisibility,
)
from investigation_world.portability.sre import build_sre_portable_manifest
from investigation_world.portability.validation import validate_portable_manifest
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


def _release() -> SealedSRERelease:
    evidence = EvidenceManifest(
        items=[
            EvidenceItem(
                evidence_id="ev-1",
                source_group_id="source-a",
                source_uri="fixture://source-a",
                content_sha256="a" * 64,
            )
        ]
    )
    scenarios = [
        QualificationScenario(
            scenario_id="train-private-source-id",
            source_group_id="source-a",
            split=QualificationSplit.TRAIN,
            normalized_text="Service latency increased after a deploy.",
            public_digest="1" * 64,
            private_digest="a" * 64,
            metadata={"provider": "fixture", "causal_class": "regression"},
        ),
        QualificationScenario(
            scenario_id="dev-private-source-id",
            source_group_id="source-b",
            split=QualificationSplit.DEV,
            normalized_text="A dependency returned intermittent 503 responses.",
            public_digest="2" * 64,
            private_digest="b" * 64,
            metadata={"provider": "fixture", "causal_class": "transient"},
        ),
        QualificationScenario(
            scenario_id="secret-private-test-id",
            source_group_id="source-c",
            split=QualificationSplit.PRIVATE_TEST,
            normalized_text="Worker queues grew while demand exceeded available slots.",
            public_digest="3" * 64,
            private_digest="c" * 64,
            metadata={"provider": "fixture", "causal_class": "capacity"},
        ),
    ]
    candidate = QualificationCandidate(
        candidate_id="SRE-CAND-FIXTURE",
        domain="sre",
        version="sre-v4",
        scenarios=scenarios,
        evidence_manifest=evidence,
    )
    report = QualificationReport(
        report_id="QREPORT-FIXTURE",
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        evidence_manifest_id=evidence.manifest_id,
        panel_id="QPANEL-FIXTURE",
        gates=[QualificationGate(name="fixture", passed=True)],
        policy_means={},
        releaseable=True,
    )
    private_release = PrivateReleaseManifest(
        candidate_id=candidate.candidate_id,
        candidate_version=candidate.version,
        qualification_report_id=report.report_id,
        evidence_manifest_id=evidence.manifest_id,
        panel_id=report.panel_id,
        train_scenario_ids=[scenarios[0].scenario_id],
        dev_scenario_ids=[scenarios[1].scenario_id],
        private_test_scenario_ids=[scenarios[2].scenario_id],
    )
    return SealedSRERelease(
        candidate=candidate,
        qualification=report,
        private_release_manifest=private_release,
        cases=[],
    )


def _minimal_manifest() -> PortableEnvironmentManifest:
    release = PortableReleaseIdentity(
        candidate_id="candidate",
        candidate_version="v1",
        evidence_manifest_id="evidence",
        qualification_report_id="report",
        panel_id="panel",
        private_release_manifest_id="private-release",
    )
    task = PortableTask(
        task_id="task-1",
        split=PortableSplit.DEV,
        seed=7,
        agent_payload={"prompt": "fixture"},
        content_digest="digest",
        verifier_reference="verifier",
    )
    return PortableEnvironmentManifest(
        environment_id="fixture.environment",
        environment_version="v1",
        sku="Fixture",
        domain="fixture",
        description="fixture",
        visibility=PortableVisibility.BUYER_SAFE,
        release=release,
        taskset=PortableTasksetManifest(taskset_version="v1", visible_tasks=[task]),
        capabilities=[PortableCapability(capability_id="submit", description="submit")],
        reset=PortableResetContract(reset_semantics="deterministic fixture reset"),
        verifier=PortableVerifierContract(verifier_id="verifier", description="fixture verifier"),
    )


def test_manifest_identity_is_deterministic() -> None:
    first = _minimal_manifest()
    second = _minimal_manifest()
    assert first.manifest_id == second.manifest_id
    assert first.taskset.taskset_id == second.taskset.taskset_id


def test_task_and_run_identity_are_deterministic() -> None:
    task_a = portable_task_id(
        environment_id="env",
        environment_version="v1",
        source_digest="digest",
        split="dev",
        seed=3,
    )
    task_b = portable_task_id(
        environment_id="env",
        environment_version="v1",
        source_digest="digest",
        split="dev",
        seed=3,
    )
    assert task_a == task_b
    assert portable_run_id(
        environment_id="env",
        environment_version="v1",
        task_id=task_a,
        seed=3,
        invocation="fixture",
    ) == portable_run_id(
        environment_id="env",
        environment_version="v1",
        task_id=task_b,
        seed=3,
        invocation="fixture",
    )


def test_buyer_safe_sre_projection_omits_private_rows_and_source_ids(monkeypatch) -> None:
    release = _release()
    monkeypatch.setattr(
        "investigation_world.portability.sre.load_sealed_sre_release",
        lambda *args, **kwargs: release,
    )

    manifest = build_sre_portable_manifest(
        qualification_path=None,  # type: ignore[arg-type]
        visibility=PortableVisibility.BUYER_SAFE,
        public_sample_limit=10,
    )

    assert manifest.taskset.private_task_count == 1
    assert manifest.taskset.private_task_ids_included is False
    assert manifest.taskset.private_ground_truth_included is False
    assert all(task.split != PortableSplit.PRIVATE_TEST for task in manifest.taskset.visible_tasks)

    rendered = manifest.model_dump_json()
    assert "secret-private-test-id" not in rendered
    assert "train-private-source-id" not in rendered
    assert "dev-private-source-id" not in rendered
    assert "causal_class\":\"capacity" not in rendered
    assert validate_portable_manifest(manifest) == []


def test_private_operator_projection_can_include_private_agent_payload_without_oracle(monkeypatch) -> None:
    release = _release()
    monkeypatch.setattr(
        "investigation_world.portability.sre.load_sealed_sre_release",
        lambda *args, **kwargs: release,
    )

    manifest = build_sre_portable_manifest(
        qualification_path=None,  # type: ignore[arg-type]
        visibility=PortableVisibility.PRIVATE_OPERATOR,
    )

    assert manifest.taskset.private_task_count == 1
    assert manifest.taskset.private_task_ids_included is True
    assert manifest.taskset.private_ground_truth_included is False
    assert any(task.split == PortableSplit.PRIVATE_TEST for task in manifest.taskset.visible_tasks)
    assert "secret-private-test-id" not in manifest.model_dump_json()
    assert validate_portable_manifest(manifest) == []


def test_buyer_safe_manifest_rejects_private_task_rows() -> None:
    manifest = _minimal_manifest()
    private_task = manifest.taskset.visible_tasks[0].model_copy(update={"split": PortableSplit.PRIVATE_TEST})
    unsafe_taskset = PortableTasksetManifest(
        taskset_version="v1",
        visible_tasks=[private_task],
        private_task_count=1,
    )
    unsafe = manifest.model_copy(update={"taskset": unsafe_taskset, "manifest_id": ""})
    unsafe = PortableEnvironmentManifest.model_validate(unsafe.model_dump())

    codes = {issue.code for issue in validate_portable_manifest(unsafe)}
    assert "private_tasks_visible" in codes
