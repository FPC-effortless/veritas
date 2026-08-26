from __future__ import annotations

from math import sqrt
from statistics import mean, stdev
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.aggregation import MetricEstimate, critical_95
from investigation_world.observatory.interventions import InterventionEffectReport, InterventionSpec
from investigation_world.observatory.models import ModelSpec


class InterventionEffectSample(BaseModel):
    """One paired baseline/treatment effect for one scenario seed."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    model: ModelSpec
    intervention: InterventionSpec
    effect: InterventionEffectReport
    sample_id: str = ""

    @model_validator(mode="after")
    def validate_sample_id(self) -> "InterventionEffectSample":
        if self.effect.intervention_id != self.intervention.intervention_id:
            raise ValueError("effect/intervention identity mismatch")
        expected = f"ISAMPLE-{stable_hash([self.model.model_dump(mode='json'), self.intervention.intervention_id, self.effect.baseline_run_id, self.effect.intervention_run_id])[:20].upper()}"
        if self.sample_id and self.sample_id != expected:
            raise ValueError("sample_id does not match intervention sample contents")
        object.__setattr__(self, "sample_id", expected)
        return self


def intervention_family_payload(spec: InterventionSpec) -> dict:
    """Intervention identity across scenario/mutation seeds.

    Scenario identity and all RNG seeds are intentionally excluded. Mutation kinds, ordered
    parameters, truth-preservation semantics, and the human-readable family name remain.
    """
    return {
        "name": spec.name,
        "truth_preserving": spec.truth_preserving,
        "mutations": [
            {
                "kind": mutation.kind.value,
                "parameters": mutation.parameters,
            }
            for mutation in spec.mutations
        ],
    }


def intervention_family_key(spec: InterventionSpec) -> str:
    return f"IFAMILY-{stable_hash(intervention_family_payload(spec))[:20].upper()}"


def model_key(model: ModelSpec) -> str:
    return f"IMODEL-{stable_hash(model.model_dump(mode='json'))[:20].upper()}"


def _estimate(values: list[float]) -> MetricEstimate:
    if not values:
        raise ValueError("cannot estimate an empty intervention metric")
    n = len(values)
    center = mean(values)
    deviation = stdev(values) if n > 1 else 0.0
    error = deviation / sqrt(n) if n > 1 else 0.0
    margin = critical_95(n) * error
    return MetricEstimate(
        n=n,
        mean=center,
        stddev=deviation,
        standard_error=error,
        ci95_low=center - margin,
        ci95_high=center + margin,
        minimum=min(values),
        maximum=max(values),
    )


class ScenarioInterventionEffect(BaseModel):
    """Treatment-minus-baseline effect retained at the scenario level for paired interactions."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    scenario_seed: int
    sample_id: str
    reward: float
    cost: float
    steps: float
    dimensions: dict[str, float] = Field(default_factory=dict)


class AggregatedInterventionEffect(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    aggregate_id: str
    family_key: str
    model_key: str
    model: ModelSpec
    sample_ids: list[str]
    scenario_ids: list[str]
    scenario_seeds: list[int]
    reward: MetricEstimate
    cost: MetricEstimate
    steps: MetricEstimate
    dimensions: dict[str, MetricEstimate] = Field(default_factory=dict)
    degraded_dimensions: list[str] = Field(default_factory=list)
    improved_dimensions: list[str] = Field(default_factory=list)
    scenario_pairs: list[tuple[str, int]] = Field(default_factory=list)
    sample_effects: list[ScenarioInterventionEffect] = Field(default_factory=list)
    interpretation: str = (
        "Each observation is a paired treatment-minus-baseline effect for one scenario seed. "
        "The aggregate estimates the mean paired intervention effect across seeds."
    )


def aggregate_intervention_effects(
    samples: Iterable[InterventionEffectSample],
    *,
    tolerance: float = 1e-9,
) -> AggregatedInterventionEffect:
    items = list(samples)
    if not items:
        raise ValueError("cannot aggregate zero intervention samples")
    family = intervention_family_key(items[0].intervention)
    model_identity = model_key(items[0].model)
    for item in items:
        if intervention_family_key(item.intervention) != family:
            raise ValueError("intervention samples do not belong to one intervention family")
        if model_key(item.model) != model_identity:
            raise ValueError("intervention samples do not belong to one ModelSpec")

    sample_ids = [item.sample_id for item in items]
    if len(set(sample_ids)) != len(sample_ids):
        raise ValueError("duplicate intervention samples are not allowed")
    scenario_pairs = [
        (item.intervention.scenario.scenario_id, item.intervention.scenario.seed)
        for item in items
    ]
    if len(set(scenario_pairs)) != len(scenario_pairs):
        raise ValueError("duplicate scenario/seed pairs are not allowed")

    common_dimensions = set(items[0].effect.dimensions)
    for item in items[1:]:
        common_dimensions &= set(item.effect.dimensions)
    dimensions = {
        name: _estimate([item.effect.dimensions[name].delta for item in items])
        for name in sorted(common_dimensions)
    }
    degraded = [name for name, metric in dimensions.items() if metric.mean < -tolerance]
    improved = [name for name, metric in dimensions.items() if metric.mean > tolerance]
    ordered_sample_ids = sorted(sample_ids)
    sample_effects = sorted(
        [
            ScenarioInterventionEffect(
                scenario_id=item.intervention.scenario.scenario_id,
                scenario_seed=item.intervention.scenario.seed,
                sample_id=item.sample_id,
                reward=item.effect.reward.delta,
                cost=item.effect.cost.delta,
                steps=item.effect.steps.delta,
                dimensions={
                    name: item.effect.dimensions[name].delta
                    for name in sorted(common_dimensions)
                },
            )
            for item in items
        ],
        key=lambda effect: (effect.scenario_id, effect.scenario_seed),
    )
    ordered_pairs = [(effect.scenario_id, effect.scenario_seed) for effect in sample_effects]
    aggregate_id = f"IAGG-{stable_hash([family, model_identity, ordered_sample_ids])[:20].upper()}"
    return AggregatedInterventionEffect(
        aggregate_id=aggregate_id,
        family_key=family,
        model_key=model_identity,
        model=items[0].model,
        sample_ids=ordered_sample_ids,
        scenario_ids=sorted(item.intervention.scenario.scenario_id for item in items),
        scenario_seeds=sorted(item.intervention.scenario.seed for item in items),
        reward=_estimate([item.effect.reward.delta for item in items]),
        cost=_estimate([item.effect.cost.delta for item in items]),
        steps=_estimate([item.effect.steps.delta for item in items]),
        dimensions=dimensions,
        degraded_dimensions=degraded,
        improved_dimensions=improved,
        scenario_pairs=ordered_pairs,
        sample_effects=sample_effects,
    )


class InteractionEstimate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    first_effect: float
    second_effect: float
    difference: float
    standard_error: float = Field(ge=0.0)
    ci95_low: float
    ci95_high: float
    n: int = Field(default=0, ge=0)


def _paired_interaction(first: list[float], second: list[float]) -> InteractionEstimate:
    if len(first) != len(second) or not first:
        raise ValueError("model interaction requires non-empty paired scenario effects")
    differences = [second_value - first_value for first_value, second_value in zip(first, second)]
    n = len(differences)
    center = mean(differences)
    deviation = stdev(differences) if n > 1 else 0.0
    error = deviation / sqrt(n) if n > 1 else 0.0
    margin = critical_95(n) * error
    return InteractionEstimate(
        first_effect=mean(first),
        second_effect=mean(second),
        difference=center,
        standard_error=error,
        ci95_low=center - margin,
        ci95_high=center + margin,
        n=n,
    )


class ModelInterventionInteractionReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    interaction_id: str
    family_key: str
    first_aggregate_id: str
    second_aggregate_id: str
    first_model: ModelSpec
    second_model: ModelSpec
    reward: InteractionEstimate
    cost: InteractionEstimate
    steps: InteractionEstimate
    dimensions: dict[str, InteractionEstimate] = Field(default_factory=dict)
    scenario_pairs: list[tuple[str, int]] = Field(default_factory=list)
    interpretation: str = (
        "Interaction values are paired scenario-level difference-in-differences: for each identical "
        "scenario/seed, second-model treatment-minus-baseline minus first-model treatment-minus-"
        "baseline. They measure differential sensitivity to the same intervention family; they are "
        "not longitudinal model drift. CI95 is computed from the paired interaction distribution."
    )


def compare_model_intervention_effects(
    first: AggregatedInterventionEffect,
    second: AggregatedInterventionEffect,
) -> ModelInterventionInteractionReport:
    if first.family_key != second.family_key:
        raise ValueError("model interaction requires the same intervention family")
    if first.model_key == second.model_key:
        raise ValueError("model interaction requires two distinct ModelSpecs")
    if not first.sample_effects or not second.sample_effects:
        raise ValueError("model interaction requires retained scenario-level intervention effects")
    if first.scenario_pairs != second.scenario_pairs:
        raise ValueError("model interaction requires identical scenario/seed panels")

    first_by_pair = {
        (effect.scenario_id, effect.scenario_seed): effect for effect in first.sample_effects
    }
    second_by_pair = {
        (effect.scenario_id, effect.scenario_seed): effect for effect in second.sample_effects
    }
    pairs = list(first.scenario_pairs)
    common_dimensions = sorted(
        set.intersection(
            *(set(first_by_pair[pair].dimensions) & set(second_by_pair[pair].dimensions) for pair in pairs)
        )
    ) if pairs else []
    interaction_id = f"IINT-{stable_hash([first.aggregate_id, second.aggregate_id, pairs])[:20].upper()}"
    return ModelInterventionInteractionReport(
        interaction_id=interaction_id,
        family_key=first.family_key,
        first_aggregate_id=first.aggregate_id,
        second_aggregate_id=second.aggregate_id,
        first_model=first.model,
        second_model=second.model,
        reward=_paired_interaction(
            [first_by_pair[pair].reward for pair in pairs],
            [second_by_pair[pair].reward for pair in pairs],
        ),
        cost=_paired_interaction(
            [first_by_pair[pair].cost for pair in pairs],
            [second_by_pair[pair].cost for pair in pairs],
        ),
        steps=_paired_interaction(
            [first_by_pair[pair].steps for pair in pairs],
            [second_by_pair[pair].steps for pair in pairs],
        ),
        dimensions={
            name: _paired_interaction(
                [first_by_pair[pair].dimensions[name] for pair in pairs],
                [second_by_pair[pair].dimensions[name] for pair in pairs],
            )
            for name in common_dimensions
        },
        scenario_pairs=pairs,
    )
