from __future__ import annotations

from types import SimpleNamespace

from investigation_world.portability.evidence import build_sre_portable_qualification_evidence


def _release():
    scenarios = [
        SimpleNamespace(
            scenario_id="secret-train-id",
            split=SimpleNamespace(value="train"),
            source_group_id="source-a",
        ),
        SimpleNamespace(
            scenario_id="secret-private-id",
            split=SimpleNamespace(value="private_test"),
            source_group_id="source-b",
        ),
    ]
    candidate = SimpleNamespace(
        candidate_id="SRE-CAND-FIXTURE",
        version="sre-v4",
        evidence_manifest=SimpleNamespace(manifest_id="EVID-FIXTURE"),
        scenarios=scenarios,
    )
    qualification = SimpleNamespace(
        report_id="QREPORT-FIXTURE",
        panel_id="QPANEL-FIXTURE",
        gates=[
            SimpleNamespace(name="determinism", passed=True),
            SimpleNamespace(name="private leakage", passed=True),
        ],
        policy_means={"oracle": 1.0, "random": 0.2},
        releaseable=True,
    )
    private_release_manifest = SimpleNamespace(manifest_id="PRIVREL-FIXTURE")
    return SimpleNamespace(
        candidate=candidate,
        qualification=qualification,
        private_release_manifest=private_release_manifest,
    )


def test_qualification_evidence_is_deterministic_and_buyer_safe() -> None:
    first = build_sre_portable_qualification_evidence(_release())
    second = build_sre_portable_qualification_evidence(_release())

    assert first.evidence_id == second.evidence_id
    assert first.scenario_count == 2
    assert first.split_counts == {"private_test": 1, "train": 1}
    assert first.source_group_count == 2
    assert first.gate_count == 2
    assert first.failed_gate_count == 0
    assert first.private_case_details_included is False
    assert first.scenario_ids_included is False
    assert first.hidden_ground_truth_included is False

    rendered = first.model_dump_json()
    assert "secret-train-id" not in rendered
    assert "secret-private-id" not in rendered


def test_evidence_identity_changes_with_release_hash() -> None:
    first = build_sre_portable_qualification_evidence(
        _release(), source_bundle_sha256="a" * 64
    )
    second = build_sre_portable_qualification_evidence(
        _release(), source_bundle_sha256="b" * 64
    )
    assert first.evidence_id != second.evidence_id
