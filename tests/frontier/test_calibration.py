from investigation_world.frontier.calibration import (
    capability_separation_gate,
    failure_mode_breadth_gate,
    harness_sensitivity_gate,
    non_saturation_gate,
)
from investigation_world.frontier.models import (
    FrontierCalibrationObservation,
    FrontierQualificationPolicy,
    GateStatus,
)


def _obs(*, tier: str, score: float, model: str, harness: str = "h1", **kwargs):
    return FrontierCalibrationObservation(
        tier=tier,
        score=score,
        model_identity=model,
        harness_identity=harness,
        **kwargs,
    )


def test_model_saturation_is_detected():
    gate = non_saturation_gate(
        [
            _obs(tier="strong", score=0.96, model="s1"),
            _obs(tier="frontier", score=0.98, model="s2"),
        ],
        FrontierQualificationPolicy(),
    )
    assert gate.status is GateStatus.FAIL
    assert gate.observed["classification"] == "strong_models_saturated"


def test_model_floor_behavior_is_detected():
    gate = non_saturation_gate(
        [
            _obs(tier="strong", score=0.02, model="s1"),
            _obs(tier="frontier", score=0.08, model="s2"),
        ],
        FrontierQualificationPolicy(),
    )
    assert gate.status is GateStatus.FAIL
    assert gate.observed["classification"] == "strong_models_at_floor"


def test_absent_strong_model_evidence_is_unknown():
    gate = non_saturation_gate(
        [_obs(tier="weak", score=0.25, model="tiny")], FrontierQualificationPolicy()
    )
    assert gate.status is GateStatus.UNKNOWN


def test_meaningful_weak_strong_separation_can_pass_with_uncertainty():
    observations = [
        _obs(tier="weak", score=0.20, model="weak", sample_size=100, successes=20),
        _obs(tier="strong", score=0.70, model="strong", sample_size=100, successes=70),
    ]
    gate = capability_separation_gate(observations, FrontierQualificationPolicy())
    assert gate.status is GateStatus.PASS
    assert gate.observed["effect_size_score_gap"] > 0.49
    assert gate.observed["confidence_adjusted_gap"] > 0


def test_point_estimates_alone_do_not_pass_capability_separation():
    gate = capability_separation_gate(
        [
            _obs(tier="weak", score=0.2, model="weak"),
            _obs(tier="strong", score=0.8, model="strong"),
        ],
        FrontierQualificationPolicy(),
    )
    assert gate.status is GateStatus.UNKNOWN


def test_harness_sensitivity_requires_comparable_pair_and_can_pass():
    policy = FrontierQualificationPolicy()
    single = harness_sensitivity_gate(
        [_obs(tier="strong", score=0.5, model="m", harness="h1")], policy
    )
    assert single.status is GateStatus.UNKNOWN
    pair = [
        _obs(tier="strong", score=0.42, model="m", harness="h1", seed=7),
        _obs(tier="strong", score=0.62, model="m", harness="h2", seed=7),
    ]
    assert harness_sensitivity_gate(pair, policy).status is GateStatus.PASS


def test_parser_or_infrastructure_dominance_fails_failure_breadth():
    observation = _obs(
        tier="strong",
        score=0.4,
        model="m",
        failure_mode_counts={"parser": 90, "reasoning": 5, "tool_selection": 5},
    )
    gate = failure_mode_breadth_gate([observation], FrontierQualificationPolicy())
    assert gate.status is GateStatus.FAIL
