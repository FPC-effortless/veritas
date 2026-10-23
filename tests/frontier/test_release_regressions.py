from __future__ import annotations

from investigation_world.frontier.calibration import non_saturation_gate
from investigation_world.frontier.diversity import compute_task_diversity
from investigation_world.frontier.models import (
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    GateStatus,
    PairedCapabilityComparison,
)
from investigation_world.frontier.qualification import (
    build_frontier_qualification_report,
    scientific_qualification_summary,
    task_diversity_gate,
)


def _observation(*, tier: str, score: float, model: str, successes: int) -> FrontierCalibrationObservation:
    return FrontierCalibrationObservation(
        benchmark_name="SRE",
        benchmark_version="sre-v4",
        candidate_id="candidate",
        panel_id="panel",
        model_identity=model,
        model_snapshot=f"{model}-snapshot",
        harness_identity="direct",
        tier=tier,
        score=score,
        successes=successes,
        sample_size=30,
    )


def test_non_saturation_requires_actual_intermediate_strong_performance() -> None:
    gate = non_saturation_gate(
        [
            _observation(tier="strong", score=0.05, model="strong-a", successes=2),
            _observation(tier="frontier", score=0.95, model="strong-b", successes=29),
        ],
        FrontierQualificationPolicy(),
    )

    assert gate.status is GateStatus.FAIL
    assert gate.observed["classification"] == "no_intermediate_strong_performance"


def test_task_diversity_is_unknown_when_required_structural_dimensions_are_missing() -> None:
    tasks = [
        {
            "task_id": f"task-{index}",
            "split": "train" if index < 8 else "private_test",
            "source_family": f"source-{index % 6}",
            "prompt": f"Distinct text-only task {index} with source {index % 6}",
        }
        for index in range(16)
    ]
    diversity = compute_task_diversity(tasks)
    gate = task_diversity_gate(diversity, FrontierQualificationPolicy())

    assert gate.status is GateStatus.UNKNOWN
    assert "missing_dimensions" in gate.observed
    assert "workflow_topology" in gate.observed["missing_dimensions"]
    assert "tool_action_sequence" in gate.observed["missing_dimensions"]


def test_benchmark_candidate_without_explicit_gate_evidence_is_not_scientific_pass() -> None:
    observed, passed, detail = scientific_qualification_summary(
        {"status": "benchmark_candidate", "candidate_id": "candidate"}
    )

    assert observed is True
    assert passed is None
    assert "not recognizable" in detail or "missing" in detail.lower()


def test_report_builder_consumes_paired_capability_evidence_directly() -> None:
    weak = _observation(tier="weak", score=10 / 30, model="weak", successes=10)
    strong = _observation(tier="strong", score=22 / 30, model="strong", successes=22)
    paired = PairedCapabilityComparison(
        benchmark_name="SRE",
        benchmark_version="sre-v4",
        candidate_id="candidate",
        panel_id="panel",
        weak_observation_id=weak.observation_id,
        strong_observation_id=strong.observation_id,
        both_correct=8,
        weak_only_correct=2,
        strong_only_correct=14,
        both_wrong=6,
    )

    report = build_frontier_qualification_report(
        scientific_qualification={"releaseable": True},
        observations=[weak, strong],
        paired_comparisons=[paired],
    )
    separation = next(gate for gate in report.gates if gate.name == "capability_separation")

    assert separation.status is GateStatus.PASS
    assert separation.observed["method"] == "paired-difference-normal-v1"
    assert paired.comparison_id in separation.evidence_ids
