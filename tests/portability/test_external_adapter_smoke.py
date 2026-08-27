from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from investigation_world.commercial.sre_release import SealedSRERelease
from investigation_world.portability.hud import build_hud_sre_package
from investigation_world.portability.prime import build_prime_sre_package
from investigation_world.portability.sre import build_sre_portable_manifest
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
            scenario_id="train-id",
            source_group_id="source-a",
            split=QualificationSplit.TRAIN,
            normalized_text="A deploy preceded a latency regression.",
            public_digest="1" * 64,
            private_digest="a" * 64,
            metadata={"provider": "fixture", "causal_class": "regression"},
        ),
        QualificationScenario(
            scenario_id="private-id",
            source_group_id="source-b",
            split=QualificationSplit.PRIVATE_TEST,
            normalized_text="Demand exceeded worker capacity and queues grew.",
            public_digest="2" * 64,
            private_digest="b" * 64,
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
        dev_scenario_ids=[],
        private_test_scenario_ids=[scenarios[1].scenario_id],
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


def _manifest(monkeypatch):
    release = _release()
    monkeypatch.setattr(
        "investigation_world.portability.sre.load_sealed_sre_release",
        lambda *args, **kwargs: release,
    )
    return release, build_sre_portable_manifest(
        qualification_path=None,  # type: ignore[arg-type]
        public_sample_limit=8,
    )


def test_generated_hud_package_loads_with_current_sdk(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("hud")
    release, manifest = _manifest(monkeypatch)
    package_root = tmp_path / "hud"
    build_hud_sre_package(
        package_root,
        manifest=manifest,
        private_tasks=build_sre_private_portable_tasks(release),
    )

    sys.path.insert(0, str(package_root))
    try:
        env_module = importlib.import_module("env")
        tasks_module = importlib.import_module("tasks")
        assert env_module.env is not None
        assert len(tasks_module.tasks) == 1
    finally:
        sys.path.remove(str(package_root))
        sys.modules.pop("env", None)
        sys.modules.pop("tasks", None)


def test_generated_prime_package_loads_with_current_v1_sdk(tmp_path: Path, monkeypatch) -> None:
    pytest.importorskip("verifiers.v1")
    release, manifest = _manifest(monkeypatch)
    package_root = tmp_path / "prime"
    build_prime_sre_package(
        package_root,
        manifest=manifest,
        private_tasks=build_sre_private_portable_tasks(release),
    )

    sys.path.insert(0, str(package_root))
    try:
        module = importlib.import_module("veritas_sre_prime")
        taskset = module.SRETaskset()
        tasks = taskset.load()
        assert len(tasks) == 1
        assert tasks[0].data.portable_task_id.startswith("PTASK-")
    finally:
        sys.path.remove(str(package_root))
        for name in list(sys.modules):
            if name == "veritas_sre_prime" or name.startswith("veritas_sre_prime."):
                sys.modules.pop(name, None)
