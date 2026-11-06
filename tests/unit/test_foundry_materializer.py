import pytest

from investigation_world.calibration.fixtures import build_o2c_episode
from investigation_world.companyworld.models import CompanySystem
from investigation_world.foundry import (
    DifficultyVector,
    DistributionSplit,
    FoundryCompanyWorldRuntime,
    FoundryToolFailure,
    SampledTaskParameters,
    materialize_companyworld_task,
)


def _sample(**difficulty_overrides):
    difficulty = DifficultyVector(**difficulty_overrides)
    return SampledTaskParameters(
        sample_id="TDS-MATERIALIZER-001",
        distribution_id="materializer-test",
        split=DistributionSplit.ADVERSARIAL,
        seed=123,
        capability_tags=["discover", "interpret", "verify"],
        task_family="O2C_FULFILLMENT_TIMING",
        domain="operations",
        difficulty=difficulty,
    )


def test_materializer_changes_public_world_without_changing_oracle_truth():
    base = build_o2c_episode(91, delay_days=3)
    expected = [fact.expected_value for fact in base.oracle.facts]
    task = materialize_companyworld_task(
        base,
        _sample(
            entities=4,
            tools=4,
            steps=3,
            distractors=3,
            missing_probability=1.0,
            conflict_probability=1.0,
            dependency_depth=3,
            budget_ratio=0.5,
            stochasticity=0.0,
            adversarial_pressure=0.8,
        ),
    )
    assert [fact.expected_value for fact in task.episode.oracle.facts] == expected
    assert len(task.materialization["distractor_record_ids"]) >= 3
    assert len(task.materialization["competing_record_ids"]) == len(base.oracle.facts)
    assert task.runtime.total_cost == 20
    assert len(task.episode.task.permitted_systems) >= 2
    public_text = str(task.episode.public_payload())
    assert "expected_value" not in public_text
    assert "supporting_record_ids" not in public_text
    assert "foundry_seed" not in public_text
    assert "adversarial_pressure" not in public_text
    assert "conflict_probability" not in public_text
    assert "foundry_split" not in public_text
    assert "foundry_conflicting" not in public_text


def test_materialized_runtime_failure_is_observable_reproducible_and_budgeted():
    base = build_o2c_episode(92, delay_days=2)
    sample = _sample(
        entities=1,
        tools=2,
        steps=2,
        dependency_depth=2,
        budget_ratio=0.75,
        stochasticity=1.0,
    )
    first = materialize_companyworld_task(base, sample)
    second = materialize_companyworld_task(base, sample)
    assert first.model_dump(mode="json") == second.model_dump(mode="json")

    runtime = FoundryCompanyWorldRuntime(first)
    before = runtime.budget_snapshot()["spent"]
    with pytest.raises(FoundryToolFailure) as exc:
        runtime.search_system(CompanySystem.ERP, "SO-CAL")
    after = runtime.budget_snapshot()["spent"]
    assert exc.value.retryable is True
    assert after > before


def test_latent_randomness_is_privileged_but_reproducible():
    base = build_o2c_episode(94, delay_days=4)
    task = materialize_companyworld_task(
        base,
        _sample(conflict_probability=1.0, adversarial_pressure=1.0, stochasticity=0.5),
    )
    public = task.episode.public_payload()
    assert "seed" not in str(public).casefold()
    assert task.sample.seed == 123
    assert task.runtime.failure_seed == 123
    assert task.materialization["latent_difficulty"]["adversarial_pressure"] == 1.0


def test_materializer_preserves_systems_required_by_supporting_evidence():
    base = build_o2c_episode(93, delay_days=1)
    task = materialize_companyworld_task(base, _sample(tools=1))
    support_ids = {
        record_id for fact in task.episode.oracle.facts for record_id in fact.supporting_record_ids
    }
    support_systems = {
        record.system for record in task.episode.records if record.record_id in support_ids
    }
    assert support_systems.issubset(set(task.episode.task.permitted_systems))
