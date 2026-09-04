from investigation_world.gold10 import build_pilot_gate_report


def test_pilot_gate_report_is_deterministic_and_complete() -> None:
    first = build_pilot_gate_report()
    second = build_pilot_gate_report()
    assert first == second
    assert len(first["report_sha256"]) == 64
    assert len(first["taskset_rebuild_sha256"]) == 64
    assert first["pilot_level_gates"] == {
        "deterministic_rebuild_identity": "pass",
        "duplicate_near_duplicate_analysis": "complete",
        "contamination_assessment": "complete_high_risk",
        "coverage_report": "complete",
        "reference_scripted_solvability": "pass",
        "exploit_shortcut_policy": "pass",
        "vq_multidimensional_scorecard": "complete",
    }


def test_contamination_and_coverage_are_reported_without_overclaim() -> None:
    report = build_pilot_gate_report()
    contamination = report["contamination_assessment"]
    coverage = report["coverage_report"]
    assert contamination["overall_assessment"] == "high_public_historical_nonsealed"
    assert contamination["contamination_clean_claim_authorized"] is False
    assert coverage["case_count"] == 10
    assert coverage["split_counts"] == {"dev": 2, "eval": 2, "train": 6}
    assert coverage["source_diversity_count"] == 1
    assert coverage["source_counts"]["uscsb"] > 0
    assert coverage["modality_diversity_count"] >= 2
    assert coverage["calibration_cases"] == ["2012-03-I-CA"]


def test_exploit_policy_falsifies_known_shortcuts() -> None:
    report = build_pilot_gate_report()
    exploit = report["exploit_shortcut_policy"]
    assert exploit["all_probes_pass"] is True
    assert all(item["passed"] for item in exploit["probes"].values())
    assert (
        exploit["probes"]["arbitrary_hypothesis_without_canonical_target"]["reward"]
        == 0.0
    )
    assert exploit["probes"]["canonical_target_statement_mismatch"]["reward"] == 0.0
    assert exploit["probes"]["hindsight_evidence"]["reward"] == 0.0


def test_vq_scorecard_preserves_pilot_candidate_ceiling() -> None:
    report = build_pilot_gate_report()
    scorecard = report["vq_scorecard"]
    assert scorecard["status"] == "pilot_candidate_only"
    assert 0.0 <= scorecard["overall_mean"] <= 1.0
    assert scorecard["dimensions"]["verifier_robustness"] <= 0.75
    assert scorecard["dimensions"]["contamination_resilience"] < 1.0
    assert all(
        authorized is False
        for authorized in scorecard["qualification_authority"].values()
    )
