from __future__ import annotations

from statistics import mean, stdev
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from investigation_world.foundry.models import stable_hash
from investigation_world.observatory.live import CompanyWorldLiveRunConfig, run_companyworld_observation
from investigation_world.observatory.models import CapabilityRun
from investigation_world.observatory.store import ObservatoryStore


class GenerationReplicatePlan(BaseModel):
    """Nested model-generation RNG replicates over one frozen scenario panel."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    seeds: list[int] = Field(min_length=2)
    seed_parameter: str = "seed"

    @model_validator(mode="after")
    def validate_unique_seeds(self) -> "GenerationReplicatePlan":
        if len(set(self.seeds)) != len(self.seeds):
            raise ValueError("generation replicate seeds must be unique")
        if not self.seed_parameter.strip():
            raise ValueError("seed_parameter must be non-empty")
        return self

    @property
    def plan_id(self) -> str:
        return f"GENPLAN-{stable_hash(self.model_dump(mode='json'))[:20].upper()}"


class GenerationScenarioStatistic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    scenario_id: str
    task_id: str | None = None
    scenario_seed: int
    rewards_by_generation_seed: dict[int, float]
    mean_reward: float
    stddev_reward: float
    minimum_reward: float
    maximum_reward: float


class GenerationReplicateReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str
    plan_id: str
    panel_id: str
    model_id: str
    model_snapshot: str
    generation_seeds: list[int]
    scenario_count: int = Field(ge=1)
    mean_reward_by_generation_seed: dict[int, float]
    between_seed_mean_stddev: float
    scenarios: list[GenerationScenarioStatistic]


def _scenario_key(run: CapabilityRun) -> tuple[str, str | None, int]:
    scenario = run.cell.scenario
    return (scenario.scenario_id, scenario.task_id, scenario.seed)


def _seeded_config(
    config: CompanyWorldLiveRunConfig,
    plan: GenerationReplicatePlan,
    seed: int,
) -> CompanyWorldLiveRunConfig:
    provider = config.provider.casefold()
    if provider == "openai":
        raise ValueError(
            "OpenAI Responses does not expose a stable generation-seed contract here; "
            "use deterministic decoding or an adapter with an explicit seed contract"
        )
    if provider in {"local", "subprocess"} and not config.local_json_stdin:
        raise ValueError(
            "subprocess generation replicates require local_json_stdin=true so the seed is "
            "transported to the model process"
        )
    parameters = dict(config.provider_parameters)
    existing = parameters.get(plan.seed_parameter)
    if existing is not None and int(existing) != seed:
        raise ValueError("provider_parameters already contain a conflicting generation seed")
    parameters[plan.seed_parameter] = seed
    return config.model_copy(update={"provider_parameters": parameters})


def summarize_generation_replicates(
    runs_by_seed: dict[int, Iterable[CapabilityRun]],
    *,
    plan: GenerationReplicatePlan,
) -> GenerationReplicateReport:
    if set(runs_by_seed) != set(plan.seeds):
        raise ValueError("replicate results must cover exactly the generation seeds in the plan")

    materialized = {seed: list(runs_by_seed[seed]) for seed in plan.seeds}
    if any(not runs for runs in materialized.values()):
        raise ValueError("every generation seed must produce at least one run")

    panel_by_seed = {
        seed: {_scenario_key(run) for run in runs}
        for seed, runs in materialized.items()
    }
    first_panel = panel_by_seed[plan.seeds[0]]
    if any(panel != first_panel for panel in panel_by_seed.values()):
        raise ValueError("generation replicates require identical scenario/task/seed panels")

    model_identity = {
        (run.cell.model.provider, run.cell.model.model_id, run.cell.model.snapshot)
        for runs in materialized.values()
        for run in runs
    }
    if len(model_identity) != 1:
        raise ValueError("generation replicates require one model provider/id/snapshot")
    _, model_id, model_snapshot = next(iter(model_identity))

    reward_lookup: dict[int, dict[tuple[str, str | None, int], float]] = {}
    for seed, runs in materialized.items():
        by_scenario: dict[tuple[str, str | None, int], float] = {}
        for run in runs:
            key = _scenario_key(run)
            if key in by_scenario:
                raise ValueError("duplicate run for a scenario inside one generation replicate")
            by_scenario[key] = run.total_reward
        reward_lookup[seed] = by_scenario

    scenario_stats: list[GenerationScenarioStatistic] = []
    for scenario_id, task_id, scenario_seed in sorted(first_panel):
        rewards = {
            seed: reward_lookup[seed][(scenario_id, task_id, scenario_seed)]
            for seed in plan.seeds
        }
        values = list(rewards.values())
        scenario_stats.append(
            GenerationScenarioStatistic(
                scenario_id=scenario_id,
                task_id=task_id,
                scenario_seed=scenario_seed,
                rewards_by_generation_seed=rewards,
                mean_reward=mean(values),
                stddev_reward=stdev(values) if len(values) > 1 else 0.0,
                minimum_reward=min(values),
                maximum_reward=max(values),
            )
        )

    seed_means = {
        seed: mean(reward_lookup[seed].values())
        for seed in plan.seeds
    }
    seed_mean_values = list(seed_means.values())
    panel_payload = sorted(
        [scenario_id, task_id, scenario_seed]
        for scenario_id, task_id, scenario_seed in first_panel
    )
    panel_id = f"GENPANEL-{stable_hash(panel_payload)[:20].upper()}"
    report_id = f"GENREP-{stable_hash([plan.plan_id, panel_id, model_id, model_snapshot, seed_means])[:20].upper()}"
    return GenerationReplicateReport(
        report_id=report_id,
        plan_id=plan.plan_id,
        panel_id=panel_id,
        model_id=model_id,
        model_snapshot=model_snapshot,
        generation_seeds=list(plan.seeds),
        scenario_count=len(first_panel),
        mean_reward_by_generation_seed=seed_means,
        between_seed_mean_stddev=(
            stdev(seed_mean_values) if len(seed_mean_values) > 1 else 0.0
        ),
        scenarios=scenario_stats,
    )


def run_companyworld_generation_replicates(
    config: CompanyWorldLiveRunConfig,
    plan: GenerationReplicatePlan,
) -> GenerationReplicateReport:
    """Execute nested generation-RNG replicates on an otherwise frozen CompanyWorld config."""

    cycles = {}
    for seed in plan.seeds:
        seeded = _seeded_config(config, plan, seed)
        cycles[seed] = run_companyworld_observation(seeded)

    store = ObservatoryStore(config.store_root)
    runs = {run.run_id: run for run in store.load()}
    runs_by_seed = {
        seed: [runs[run_id] for run_id in cycles[seed].run_ids if run_id in runs]
        for seed in plan.seeds
    }
    return summarize_generation_replicates(runs_by_seed, plan=plan)
