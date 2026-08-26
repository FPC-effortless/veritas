from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.observatory.companyworld import (
    CompanyWorldBundleRepository,
    CompanyWorldObservatoryRuntimeFactory,
)
from investigation_world.observatory.cycles import ObservationCycleReport, ObservationCycleRunner
from investigation_world.observatory.execution import ExecutionRegistry, ObservatoryExecutionEngine
from investigation_world.observatory.harnesses import (
    CompanyWorldAgentHarnessConfig,
    CompanyWorldJSONAgentHarness,
)
from investigation_world.observatory.matrix import experiment_from_matrix
from investigation_world.observatory.models import (
    CellMatrixSpec,
    ExecutionSpec,
    HarnessSpec,
    ModelSpec,
    ScenarioPool,
    VerifierSpec,
    WorldKind,
    WorldRef,
)
from investigation_world.observatory.providers import (
    HuggingFaceInferenceProvider,
    OpenAICompatibleChatProvider,
    OpenAIResponsesProvider,
    SubprocessModelProvider,
)
from investigation_world.observatory.scheduler import LocalObservatoryScheduler, SchedulerPolicy
from investigation_world.observatory.store import ObservatoryStore


def utc_snapshot() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CompanyWorldLiveRunConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    public_bundle: Path
    oracle_bundle: Path
    store_root: Path = Path("observatory_data")
    provider: str = "huggingface"
    provider_id: str | None = None
    model_id: str
    model_snapshot: str = "provider-current"
    time_snapshot: str = Field(default_factory=utc_snapshot)
    endpoint: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    local_command: list[str] = Field(default_factory=list)
    local_json_stdin: bool = False
    split_name: str | None = "public_eval"
    scenario_limit: int | None = 10
    pool: ScenarioPool = ScenarioPool.ANCHOR
    max_workers: int = Field(default=1, ge=1)
    max_attempts: int = Field(default=2, ge=1)
    max_agent_steps: int = Field(default=20, ge=1)
    time_limit_s: float | None = Field(default=None, gt=0.0)
    token_budget: int | None = Field(default=None, ge=1)
    tool_call_budget: int | None = Field(default=None, ge=1)
    provider_cost_budget: float | None = Field(default=None, ge=0.0)
    world_cost_budget: int | None = Field(default=None, ge=1)
    input_cost_per_million: float = Field(default=0.0, ge=0.0)
    output_cost_per_million: float = Field(default=0.0, ge=0.0)
    provider_parameters: dict[str, Any] = Field(default_factory=dict)


def _provider(config: CompanyWorldLiveRunConfig):
    provider = config.provider.casefold()
    if provider == "openai":
        return OpenAIResponsesProvider(
            base_url=config.base_url or "https://api.openai.com/v1",
            api_key_env=config.api_key_env or "OPENAI_API_KEY",
            timeout_s=config.time_limit_s or 120.0,
        )
    if provider == "huggingface":
        return HuggingFaceInferenceProvider(timeout_s=config.time_limit_s or 120.0)
    if provider in {"compatible", "openai-compatible"}:
        if not config.base_url:
            raise ValueError("base_url is required for an OpenAI-compatible provider")
        return OpenAICompatibleChatProvider(
            config.provider_id or "compatible",
            base_url=config.base_url,
            api_key_env=config.api_key_env,
            timeout_s=config.time_limit_s or 120.0,
        )
    if provider in {"local", "subprocess"}:
        if not config.local_command:
            raise ValueError("local_command is required for a subprocess provider")
        return SubprocessModelProvider(
            config.provider_id or "local",
            config.local_command,
            timeout_s=config.time_limit_s or 120.0,
            json_stdin=config.local_json_stdin,
        )
    raise ValueError(f"unsupported live Observatory provider {config.provider!r}")


def run_companyworld_observation(
    config: CompanyWorldLiveRunConfig,
) -> ObservationCycleReport:
    repository = CompanyWorldBundleRepository.from_files(
        config.public_bundle,
        config.oracle_bundle,
    )
    provider = _provider(config)
    harness = CompanyWorldJSONAgentHarness(
        CompanyWorldAgentHarnessConfig(max_steps=config.max_agent_steps)
    )
    runtime_factory = CompanyWorldObservatoryRuntimeFactory(repository)

    scenarios = repository.scenario_refs(
        pool=config.pool,
        split_name=config.split_name,
        limit=config.scenario_limit,
    )
    if not scenarios:
        raise ValueError("live Observatory selection produced zero scenarios")

    model_config: dict[str, Any] = {
        "input_cost_per_million": config.input_cost_per_million,
        "output_cost_per_million": config.output_cost_per_million,
        "provider_parameters": config.provider_parameters,
    }
    execution_parameters: dict[str, Any] = {}
    if config.world_cost_budget is not None:
        execution_parameters["world_cost_budget"] = config.world_cost_budget
    model = ModelSpec(
        provider=provider.provider_id,
        model_id=config.model_id,
        snapshot=config.model_snapshot,
        endpoint=config.endpoint,
        config=model_config,
    )
    execution = ExecutionSpec(
        time_limit_s=config.time_limit_s,
        token_budget=config.token_budget,
        tool_call_budget=config.tool_call_budget,
        cost_budget=config.provider_cost_budget,
        parameters=execution_parameters,
    )
    matrix = CellMatrixSpec(
        worlds=[
            WorldRef(
                world_id=repository.world_id,
                version=repository.bundle_version,
                kind=WorldKind.OPERATIONAL,
            )
        ],
        scenarios=scenarios,
        models=[model],
        harnesses=[HarnessSpec(harness_id=harness.harness_id, version=harness.version)],
        verifiers=[VerifierSpec(verifier_id="companyworld", version="1")],
        executions=[execution],
        time_snapshots=[config.time_snapshot],
    )
    experiment, cells = experiment_from_matrix(
        f"CompanyWorld Observatory {config.model_id} {config.time_snapshot}",
        matrix,
        hypothesis="Measure longitudinal investigation capability on frozen CompanyWorld cells.",
        metadata={
            "world_version": repository.bundle_version,
            "provider": provider.provider_id,
            "model_id": config.model_id,
            "model_snapshot": config.model_snapshot,
        },
    )

    registry = ExecutionRegistry()
    registry.providers.register(provider)
    registry.harnesses.register(harness)
    registry.runtimes.register(runtime_factory)
    store = ObservatoryStore(config.store_root)
    engine = ObservatoryExecutionEngine(registry, store=store)
    scheduler = LocalObservatoryScheduler(engine, store=store)
    cycle_runner = ObservationCycleRunner(scheduler, store)
    policy = SchedulerPolicy(
        max_workers=config.max_workers,
        max_attempts=config.max_attempts,
        pools={config.pool},
    )
    return cycle_runner.run(experiment, cells, policy=policy)
