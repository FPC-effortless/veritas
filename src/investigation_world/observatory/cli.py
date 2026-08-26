from __future__ import annotations

import json
import shlex
from pathlib import Path

import typer

from investigation_world.observatory.live import (
    CompanyWorldLiveRunConfig,
    run_companyworld_observation,
)
from investigation_world.observatory.models import ScenarioPool

app = typer.Typer(help="Run the Veritas Continuous Agent Capability Observatory")


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
    provider_cost_budget: float | None = typer.Option(
        None,
        "--provider-cost-budget",
        min=0.0,
    ),
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
    try:
        provider_parameters = json.loads(provider_parameters_json)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter("provider parameters must be valid JSON") from exc
    if not isinstance(provider_parameters, dict):
        raise typer.BadParameter("provider parameters must decode to a JSON object")
    payload = {
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
        "provider_parameters": provider_parameters,
    }
    if time_snapshot is not None:
        payload["time_snapshot"] = time_snapshot
    config = CompanyWorldLiveRunConfig.model_validate(payload)
    report = run_companyworld_observation(config)
    typer.echo(
        json.dumps(
            {
                "cycle_id": report.cycle_id,
                "experiment_id": report.experiment_id,
                "planned": report.scheduler.planned,
                "succeeded": report.scheduler.succeeded,
                "failed": report.scheduler.failed,
                "skipped": report.scheduler.skipped,
                "aggregates": len(report.aggregates),
                "drift_reports": len(report.drift),
                "regressions": sorted(
                    {
                        name
                        for drift in report.drift
                        for name in drift.regressions
                    }
                ),
                "report_root": str(config.store_root / "cycles"),
            },
            indent=2,
        )
    )
    raise typer.Exit(1 if report.scheduler.failed else 0)


if __name__ == "__main__":
    app()
