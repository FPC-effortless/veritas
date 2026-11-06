from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from investigation_world.foundry.models import MutationKind, stable_hash
from investigation_world.observatory.cadence import (
    CadencePolicy,
    CadenceRunResult,
    CadenceStore,
    CadencedObservationRunner,
)
from investigation_world.observatory.capability_graph import (
    companyworld_investigation_capability_graph,
)
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
from investigation_world.observatory.interventions import (
    InterventionEffectReport,
    InterventionMaterialization,
    InterventionSpec,
    compare_intervention_runs,
    materialize_companyworld_intervention,
)
from investigation_world.observatory.matrix import experiment_from_matrix
from investigation_world.observatory.models import (
    CellMatrixSpec,
    ExecutionSpec,
    HarnessSpec,
    ModelSpec,
    ScenarioPool,
    ScenarioRef,
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


class CompanyWorldInterventionRunReport(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    report_id: str
    intervention: InterventionSpec
    materialization: InterventionMaterialization
    baseline_cycle_id: str
    intervention_cycle_id: str
    effect: InterventionEffectReport
    created_at: datetime


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


def _run_repository_observation(
    config: CompanyWorldLiveRunConfig,
    repository: CompanyWorldBundleRepository,
    *,
    scenarios: list[ScenarioRef] | None = None,
    experiment_label: str = "CompanyWorld Observatory",
    hypothesis: str = "Measure longitudinal investigation capability on frozen CompanyWorld cells.",
    experiment_metadata: dict[str, Any] | None = None,
) -> ObservationCycleReport:
    provider = _provider(config)
    harness = CompanyWorldJSONAgentHarness(
        CompanyWorldAgentHarnessConfig(max_steps=config.max_agent_steps)
    )
    runtime_factory = CompanyWorldObservatoryRuntimeFactory(repository)

    selected = scenarios
    if selected is None:
        selected = repository.scenario_refs(
            pool=config.pool,
            split_name=config.split_name,
            limit=config.scenario_limit,
        )
    if not selected:
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
        scenarios=selected,
        models=[model],
        harnesses=[HarnessSpec(harness_id=harness.harness_id, version=harness.version)],
        verifiers=[VerifierSpec(verifier_id="companyworld", version="1")],
        executions=[execution],
        time_snapshots=[config.time_snapshot],
    )
    metadata = {
        "world_version": repository.bundle_version,
        "provider": provider.provider_id,
        "model_id": config.model_id,
        "model_snapshot": config.model_snapshot,
    }
    if experiment_metadata:
        metadata.update(experiment_metadata)
    experiment, cells = experiment_from_matrix(
        f"{experiment_label} {config.model_id} {config.time_snapshot}",
        matrix,
        hypothesis=hypothesis,
        metadata=metadata,
    )

    registry = ExecutionRegistry()
    registry.providers.register(provider)
    registry.harnesses.register(harness)
    registry.runtimes.register(runtime_factory)
    store = ObservatoryStore(config.store_root)
    engine = ObservatoryExecutionEngine(registry, store=store)
    scheduler = LocalObservatoryScheduler(engine, store=store)
    cycle_runner = ObservationCycleRunner(
        scheduler,
        store,
        capability_graph=companyworld_investigation_capability_graph(),
    )
    policy = SchedulerPolicy(
        max_workers=config.max_workers,
        max_attempts=config.max_attempts,
        pools={item.pool for item in selected},
    )
    return cycle_runner.run(experiment, cells, policy=policy)


def run_companyworld_observation(
    config: CompanyWorldLiveRunConfig,
) -> ObservationCycleReport:
    repository = CompanyWorldBundleRepository.from_files(
        config.public_bundle,
        config.oracle_bundle,
    )
    return _run_repository_observation(config, repository)


def _cadence_experiment_identity(
    config: CompanyWorldLiveRunConfig,
    repository: CompanyWorldBundleRepository,
) -> str:
    payload = config.model_dump(mode="json")
    for key in (
        "time_snapshot",
        "model_snapshot",
        "public_bundle",
        "oracle_bundle",
        "store_root",
    ):
        payload.pop(key, None)
    payload["bundle_version"] = repository.bundle_version
    return f"companyworld:{stable_hash(payload)[:24]}"


def run_companyworld_cadence(
    config: CompanyWorldLiveRunConfig,
    *,
    interval_hours: int = 168,
    cadence_root: str | Path | None = None,
    now: datetime | None = None,
    force: bool = False,
) -> CadenceRunResult:
    """Run a CompanyWorld anchor cycle only when its persisted cadence is due."""
    if interval_hours < 1:
        raise ValueError("interval_hours must be at least 1")
    repository = CompanyWorldBundleRepository.from_files(
        config.public_bundle,
        config.oracle_bundle,
    )
    root = Path(cadence_root) if cadence_root is not None else config.store_root / "cadence"
    policy = CadencePolicy(
        name=_cadence_experiment_identity(config, repository),
        interval_seconds=interval_hours * 3600,
    )
    cadence_store = CadenceStore(root)

    def execute(snapshot: str) -> ObservationCycleReport:
        return _run_repository_observation(
            config.model_copy(update={"time_snapshot": snapshot}),
            repository,
        )

    return CadencedObservationRunner(policy, cadence_store, execute).run_if_due(
        now=now,
        force=force,
    )


def run_companyworld_intervention(
    config: CompanyWorldLiveRunConfig,
    spec: InterventionSpec,
    *,
    persist_report: bool = True,
) -> CompanyWorldInterventionRunReport:
    """Execute a controlled baseline/intervention A/B comparison with frozen agent components."""
    if config.world_cost_budget is not None and any(
        mutation.kind == MutationKind.TIGHTEN_BUDGET for mutation in spec.mutations
    ):
        raise ValueError(
            "explicit world_cost_budget would mask a TIGHTEN_BUDGET intervention; "
            "remove the override for this experiment"
        )
    source = CompanyWorldBundleRepository.from_files(config.public_bundle, config.oracle_bundle)
    variant, materialization = materialize_companyworld_intervention(source, spec)
    scenario = spec.scenario.model_copy(update={"pool": ScenarioPool.ANCHOR})

    baseline_cycle = _run_repository_observation(
        config,
        source,
        scenarios=[scenario],
        experiment_label="CompanyWorld intervention baseline",
        hypothesis="Establish the baseline response for a controlled intervention experiment.",
        experiment_metadata={"intervention_id": spec.intervention_id, "arm": "baseline"},
    )
    intervention_cycle = _run_repository_observation(
        config,
        variant,
        scenarios=[scenario],
        experiment_label="CompanyWorld intervention treatment",
        hypothesis="Measure sensitivity to a controlled truth-preserving world intervention.",
        experiment_metadata={"intervention_id": spec.intervention_id, "arm": "intervention"},
    )
    if not baseline_cycle.run_ids or not intervention_cycle.run_ids:
        raise RuntimeError("intervention experiment did not produce both baseline and intervention runs")

    store = ObservatoryStore(config.store_root)
    runs = {run.run_id: run for run in store.load()}
    baseline = runs[baseline_cycle.run_ids[0]]
    intervention = runs[intervention_cycle.run_ids[0]]
    effect = compare_intervention_runs(spec, baseline, intervention)
    created_at = datetime.now(timezone.utc)
    report_id = f"IREPORT-{stable_hash([spec.intervention_id, baseline.run_id, intervention.run_id])[:20].upper()}"
    report = CompanyWorldInterventionRunReport(
        report_id=report_id,
        intervention=spec,
        materialization=materialization,
        baseline_cycle_id=baseline_cycle.cycle_id,
        intervention_cycle_id=intervention_cycle.cycle_id,
        effect=effect,
        created_at=created_at,
    )
    if persist_report:
        root = config.store_root / "interventions"
        root.mkdir(parents=True, exist_ok=True)
        target = root / f"{report_id}.json"
        target.write_text(
            json.dumps(report.model_dump(mode="json"), indent=2, default=str),
            encoding="utf-8",
        )
    return report
