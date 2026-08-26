from __future__ import annotations

import json
from pathlib import Path

import typer

from investigation_world.operational.models import WorldDomain
from investigation_world.veritas import Veritas

app = typer.Typer(
    help="Veritas unified operational-world capability foundry",
    no_args_is_help=True,
)


@app.command("domains")
def domains_cmd() -> None:
    """List first-class operational world domains."""
    typer.echo(
        json.dumps(
            {"domains": [domain.value for domain in WorldDomain]},
            indent=2,
        )
    )


@app.command("build-world")
def build_world_cmd(
    domain: WorldDomain,
    seed: int = 42,
    output: Path = Path("operational_world.json"),
    oracle_output: Path | None = None,
) -> None:
    """Build one public operational world and optionally its private oracle."""
    episode = Veritas(seed=seed).build_world(domain)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(episode.public_payload(), indent=2, default=str),
        encoding="utf-8",
    )
    result = {
        "domain": domain.value,
        "world_id": episode.world_id,
        "task_id": episode.task.task_id,
        "public_output": str(output),
    }
    if oracle_output is not None:
        oracle_output.parent.mkdir(parents=True, exist_ok=True)
        oracle_output.write_text(
            episode.oracle.model_dump_json(indent=2),
            encoding="utf-8",
        )
        result["private_oracle_output"] = str(oracle_output)
    typer.echo(json.dumps(result, indent=2))


@app.command("build-suite")
def build_suite_cmd(
    seed: int = 42,
    output: Path = Path("veritas_operational_suite.json"),
    oracle_output: Path | None = None,
) -> None:
    """Build all five public worlds with optional evaluator-only oracle bundle."""
    veritas = Veritas(seed=seed)
    episodes = veritas.build_suite()
    payload = {
        "manifest": veritas.manifest().model_dump(mode="json"),
        "episodes": [episode.public_payload() for episode in episodes],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    result = {
        "worlds": len(episodes),
        "domains": [episode.task.domain.value for episode in episodes],
        "public_output": str(output),
    }
    if oracle_output is not None:
        oracle_output.parent.mkdir(parents=True, exist_ok=True)
        oracle_output.write_text(
            json.dumps(
                {
                    "oracles": [
                        episode.oracle.model_dump(mode="json") for episode in episodes
                    ]
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )
        result["private_oracle_output"] = str(oracle_output)
    typer.echo(json.dumps(result, indent=2))


@app.command("build-company")
def build_company_cmd(
    organization_id: str = "ORG-VERITAS-001",
    seed: int = 42,
    output: Path = Path("veritas_company.json"),
) -> None:
    """Build one persistent synthetic company spanning all five domains."""
    company = Veritas(seed=seed).build_company(organization_id=organization_id)
    payload = {
        "organization_id": organization_id,
        "snapshot": company.snapshot().model_dump(mode="json"),
        "worlds": [episode.public_payload() for episode in company.episodes],
        "event_history": [
            event.model_dump(mode="json") for event in company.substrate.history()
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    typer.echo(
        json.dumps(
            {
                "organization_id": organization_id,
                "worlds": len(company.episodes),
                "events": company.substrate.sequence,
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()
