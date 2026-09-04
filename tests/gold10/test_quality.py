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
    assert coverage["task_structure"]["case_specific_hypothesis_targets_required"] is True
    assert coverage["task_structure"]["calibration_uncertainty_target_required"] is True


def test_exploit_policy_falsifies_known_shortcuts() -> None:
    report = build_pilot_gate_report()
    exploit = report["exploit_shortcut_policy"]
    assert exploit["all_probes_pass"] is True
    assert all(item["passed"] for item in exploit["probes"].values())
    assert (
        exploit["probes"]["arbitrary_hypothesis_without_canonical_target"]["reward"]
        == 0.0
    )
    assert (
        exploit["probes"]["nonsense_hypotheses_with_valid_factual_target"]["reward"]
        == 0.0
    )
    assert exploit["probes"]["canonical_target_statement_mismatch"]["reward"] == 0.0
    assert exploit["probes"]["hindsight_evidence"]["reward"] == 0.0
    assert exploit["probes"]["collapsed_calibration_uncertainty"]["reward"] == 0.0
    assert (
        exploit["probes"]["structured_meaningless_calibration_with_valid_target"][
            "reward"
        ]
        == 0.0
    )


def test_reference_solvability_is_target_bound_not_capability_evidence() -> None:
    report = build_pilot_gate_report()
    reference = report["reference_scripted_solvability"]
    assert reference["status"] == "pass"
    assert all(
        item["reward"] == 0.75 and item["hard_failures"] == []
        for item in reference["reference_scores"].values()
    )
    assert "target-bound scripted protocol solvability" in reference["interpretation"]
    assert "not model capability" in reference["interpretation"]


def test_vq_uses_canonical_multidimensional_scorecard_without_scalar_promotion() -> None:
    report = build_pilot_gate_report()
    vq = report["vq_scorecard"]
    scorecard = vq["scorecard"]
    assert scorecard["scorecard_version"] == "veritas.environment-quality-scorecard.v1"
    assert len(scorecard["dimensions"]) == 18
    assert vq["complete"] is False
    assert vq["failed_dimensions"] == []
    assert len(vq["unknown_dimensions"]) == 18
    assert vq["evidence_outcome_ceiling"] == "OBSERVED"
    assert "overall_mean" not in vq
    observed = {
        item["dimension"]
        for item in scorecard["dimensions"]
        if item["observed_records"] > 0
    }
    assert observed == {
        "provenance_completeness",
        "reproducibility",
        "reset_determinism",
        "reward_hack_resistance",
        "structural_diversity",
        "task_ambiguity",
    }
    assert all(
        authorized is False
        for authorized in vq["qualification_authority"].values()
    )
