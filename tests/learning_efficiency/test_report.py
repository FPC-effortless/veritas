"""CONSTRUCTED arithmetic and adversarial records, never model-efficiency evidence."""

import runpy
from pathlib import Path

import pytest

from investigation_world.learning_efficiency import (
    EfficiencyStudy,
    LearningEfficiencyReport,
    ResourceObservation,
    ResourcePlan,
    assess_efficiency,
    resource_components,
    validate_efficiency,
)
from investigation_world.training_qualification import TrainingPolicy, assess_training

FIXTURE = runpy.run_path(
    str(Path(__file__).parents[1] / "training_qualification" / "test_training_qualification.py")
)
ref = FIXTURE["ref"]


def rebuild(record, **changes):
    payload = record.model_dump(mode="python")
    payload.update(changes)
    payload["record_id"] = ""
    return type(record).model_validate(payload)


def study(**kwargs):
    return EfficiencyStudy(
        experiment_id="CONSTRUCTED-efficiency-study",
        training=assess_training(
            FIXTURE["evidence"](**kwargs),
            policy=TrainingPolicy(minimum_replicates=2, minimum_population=4),
        ),
        evidence_references=(ref("CONSTRUCTED-study"),),
    )


def plan(**kwargs):
    return ResourcePlan(
        metric="gpu_hours",
        unit="GPU-hour",
        unit_definition=ref("CONSTRUCTED-GPU-profile"),
        stages=("training",),
        **kwargs,
    )


def measurements(s, p, amounts=(2.0, 6.0)):
    return tuple(
        ResourceObservation(
            study_id=s.record_id,
            plan_id=p.record_id,
            measurement=ref(f"CONSTRUCTED-meter-{index}"),
            component_ids=(component,),
            value=value,
            provenance="CONSTRUCTED",
            unavailable_reason="meter unavailable" if value is None else None,
        )
        for index, (component, value) in enumerate(
            zip(resource_components(s, p), amounts, strict=True)
        )
    )


def test_complete_descriptive_ratio_is_not_verified_efficiency():
    s, p = study(), plan()
    obs = measurements(s, p)
    report = assess_efficiency(s, plans=(p,), observations=obs)
    denominator = report.denominators[0]
    assert denominator.value == 8
    assert denominator.recorded_metric_delta == pytest.approx(0.4)
    assert denominator.ratio == pytest.approx(0.05)
    assert denominator.aggregation == "mean_recorded_delta_per_total_resource"
    assert denominator.excluded_stages == ("generation", "selection", "derivation", "evaluation")
    assert denominator.coverage == "COMPLETE_DECLARED_SCOPE"
    assert report.verified_capability_efficiency == "UNKNOWN"
    assert report.capability_gain is None
    assert report.uncertainty.expected_seeds == (1, 2)
    assert report.uncertainty.complete
    assert report.uncertainty.confidence_interval is None
    assert report.counts.training_examples == 4
    assert report.counts.raw_candidates is None
    assert report.resource_availability["monetary_cost"] == "UNKNOWN"
    assert validate_efficiency(report, study=s, plans=(p,), observations=obs) == report


@pytest.mark.parametrize("after, expected", [(0.6, 0.05), (0.2, 0), (0.0, -0.025)])
def test_positive_zero_and_negative_deltas_are_retained(after, expected):
    s, p = study(heldout_after=(after,) * 4), plan()
    report = assess_efficiency(s, plans=(p,), observations=measurements(s, p))
    assert report.denominators[0].ratio == pytest.approx(expected)
    assert report.verified_capability_efficiency == "UNKNOWN"


@pytest.mark.parametrize(
    "amounts, reason",
    [((0.0, 0.0), "zero_denominator"), ((2.0, None), "incomplete_resource_coverage")],
)
def test_zero_and_unknown_are_not_infinity_or_fabricated_zero(amounts, reason):
    s, p = study(), plan()
    row = assess_efficiency(s, plans=(p,), observations=measurements(s, p, amounts)).denominators[0]
    assert row.ratio is None and row.reason == reason
    assert row.value == (0 if amounts == (0.0, 0.0) else None)


def test_missing_replicate_does_not_shrink_cohort_but_seed_arithmetic_survives():
    s, p = study(seeds=(1,)), plan()
    obs = measurements(s, p, (2.0,))
    report = assess_efficiency(s, plans=(p,), observations=obs)
    assert report.uncertainty.missing_seeds == (2,)
    assert report.uncertainty.mean is None
    assert report.denominators[0].ratio is None
    per_seed = plan(seed=1)
    result = assess_efficiency(s, plans=(per_seed,), observations=measurements(s, per_seed, (2.0,)))
    assert result.denominators[0].ratio == pytest.approx(0.2)
    assert not result.uncertainty.complete


def test_unscored_panel_member_does_not_vanish():
    s, p = study(heldout_after=(None, 0.6, 0.6, 0.6)), plan()
    result = assess_efficiency(s, plans=(p,), observations=measurements(s, p))
    assert result.denominators[0].recorded_metric_delta is None
    assert result.denominators[0].ratio is None
    assert result.uncertainty.unknown_seeds == (1, 2)


def test_shared_measurement_alias_is_counted_once_and_conflicts_reject():
    s, p = study(), plan()
    obs = measurements(s, p)
    report = assess_efficiency(s, plans=(p,), observations=(*obs, obs[0]))
    assert report.denominators[0].value == 8
    assert report.denominators[0].duplicate_observations == 1
    with pytest.raises(ValueError, match="measurement"):
        assess_efficiency(s, plans=(p,), observations=(*obs, rebuild(obs[0], value=3.0)))
    with pytest.raises(ValueError, match="overlap"):
        assess_efficiency(
            s, plans=(p,), observations=(*obs, rebuild(obs[0], measurement=ref("other")))
        )


def test_one_shared_charge_covering_multiple_components_is_not_multiplied():
    s, p = study(), plan()
    obs = ResourceObservation(
        study_id=s.record_id,
        plan_id=p.record_id,
        measurement=ref("shared-invoice"),
        component_ids=resource_components(s, p),
        value=7.0,
        provenance="CONSTRUCTED",
    )
    assert assess_efficiency(s, plans=(p,), observations=(obs,)).denominators[0].value == 7


def test_full_pipeline_cannot_hide_missing_generation_or_selection():
    s = study()
    p = ResourcePlan(
        metric="monetary_cost",
        unit="USD",
        unit_definition=ref("invoice-currency-basis"),
        stages=("generation", "selection", "derivation", "training", "evaluation"),
    )
    obs = measurements(s, p, tuple(1.0 for _ in resource_components(s, p)))
    row = assess_efficiency(s, plans=(p,), observations=obs).denominators[0]
    assert row.value is None and row.ratio is None
    assert set(row.unavailable_stages) >= {"generation", "selection", "derivation"}


@pytest.mark.parametrize("changes", [{"unit": "USD"}, {"unit": "native-budget-units"}])
def test_units_cannot_convert_native_budgets_or_money_into_compute(changes):
    with pytest.raises(ValueError, match="unit"):
        rebuild(plan(), **changes)


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True])
def test_invalid_resource_numbers_reject(value):
    s, p = study(), plan()
    with pytest.raises(ValueError):
        rebuild(measurements(s, p)[0], value=value)


def test_experiment_and_scope_substitution_reject():
    s, p = study(), plan()
    obs = measurements(s, p)
    with pytest.raises(ValueError, match="study"):
        assess_efficiency(rebuild(s, experiment_id="other"), plans=(p,), observations=obs)
    with pytest.raises(ValueError, match="component"):
        assess_efficiency(s, plans=(p,), observations=(rebuild(obs[0], component_ids=("other",)),))


def test_forged_summary_or_provider_result_cannot_be_rehashed_into_validity():
    s, p = study(), plan()
    obs = measurements(s, p)
    result = assess_efficiency(s, plans=(p,), observations=obs)
    data = result.model_dump(mode="python")
    data["record_id"] = ""
    data["denominators"][0]["record_id"] = ""
    data["denominators"][0]["ratio"] = 123
    with pytest.raises(ValueError, match="recomputed"):
        LearningEfficiencyReport.model_validate(data)
    fake = s.training.model_copy(update={"record_id": "", "mean_recorded_heldout_delta": 1.0})
    with pytest.raises(ValueError):
        assess_efficiency(s.model_copy(update={"record_id": "", "training": fake}))


def test_material_changes_change_identity_and_expected_validation_rejects_rewrites():
    s, p = study(), plan()
    obs = measurements(s, p)
    old = assess_efficiency(s, plans=(p,), observations=obs)
    newer = assess_efficiency(s, plans=(p,), observations=(rebuild(obs[0], value=3.0), obs[1]))
    assert old.record_id != newer.record_id
    with pytest.raises(ValueError, match="expected"):
        validate_efficiency(newer, study=s, plans=(p,), observations=obs)
    assert rebuild(s, evidence_references=(ref("different-evidence"),)).record_id != s.record_id


def test_private_identity_and_free_text_never_enter_public_projection():
    s = rebuild(study(), limitations=("PRIVATE-SENTINEL",))
    result = assess_efficiency(s)
    expected = {"status": "UNKNOWN", "reason": "evidence_not_visible"}
    assert result.public_payload() == result.buyer_safe_payload() == expected
    assert s.record_id not in str(result.public_payload())
    with pytest.raises(ValueError):
        rebuild(result, visibility="public")


def test_derived_example_normalizer_is_explicit_dataset_scope_not_processed_tokens():
    result = assess_efficiency(study())
    by_metric = {row.metric: row for row in result.denominators}
    examples = by_metric["training_examples"]
    assert examples.value == 4
    assert examples.ratio == pytest.approx(0.1)
    assert examples.unit == "example"
    assert examples.provenances == ("DERIVED_RECORD_COUNT",)
    assert by_metric["raw_candidates"].value is None
    assert by_metric["native_runtime_budget"].ratio is None
    assert result.counts.training_tokens is None


def test_reusing_one_charge_across_different_seed_scopes_rejects():
    s = study()
    one, two = plan(seed=1), plan(seed=2)
    a = measurements(s, one, (3.0,))[0]
    b = measurements(s, two, (3.0,))[0]  # Same meter identity, different covered run.
    with pytest.raises(ValueError, match="measurement"):
        assess_efficiency(s, plans=(one, two), observations=(a, b))


def test_same_measurement_identity_cannot_rebind_its_bytes():
    s, p = study(), plan()
    a, b = measurements(s, p)
    different = ref("different measurement bytes").model_copy(
        update={"reference_id": a.measurement.reference_id}
    )
    with pytest.raises(ValueError, match="measurement"):
        assess_efficiency(s, plans=(p,), observations=(a, rebuild(b, measurement=different)))


def test_fractional_tokens_are_not_valid_observed_counts():
    s = study()
    p = ResourcePlan(
        metric="training_tokens",
        unit="token",
        unit_definition=ref("tokenizer"),
        stages=("training",),
    )
    with pytest.raises(ValueError, match="integer"):
        assess_efficiency(s, plans=(p,), observations=measurements(s, p, (1.5, 2.0)))


def test_no_unaccounted_provider_inputs_are_silently_dropped():
    with pytest.raises(ValueError, match="selection"):
        assess_efficiency(study(), gap_sources=((object(), object()),))
    with pytest.raises(ValueError, match="derivation"):
        assess_efficiency(study(), derivation_receipts=(object(),))


@pytest.mark.parametrize("unit", ["EUR", "native-budget-units", "dollar", "token"])
def test_equivalent_compute_has_no_caller_invented_dimension_escape(unit):
    with pytest.raises(ValueError, match="unit"):
        ResourcePlan(
            metric="equivalent_compute",
            unit=unit,
            unit_definition=ref("invented"),
            stages=("training",),
        )


def test_known_numerical_policy_failure_does_not_suppress_negative_resource_result():
    result = assess_efficiency(study(heldout_after=(0.0,) * 4))
    assert result.study.training.status == "FAIL"
    assert next(d for d in result.denominators if d.metric == "training_examples").ratio < 0
    assert result.verified_capability_efficiency == "UNKNOWN"


def test_generator_tokens_cannot_be_relabeled_training_tokens():
    with pytest.raises(ValueError, match="training_tokens"):
        ResourcePlan(
            metric="training_tokens",
            unit="token",
            unit_definition=ref("tokenizer"),
            stages=("generation",),
        )
