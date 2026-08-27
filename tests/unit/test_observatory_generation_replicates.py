from pathlib import Path

import pytest

from investigation_world.observatory.generation_replicates import (
    GenerationReplicatePlan,
    _seeded_config,
    summarize_generation_replicates,
)
from investigation_world.observatory.live import CompanyWorldLiveRunConfig
from investigation_world.observatory.models import (
    BehavioralFingerprint,
    CapabilityProfile,
    CapabilityRun,
    HarnessSpec,
    LongitudinalCell,
    ModelSpec,
    RunProvenance,
    ScenarioRef,
    VerifierSpec,
    WorldRef,
)


def _run(generation_seed: int, scenario_id: str, scenario_seed: int, reward: float) -> CapabilityRun:
    cell = LongitudinalCell(
        world=WorldRef(world_id="companyworld", version="cw-v1"),
        scenario=ScenarioRef(
            scenario_id=scenario_id,
            task_id=f"TASK-{scenario_id}",
            seed=scenario_seed,
        ),
        model=ModelSpec(
            provider="compatible",
            model_id="agent",
            snapshot="snapshot-1",
            config={"provider_parameters": {"seed": generation_seed}},
        ),
        harness=HarnessSpec(harness_id="h", version="1"),
        verifier=VerifierSpec(verifier_id="v", version="1"),
        time_snapshot="2026-08-26T00:00:00+00:00",
    )
    return CapabilityRun(
        cell=cell,
        provenance=RunProvenance(
            trace_id=f"TRACE-{generation_seed}-{scenario_id}",
            environment_version="cw-v1",
            task_id=f"TASK-{scenario_id}",
            taskset_version="ts-v1",
            runtime_version="runtime-v1",
            harness_version="1",
        ),
        capability=CapabilityProfile(dimensions={"overall_reward": reward}),
        behavior=BehavioralFingerprint(),
        total_reward=reward,
    )


def _config(provider: str = "compatible", **updates) -> CompanyWorldLiveRunConfig:
    payload = dict(
        public_bundle=Path("public.json"),
        oracle_bundle=Path("oracle.json"),
        provider=provider,
        provider_id="compatible" if provider == "compatible" else None,
        model_id="agent",
        base_url="http://localhost:8000/v1" if provider == "compatible" else None,
    )
    payload.update(updates)
    return CompanyWorldLiveRunConfig(**payload)


def test_generation_replicates_require_unique_rng_seeds():
    with pytest.raises(ValueError, match="unique"):
        GenerationReplicatePlan(seeds=[7, 7])


def test_seeded_config_transports_seed_without_changing_other_parameters():
    plan = GenerationReplicatePlan(seeds=[7, 17])
    config = _config(provider_parameters={"temperature": 0.7})

    seeded = _seeded_config(config, plan, 17)

    assert seeded.provider_parameters == {"temperature": 0.7, "seed": 17}
    assert config.provider_parameters == {"temperature": 0.7}


def test_openai_responses_is_rejected_when_seed_contract_is_unavailable():
    plan = GenerationReplicatePlan(seeds=[7, 17])
    config = _config(provider="openai", base_url=None, provider_id=None)

    with pytest.raises(ValueError, match="does not expose a stable generation-seed contract"):
        _seeded_config(config, plan, 7)


def test_generation_replicate_report_requires_identical_scenario_panel():
    plan = GenerationReplicatePlan(seeds=[7, 17])
    runs = {
        7: [_run(7, "EP-1", 1, 0.2), _run(7, "EP-2", 2, 0.8)],
        17: [_run(17, "EP-1", 1, 0.4), _run(17, "EP-2", 2, 0.6)],
    }

    report = summarize_generation_replicates(runs, plan=plan)

    assert report.scenario_count == 2
    assert report.mean_reward_by_generation_seed == pytest.approx({7: 0.5, 17: 0.5})
    assert report.scenarios[0].rewards_by_generation_seed.keys() == {7, 17}


def test_generation_replicates_reject_panel_dropout():
    plan = GenerationReplicatePlan(seeds=[7, 17])
    runs = {
        7: [_run(7, "EP-1", 1, 0.2), _run(7, "EP-2", 2, 0.8)],
        17: [_run(17, "EP-1", 1, 0.4)],
    }

    with pytest.raises(ValueError, match="identical scenario/task/seed panels"):
        summarize_generation_replicates(runs, plan=plan)
