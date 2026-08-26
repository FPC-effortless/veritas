from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

import typer

from investigation_world.observatory.interventions import InterventionSpec
from investigation_world.observatory.live import (
    CompanyWorldLiveRunConfig,
    run_companyworld_cadence,
    run_companyworld_intervention,
    run_companyworld_observation,
)
from investigation_world.observatory.models import ScenarioPool

app = typer.Typer(help="Run the Veritas Continuous Agent Capability Observatory")


def _provider_parameters(value: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("provider parameters must be valid JSON") from exc
    if not isinstance(decoded, dict):
        raise typer.BadParameter("provider parameters must decode to a JSON object")
    return decoded


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"{label} must contain valid JSON") from exc
    if not isinstance(decoded, dict):
        raise typer.BadParameter(f"{label} must contain a JSON object")
    return decoded


def _live_config(
    *,
    public_bundle: Path,
    oracle_bundle: Path,
    model: str,
    provider: str,
    model_snapshot: str,
    store_root: Path,
    split_name: str | None,
    scenario_limit: int | None,
    pool: ScenarioPool,
    max_workers: int,
    max_attempts: int,
    max_agent_steps: int,
    time_limit_s: float | None,
    token_budget: int | None,
    tool_call_budget: int | None,
    provider_cost_budget: float | None,
    world_cost_budget: int | None,
    endpoint: str | None,
    base_url: str | None,
    api_key_env: str | None,
    provider_id: str | None,
    local_command: str | None,
    local_json_stdin: bool,
    input_cost_per_million: float,
    output_cost_per_million: float,
    provider_parameters_json: str,
    time_snapshot: str | None = None,
) -> CompanyWorldLiveRunConfig:
    payload: dict[str, Any] = {
        "public_bundle": public_bundle,
        "oracle_bundle": oracle_bundle,
        "store_root": store_root,
        "provider": provider,
        "provider_id": provider_id,
        "model_id": model,
        "model_snapshot": model_snapshot,
        "endpoint": endpoint,
        "base_url": base_url,
        "api_key_env": api_key_env,
        "local_command": shlex.split(local_command) if local_command else [],
        "local_json_stdin": local_json_stdin,
        "split_name": split_name,
        "scenario_limit": scenario_limit,
        "pool": pool,
        "max_workers": max_workers,
        "max_attempts": max_attempts,
        "max_agent_steps": max_agent_steps,
        "time_limit_s": time_limit_s,
        "token_budget": token_budget,
        "tool_call_budget": tool_call_budget,
        "provider_cost_budget": provider_cost_budget,
        "world_cost_budget": world_cost_budget,
        "input_cost_per_million": input_cost_per_million,
        "output_cost_per_million": output_cost_per_million,
        "provider_parameters": _provider_parameters(provider_parameters_json),
    }
    if time_snapshot is not None:
        payload["time_snapshot"] = time_snapshot
    return CompanyWorldLiveRunConfig.model_validate(payload)


def _report_payload(report, store_root: Path) -> dict[str, Any]:
    return {
        "cycle_id": report.cycle_id,
        "experiment_id": report.experiment_id,
        "planned": report.scheduler.planned,
        "succeeded": report.scheduler.succeeded,
        "failed": report.scheduler.failed,
        "skipped": report.scheduler.skipped,
        "aggregates": len(report.aggregates),
        "drift_reports": len(report.drift),
        "attribution_reports": len(report.attribution),
        "regressions": sorted(
            {name for drift in report.drift for name in drift.regressions}
        ),
        "candidate_roots": sorted(
            {
                capability
                for attribution in report.attribution
                for capability in attribution.candidate_roots
            }
        ),
        "report_root": str(store_root / "cycles"),
    }


@app.command("companyworld")
def run_companyworld(
    public_bundle: Path = typer.Option(..., exists=True, readable=True),
    oracle_bundle: Path = typer.Option(..., exists=True, readable=True),
    model: str = typer.Option(..., "--model"),
    provider: str = typer.Option("huggingface", "--provider"),
    model_snapshot: str = typer.Option("provider-current", "--model-snapshot"),
    time_snapshot: str | None = typer.Option(None, "--time-snapshot"),
    store_root: Path = typer.Option(Path("observatory_data"), "--store-root"),
    split_name: str | None = typer.Option("public_eval", "--split"),
    scenario_limit: int | None = typer.Option(10, "--limit", min=1),
    pool: ScenarioPool = typer.Option(ScenarioPool.ANCHOR, "--pool"),
    max_workers: int = typer.Option(1, "--max-workers", min=1),
    max_attempts: int = typer.Option(2, "--max-attempts", min=1),
    max_agent_steps: int = typer.Option(20, "--max-agent-steps", min=1),
    time_limit_s: float | None = typer.Option(None, "--time-limit-s", min=0.001),
    token_budget: int | None = typer.Option(None, "--token-budget", min=1),
    tool_call_budget: int | None = typer.Option(None, "--tool-call-budget", min=1),
    provider_cost_budget: float | None = typer.Option(None, "--provider-cost-budget", min=0.0),
    world_cost_budget: int | None = typer.Option(None, "--world-cost-budget", min=1),
    endpoint: str | None = typer.Option(None, "--endpoint"),
    base_url: str | None = typer.Option(None, "--base-url"),
    api_key_env: str | None = typer.Option(None, "--api-key-env"),
    provider_id: str | None = typer.Option(None, "--provider-id"),
    local_command: str | None = typer.Option(None, "--local-command"),
    local_json_stdin: bool = typer.Option(False, "--local-json-stdin"),
    input_cost_per_million: float = typer.Option(0.0, "--input-cost-per-million", min=0.0),
    output_cost_per_million: float = typer.Option(0.0, "--output-cost-per-million", min=0.0),
    provider_parameters_json: str = typer.Option("{}", "--provider-parameters-json"),
):
    """Run one CompanyWorld observation cycle against a hosted or local model."""
    config = _live_config(
        public_bundle=public_bundle,
        oracle_bundle=oracle_bundle,
        model=model,
        provider=provider,
        model_snapshot=model_snapshot,
        time_snapshot=time_snapshot,
        store_root=store_root,
        split_name=split_name,
        scenario_limit=scenario_limit,
        pool=pool,
        max_workers=max_workers,
        max_attempts=max_attempts,
        max_agent_steps=max_agent_steps,
        time_limit_s=time_limit_s,
        token_budget=token_budget,
        tool_call_budget=tool_call_budget,
        provider_cost_budget=provider_cost_budget,
        world_cost_budget=world_cost_budget,
        endpoint=endpoint,
        base_url=base_url,
        api_key_env=api_key_env,
        provider_id=provider_id,
        local_command=local_command,
        local_json_stdin=local_json_stdin,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
        provider_parameters_json=provider_parameters_json,
    )
    report = run_companyworld_observation(config)
    typer.echo(json.dumps(_report_payload(report, config.store_root), indent=2))
    raise typer.Exit(1 if report.scheduler.failed else 0)


@app.command("companyworld-cadence")
def run_companyworld_on_cadence(
    public_bundle: Path = typer.Option(..., exists=True, readable=True),
    oracle_bundle: Path = typer.Option(..., exists=True, readable=True),
    model: str = typer.Option(..., "--model"),
    provider: str = typer.Option("huggingface", "--provider"),
    model_snapshot: str = typer.Option("provider-current", "--model-snapshot"),
    interval_hours: int = typer.Option(168, "--interval-hours", min=1),
    force: bool = typer.Option(False, "--force"),
    store_root: Path = typer.Option(Path("observatory_data"), "--store-root"),
    split_name: str | None = typer.Option("public_eval", "--split"),
    scenario_limit: int | None = typer.Option(10, "--limit", min=1),
    pool: ScenarioPool = typer.Option(ScenarioPool.ANCHOR, "--pool"),
    max_workers: int = typer.Option(1, "--max-workers", min=1),
    max_attempts: int = typer.Option(2, "--max-attempts", min=1),
    max_agent_steps: int = typer.Option(20, "--max-agent-steps", min=1),
    time_limit_s: float | None = typer.Option(None, "--time-limit-s", min=0.001),
    token_budget: int | None = typer.Option(None, "--token-budget", min=1),
    tool_call_budget: int | None = typer.Option(None, "--tool-call-budget", min=1),
    provider_cost_budget: float | None = typer.Option(None, "--provider-cost-budget", min=0.0),
    world_cost_budget: int | None = typer.Option(None, "--world-cost-budget", min=1),
    endpoint: str | None = typer.Option(None, "--endpoint"),
    base_url: str | None = typer.Option(None, "--base-url"),
    api_key_env: str | None = typer.Option(None, "--api-key-env"),
    provider_id: str | None = typer.Option(None, "--provider-id"),
    local_command: str | None = typer.Option(None, "--local-command"),
    local_json_stdin: bool = typer.Option(False, "--local-json-stdin"),
    input_cost_per_million: float = typer.Option(0.0, "--input-cost-per-million", min=0.0),
    output_cost_per_million: float = typer.Option(0.0, "--output-cost-per-million", min=0.0),
    provider_parameters_json: str = typer.Option("{}", "--provider-parameters-json"),
):
    """Run an anchor observation only when its persisted cadence is due."""
    config = _live_config(
        public_bundle=public_bundle,
        oracle_bundle=oracle_bundle,
        model=model,
        provider=provider,
        model_snapshot=model_snapshot,
        store_root=store_root,
        split_name=split_name,
        scenario_limit=scenario_limit,
        pool=pool,
        max_workers=max_workers,
        max_attempts=max_attempts,
        max_agent_steps=max_agent_steps,
        time_limit_s=time_limit_s,
        token_budget=token_budget,
        tool_call_budget=tool_call_budget,
        provider_cost_budget=provider_cost_budget,
        world_cost_budget=world_cost_budget,
        endpoint=endpoint,
        base_url=base_url,
        api_key_env=api_key_env,
        provider_id=provider_id,
        local_command=local_command,
        local_json_stdin=local_json_stdin,
        input_cost_per_million=input_cost_per_million,
        output_cost_per_million=output_cost_per_million,
        provider_parameters_json=provider_parameters_json,
    )
    result = run_companyworld_cadence(
        config,
        interval_hours=interval_hours,
        force=force,
    )
    if result.cycle is None:
        typer.echo(
            json.dumps(
                {
                    "due": False,
                    "reason": result.decision.reason,
                    "next_due_at": result.decision.next_due_at.isoformat(),
                },
                indent=2,
            )
        )
        return
    payload = _report_payload(result.cycle, config.store_root)
    payload.update({"due": True, "cadence_id": result.decision.cadence_id})
    typer.echo(json.dumps(payload, indent=2))
    raise typer.Exit(1 if result.cycle.scheduler.failed else 0)


@app.command("companyworld-intervention")
def run_companyworld_intervention_command(
    config_json: Path = typer.Option(..., "--config", exists=True, readable=True),
    intervention_json: Path = typer.Option(..., "--intervention", exists=True, readable=True),
):
    """Run a controlled CompanyWorld baseline/intervention A/B experiment from JSON specs."""
    config = CompanyWorldLiveRunConfig.model_validate(
        _read_json_object(config_json, "live config")
    )
    spec = InterventionSpec.model_validate(
        _read_json_object(intervention_json, "intervention spec")
    )
    report = run_companyworld_intervention(config, spec)
    typer.echo(
        json.dumps(
            {
                "report_id": report.report_id,
                "intervention_id": report.intervention.intervention_id,
                "baseline_cycle_id": report.baseline_cycle_id,
                "intervention_cycle_id": report.intervention_cycle_id,
                "source_world_version": report.materialization.source_world_version,
                "intervention_world_version": report.materialization.intervention_world_version,
                "reward_delta": report.effect.reward.delta,
                "cost_delta": report.effect.cost.delta,
                "step_delta": report.effect.steps.delta,
                "degraded_dimensions": report.effect.degraded_dimensions,
                "improved_dimensions": report.effect.improved_dimensions,
                "report": str(config.store_root / "interventions" / f"{report.report_id}.json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
