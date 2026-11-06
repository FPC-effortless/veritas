from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from investigation_world.foundry.models import stable_hash
from investigation_world.qualification import (
    PrivateReleaseManifest,
    QualificationCandidate,
    QualificationReport,
    QualificationSplit,
    SRECausalClass,
    SREQualificationCase,
)


@dataclass(frozen=True)
class SealedSRERelease:
    candidate: QualificationCandidate
    qualification: QualificationReport
    private_release_manifest: PrivateReleaseManifest
    cases: list[SREQualificationCase]


def _panel_id(candidate: QualificationCandidate) -> str:
    private_scenarios = sorted(
        (
            scenario
            for scenario in candidate.scenarios
            if scenario.split == QualificationSplit.PRIVATE_TEST
        ),
        key=lambda scenario: scenario.scenario_id,
    )
    payload = [
        [scenario.scenario_id, scenario.source_group_id, scenario.public_digest]
        for scenario in private_scenarios
    ]
    return f"QPANEL-{stable_hash(payload)[:24].upper()}"


def load_sealed_sre_release(
    qualification_path: Path,
    *,
    expected_candidate_id: str | None = None,
    expected_evidence_manifest_id: str | None = None,
    expected_report_id: str | None = None,
    expected_panel_id: str | None = None,
    expected_private_release_manifest_id: str | None = None,
) -> SealedSRERelease:
    payload = json.loads(qualification_path.read_text(encoding="utf-8"))
    if payload.get("status") != "benchmark_candidate":
        raise RuntimeError(f"sealed SRE release is not qualified: {payload.get('status')!r}")

    candidate = QualificationCandidate.model_validate(payload["candidate"])
    report = QualificationReport.model_validate(payload["qualification"])
    raw_release = payload.get("private_release_manifest")
    if not raw_release:
        raise RuntimeError("sealed SRE release is missing its private release manifest")
    release = PrivateReleaseManifest.model_validate(raw_release)

    failed = [gate.name for gate in report.gates if not gate.passed]
    if not report.releaseable or failed:
        raise RuntimeError(f"sealed SRE qualification has failed gates: {failed}")

    if report.candidate_id != candidate.candidate_id:
        raise RuntimeError("qualification report candidate identity mismatch")
    if report.candidate_version != candidate.version:
        raise RuntimeError("qualification report candidate version mismatch")
    if report.evidence_manifest_id != candidate.evidence_manifest.manifest_id:
        raise RuntimeError("qualification report evidence manifest mismatch")

    computed_panel_id = _panel_id(candidate)
    if report.panel_id != computed_panel_id:
        raise RuntimeError(
            f"qualification panel identity mismatch: report={report.panel_id}, computed={computed_panel_id}"
        )

    if release.candidate_id != candidate.candidate_id:
        raise RuntimeError("private release manifest candidate identity mismatch")
    if release.candidate_version != candidate.version:
        raise RuntimeError("private release manifest candidate version mismatch")
    if release.qualification_report_id != report.report_id:
        raise RuntimeError("private release manifest report identity mismatch")
    if release.evidence_manifest_id != candidate.evidence_manifest.manifest_id:
        raise RuntimeError("private release manifest evidence identity mismatch")
    if release.panel_id != report.panel_id:
        raise RuntimeError("private release manifest panel identity mismatch")

    private_ids = sorted(
        scenario.scenario_id
        for scenario in candidate.scenarios
        if scenario.split == QualificationSplit.PRIVATE_TEST
    )
    if sorted(release.private_test_scenario_ids) != private_ids:
        raise RuntimeError("private release manifest does not seal the exact private panel")

    expected = {
        "candidate_id": (expected_candidate_id, candidate.candidate_id),
        "evidence_manifest_id": (expected_evidence_manifest_id, candidate.evidence_manifest.manifest_id),
        "report_id": (expected_report_id, report.report_id),
        "panel_id": (expected_panel_id, report.panel_id),
        "private_release_manifest_id": (
            expected_private_release_manifest_id,
            release.manifest_id,
        ),
    }
    for name, (wanted, actual) in expected.items():
        if wanted and wanted != actual:
            raise RuntimeError(f"{name} mismatch: expected {wanted}, got {actual}")

    cases: list[SREQualificationCase] = []
    for scenario in candidate.scenarios:
        provider = str(scenario.metadata.get("provider", "")).strip()
        causal_value = str(scenario.metadata.get("causal_class", "")).strip()
        if not provider:
            raise RuntimeError(f"scenario {scenario.scenario_id} is missing provider metadata")
        try:
            causal_class = SRECausalClass(causal_value)
        except ValueError as exc:
            raise RuntimeError(
                f"scenario {scenario.scenario_id} has invalid causal class {causal_value!r}"
            ) from exc
        cases.append(
            SREQualificationCase(
                scenario=scenario,
                public_text=scenario.normalized_text,
                causal_class=causal_class,
                provider=provider,
            )
        )

    return SealedSRERelease(
        candidate=candidate,
        qualification=report,
        private_release_manifest=release,
        cases=cases,
    )
