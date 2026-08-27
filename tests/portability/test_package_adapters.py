from __future__ import annotations

import json
from pathlib import Path

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


def _compile_python_files(root: Path) -> None:
    for path in root.rglob("*.py"):
        compile(path.read_text(encoding="utf-8"), str(path), "exec")


def test_private_projection_matches_sealed_panel() -> None:
    release = _release()
    records = build_sre_private_portable_tasks(release)
    assert len(records) == 1
    assert records[0].expected_causal_class == "capacity"
    assert records[0].task_id.startswith("PTASK-")
    assert "private-id" not in records[0].model_dump_json()


def test_hud_package_is_deterministic_and_operator_private(tmp_path, monkeypatch) -> None:
    release, manifest = _manifest(monkeypatch)
    private_tasks = build_sre_private_portable_tasks(release)

    first = build_hud_sre_package(tmp_path / "first", manifest=manifest, private_tasks=private_tasks)
    second = build_hud_sre_package(tmp_path / "second", manifest=manifest, private_tasks=private_tasks)

    assert first.package_id == second.package_id
    assert {item.path for item in first.files} == {
        "Dockerfile.hud",
        "README.md",
        "env.py",
        "portable_manifest.json",
        "private_tasks.json",
        "pyproject.toml",
        "tasks.py",
    }
    _compile_python_files(tmp_path / "first")
    payload = json.loads((tmp_path / "first" / "private_tasks.json").read_text())
    assert payload[0]["expected_causal_class"] == "capacity"
    public_manifest = (tmp_path / "first" / "portable_manifest.json").read_text()
    assert "private-id" not in public_manifest
    assert "expected_causal_class" not in public_manifest
    readme = (tmp_path / "first" / "README.md").read_text()
    assert "docker build -f Dockerfile.hud" in readme
    assert "hud task start" in readme
    assert "hud task grade" in readme


def test_prime_package_is_deterministic_and_v1_shaped(tmp_path, monkeypatch) -> None:
    release, manifest = _manifest(monkeypatch)
    private_tasks = build_sre_private_portable_tasks(release)

    first = build_prime_sre_package(tmp_path / "first", manifest=manifest, private_tasks=private_tasks)
    second = build_prime_sre_package(tmp_path / "second", manifest=manifest, private_tasks=private_tasks)

    assert first.package_id == second.package_id
    _compile_python_files(tmp_path / "first")
    package_dir = tmp_path / "first" / "veritas_sre_prime"
    taskset_source = (package_dir / "taskset.py").read_text()
    legacy_source = (package_dir / "legacy.py").read_text()
    assert "import verifiers.v1 as vf" in taskset_source
    assert "class SRETaskset" in taskset_source
    assert "def load(self)" in taskset_source
    assert "def load_environment()" in legacy_source
    assert "compatibility-only" in legacy_source
    manifest_text = (package_dir / "portable_manifest.json").read_text()
    assert "private-id" not in manifest_text
    private_text = (package_dir / "private_tasks.json").read_text()
    assert '"expected_causal_class": "capacity"' in private_text
