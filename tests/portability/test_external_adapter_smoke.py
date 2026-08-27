from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

from investigation_world.commercial.sre_evaluation import parse_sre_prediction
from investigation_world.commercial.sre_release import SealedSRERelease
from investigation_world.portability.evidence import build_sre_portable_qualification_evidence
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


def _clean_install(package_root: Path, install_root: Path) -> Path:
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(install_root),
            str(package_root),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return install_root


def _canonical_value(raw: str) -> str | None:
    parsed = parse_sre_prediction(raw)
    return parsed.value if parsed is not None else None


def _canonical_reward(raw: str, expected: str) -> float:
    return float(_canonical_value(raw) == expected)


def _assert_parser_parity(parser) -> None:
    samples = [
        '{"causal_class":"capacity"}',
        "regression",
        'prefix {"causal_class":"transient"} suffix',
        "not-a-valid-class",
    ]
    for raw in samples:
        assert parser(raw) == _canonical_value(raw)


def _assert_reward_parity(scorer) -> None:
    expected = "capacity"
    samples = [
        '{"causal_class":"capacity"}',
        "capacity",
        'prefix {"causal_class":"capacity"} suffix',
        '{"causal_class":"regression"}',
        "not-a-valid-class",
    ]
    for raw in samples:
        assert scorer(raw, expected) == _canonical_reward(raw, expected)


def test_generated_hud_package_clean_installs_and_loads_with_current_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    pytest.importorskip("hud")
    release, manifest = _manifest(monkeypatch)
    qualification_evidence = build_sre_portable_qualification_evidence(release)
    package_root = tmp_path / "hud-src"
    build_hud_sre_package(
        package_root,
        manifest=manifest,
        private_tasks=build_sre_private_portable_tasks(release),
        qualification_evidence=qualification_evidence,
    )
    install_root = _clean_install(package_root, tmp_path / "hud-install")

    sys.path.insert(0, str(install_root))
    try:
        env_module = importlib.import_module("env")
        tasks_module = importlib.import_module("tasks")
        assert env_module.env is not None
        assert len(tasks_module.tasks) == 1
        assert Path(tasks_module.__file__).resolve().is_relative_to(install_root.resolve())
        assert (install_root / "qualification_evidence.json").is_file()
        _assert_parser_parity(env_module._parse_prediction)
        _assert_reward_parity(env_module._score_prediction)
    finally:
        sys.path.remove(str(install_root))
        sys.modules.pop("env", None)
        sys.modules.pop("tasks", None)


def test_generated_prime_package_clean_installs_and_loads_with_current_v1_sdk(
    tmp_path: Path, monkeypatch
) -> None:
    vf = pytest.importorskip("verifiers.v1")
    release, manifest = _manifest(monkeypatch)
    qualification_evidence = build_sre_portable_qualification_evidence(release)
    package_root = tmp_path / "prime-src"
    build_prime_sre_package(
        package_root,
        manifest=manifest,
        private_tasks=build_sre_private_portable_tasks(release),
        qualification_evidence=qualification_evidence,
    )
    install_root = _clean_install(package_root, tmp_path / "prime-install")

    sys.path.insert(0, str(install_root))
    try:
        module = importlib.import_module("veritas_sre_prime")
        taskset_module = importlib.import_module("veritas_sre_prime.taskset")
        taskset = module.SRETaskset(vf.TasksetConfig())
        tasks = taskset.load()
        assert len(tasks) == 1
        assert tasks[0].data.portable_task_id.startswith("PTASK-")
        package_dir = Path(module.__file__).resolve().parent
        assert package_dir.is_relative_to(install_root.resolve())
        assert (package_dir / "portable_manifest.json").is_file()
        assert (package_dir / "qualification_evidence.json").is_file()
        _assert_parser_parity(taskset_module._parse_prediction)
        _assert_reward_parity(taskset_module._score_prediction)

        legacy_env = module.load_environment()
        assert len(legacy_env.dataset) == 1
    finally:
        sys.path.remove(str(install_root))
        for name in list(sys.modules):
            if name == "veritas_sre_prime" or name.startswith("veritas_sre_prime."):
                sys.modules.pop(name, None)
