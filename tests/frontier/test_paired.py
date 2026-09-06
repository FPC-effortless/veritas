from investigation_world.frontier.calibration import capability_separation_gate
from investigation_world.frontier.models import (
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    GateStatus,
    PairedCapabilityComparison,
)


def _obs(*, tier, score, model, successes):
    return FrontierCalibrationObservation(
        benchmark_name="SRE",
        benchmark_version="sre-v4",
        candidate_id="cand",
        panel_id="panel",
        tier=tier,
        score=score,
        successes=successes,
        sample_size=30,
        model_identity=model,
        model_snapshot=model + "-snapshot",
        harness_identity="direct",
    )


def test_paired_30_case_panel_can_support_separation_without_fake_resampling():
    weak = _obs(tier="weak", score=10/30, model="weak", successes=10)
    strong = _obs(tier="strong", score=22/30, model="strong", successes=22)
    pair = PairedCapabilityComparison(
        benchmark_name="SRE",
        benchmark_version="sre-v4",
        candidate_id="cand",
        panel_id="panel",
        weak_observation_id=weak.observation_id,
        strong_observation_id=strong.observation_id,
        both_correct=8,
        weak_only_correct=2,
        strong_only_correct=14,
        both_wrong=6,
    )
    gate = capability_separation_gate([weak, strong], FrontierQualificationPolicy(), [pair])
    assert gate.status is GateStatus.PASS
    assert gate.observed["method"] == "paired-difference-normal-v1"
    assert gate.observed["paired_case_count"] == 30


def test_paired_comparison_rejects_fake_sample_inflation_mismatch():
    weak = _obs(tier="weak", score=10/30, model="weak", successes=10)
    strong = _obs(tier="strong", score=22/30, model="strong", successes=22)
    pair = PairedCapabilityComparison(
        weak_observation_id=weak.observation_id,
        strong_observation_id=strong.observation_id,
        both_correct=80,
        weak_only_correct=20,
        strong_only_correct=140,
        both_wrong=60,
    )
    gate = capability_separation_gate([weak, strong], FrontierQualificationPolicy(), [pair])
    assert gate.observed["method"] == "independent-interval-gap-v1"
    assert gate.observed["weak_score"] == 10/30
    assert gate.observed["strong_score"] == 22/30
