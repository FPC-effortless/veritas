from __future__ import annotations

import argparse
import json
from pathlib import Path

from investigation_world.foundry.models import stable_hash
from investigation_world.portability.hud import build_hud_sre_package
from investigation_world.portability.prime import build_prime_sre_package
from investigation_world.portability.sre import build_sre_portable_manifest
from investigation_world.portability.sre_private import build_sre_private_portable_tasks
from investigation_world.commercial.sre_release import load_sealed_sre_release
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


def _panel_id(candidate: QualificationCandidate) -> str:
    private = sorted(
        (
            scenario
            for scenario in candidate.scenarios
            if scenario.split == QualificationSplit.PRIVATE_TEST
        ),
        key=lambda scenario: scenario.scenario_id,
    )
    payload = [
        [scenario.scenario_id, scenario.source_group_id, scenario.public_digest]
        for scenario in private
    ]
    return f"QPANEL-{stable_hash(payload)[:24].upper()}"


def write_fixture_qualification(path: Path) -> Path:
    evidence = EvidenceManifest(
        items=[
            EvidenceItem(
                evidence_id="fixture-evidence",
                source_group_id="fixture-source",
                source_uri="fixture://portability",
                content_sha256="a" * 64,
            )
        ]
    )
    scenarios = [
        QualificationScenario(
            scenario_id="fixture-train",
            source_group_id="fixture-source-train",
            split=QualificationSplit.TRAIN,
            normalized_text="A deployment caused a persistent latency regression.",
            public_digest="1" * 64,
            private_digest="a" * 64,
            metadata={"provider": "fixture", "causal_class": "regression"},
        ),
        QualificationScenario(
            scenario_id="fixture-private",
            source_group_id="fixture-source-private",
            split=QualificationSplit.PRIVATE_TEST,
            normalized_text="Worker demand exceeded capacity and queues accumulated.",
            public_digest="2" * 64,
            private_digest="b" * 64,
            metadata={"provider": "fixture", "causal_class": "capacity"},
        ),
    ]
    candidate = QualificationCandidate(
        candidate_id="SRE-CAND-PORTABILITY-FIXTURE",
        domain="sre",
        version="sre-v4-fixture",
        scenarios=scenarios,
        evidence_manifest=evidence,
    )
    panel_id = _panel_id(candidate)
    report = QualificationReport(
        report_id="QREPORT-PORTABILITY-FIXTURE",
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
        train_scenario_ids=[scenarios[0].scenario_id],
        dev_scenario_ids=[],
        private_test_scenario_ids=[scenarios[1].scenario_id],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "status": "benchmark_candidate",
                "candidate": candidate.model_dump(mode="json"),
                "qualification": report.model_dump(mode="json"),
                "private_release_manifest": private_release.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Build deterministic portability fixture exports")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    qualification_path = write_fixture_qualification(args.output / "qualification.json")
    release = load_sealed_sre_release(qualification_path)
    manifest = build_sre_portable_manifest(qualification_path, public_sample_limit=1)
    private_tasks = build_sre_private_portable_tasks(release)

    hud = build_hud_sre_package(args.output / "hud", manifest=manifest, private_tasks=private_tasks)
    prime = build_prime_sre_package(
        args.output / "prime", manifest=manifest, private_tasks=private_tasks
    )
    print(
        json.dumps(
            {
                "manifest_id": manifest.manifest_id,
                "hud_package_id": hud.package_id,
                "prime_package_id": prime.package_id,
                "hud_task": "sre_causal_classification",
                "hud_args": {
                    "prompt": private_tasks[0].prompt,
                    "expected_causal_class": private_tasks[0].expected_causal_class,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
