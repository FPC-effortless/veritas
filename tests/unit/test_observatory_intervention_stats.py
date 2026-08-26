from __future__ import annotations

import pytest

from investigation_world.foundry.models import MutationKind
from investigation_world.observatory.intervention_stats import (
    InterventionEffectSample,
    aggregate_intervention_effects,
    compare_model_intervention_effects,
    intervention_family_key,
)
from investigation_world.observatory.interventions import (
    InterventionEffectReport,
    InterventionMutation,
    InterventionSpec,
)
from investigation_world.observatory.models import DimensionDelta, ModelSpec, ScenarioRef


def _spec(scenario_id: str, scenario_seed: int, mutation_seed: int) -> InterventionSpec:
    return InterventionSpec(
        name="distractor-pressure",
        scenario=ScenarioRef(
            scenario_id=scenario_id,
            task_id=f"TASK-{scenario_id}",
            seed=scenario_seed,
        ),
        mutations=[
            InterventionMutation(
                kind=MutationKind.INJECT_DISTRACTOR,
                seed=mutation_seed,
                parameters={"note": "irrelevant record"},
            )
        ],
    )


def _delta(value: float) -> DimensionDelta:
    return DimensionDelta(
        baseline=1.0,
        current=1.0 + value,
        delta=value,
        relative_delta=value,
    )


def _effect(spec: InterventionSpec, suffix: str, value: float) -> InterventionEffectReport:
    return InterventionEffectReport(
        intervention_id=spec.intervention_id,
        baseline_run_id=f"BASE-{suffix}",
        intervention_run_id=f"TREAT-{suffix}",
        reward=_delta(value),
        cost=_delta(0.0),
        steps=_delta(1.0),
        dimensions={"evidence_support": _delta(value)},
        degraded_dimensions=["evidence_support"] if value < 0 else [],
        improved_dimensions=["evidence_support"] if value > 0 else [],
    )


def _samples(model_id: str, values: list[float]) -> list[InterventionEffectSample]:
    model = ModelSpec(provider="test", model_id=model_id, snapshot="v1")
    result: list[InterventionEffectSample] = []
    for index, value in enumerate(values):
        spec = _spec(f"EP-{index}", 100 + index, 900 + index)
        result.append(
            InterventionEffectSample(
                model=model,
                intervention=spec,
                effect=_effect(spec, f"{model_id}-{index}", value),
            )
        )
    return result


def test_intervention_family_ignores_scenario_and_rng_seeds():
    first = _spec("EP-A", 1, 10)
    second = _spec("EP-B", 2, 20)

    assert intervention_family_key(first) == intervention_family_key(second)


def test_paired_intervention_effects_aggregate_across_scenario_seeds():
    aggregate = aggregate_intervention_effects(_samples("model-a", [-0.2, -0.4]))

    assert aggregate.reward.n == 2
    assert aggregate.reward.mean == pytest.approx(-0.3)
    assert aggregate.dimensions["evidence_support"].mean == pytest.approx(-0.3)
    assert aggregate.steps.mean == pytest.approx(1.0)
    assert aggregate.degraded_dimensions == ["evidence_support"]


def test_model_interaction_is_difference_of_mean_paired_effects():
    first = aggregate_intervention_effects(_samples("model-a", [-0.2, -0.4]))
    second = aggregate_intervention_effects(_samples("model-b", [-0.1, -0.1]))

    interaction = compare_model_intervention_effects(first, second)

    assert interaction.reward.first_effect == pytest.approx(-0.3)
    assert interaction.reward.second_effect == pytest.approx(-0.1)
    assert interaction.reward.difference == pytest.approx(0.2)
    assert interaction.dimensions["evidence_support"].difference == pytest.approx(0.2)
    assert "not longitudinal model drift" in interaction.interpretation


def test_intervention_aggregation_rejects_duplicate_scenario_seed_pair():
    model = ModelSpec(provider="test", model_id="model-a", snapshot="v1")
    first = _spec("EP-A", 1, 10)
    second = _spec("EP-A", 1, 20)
    samples = [
        InterventionEffectSample(
            model=model,
            intervention=first,
            effect=_effect(first, "one", -0.1),
        ),
        InterventionEffectSample(
            model=model,
            intervention=second,
            effect=_effect(second, "two", -0.2),
        ),
    ]

    with pytest.raises(ValueError, match="duplicate scenario/seed"):
        aggregate_intervention_effects(samples)
