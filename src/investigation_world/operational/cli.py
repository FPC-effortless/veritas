from __future__ import annotations

import json
from pathlib import Path

import typer

from investigation_world.foundry.models import DistributionSplit
from investigation_world.operational.deep_distribution import (
    OperationalDistributionConfig,
    compile_operational_distribution,
)
from investigation_world.operational.models import WorldDomain
from investigation_world.operational.native_runtime import NativeOperationalRuntime
from investigation_world.operational.native_validation import validate_native_artifact_distribution
from investigation_world.veritas import Veritas

app = typer.Typer(
    help="Veritas unified operational-world capability foundry",
    no_args_is_help=True,
)


@app.command("capabilities")
def capabilities_cmd() -> None:
    """List the first-class capabilities that make up the Veritas product."""
    veritas = Veritas()
    typer.echo(
        json.dumps(
            {
                "product": veritas.info.name,
                "default_operational_distribution_cases": veritas.info.default_operational_distribution_cases,
                "capabilities": [
                    {
                        "capability_id": capability.capability_id,
                        "category": capability.category,
                        "maturity": capability.maturity,
                        "module": capability.module,
                        "description": capability.description,
                    }
                    for capability in veritas.capabilities()
                ],
            },
            indent=2,
        )
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
    """Build one reference episode for each operational domain."""
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


@app.command("build-distribution")
def build_distribution_cmd(
    seed: int = 42,
    train_per_domain: int = 512,
    iid_per_domain: int = 128,
    ood_per_domain: int = 128,
    adversarial_per_domain: int = 128,
    output: Path = Path("veritas_operational_distribution_public.json"),
    oracle_output: Path = Path("veritas_operational_distribution_private.json"),
) -> None:
    """Build the production-scale train/IID/OOD/adversarial operational distribution."""
    config = OperationalDistributionConfig(
        seed=seed,
        train_per_domain=train_per_domain,
        iid_per_domain=iid_per_domain,
        ood_per_domain=ood_per_domain,
        adversarial_per_domain=adversarial_per_domain,
    )
    validation = Veritas(seed=seed).write_distribution(
        output=output,
        oracle_output=oracle_output,
        config=config,
    )
    typer.echo(
        json.dumps(
            {
                "valid": validation["valid"],
                "total_cases": validation["manifest"]["total_cases"],
                "split_counts": validation["manifest"]["split_counts"],
                "domain_counts": validation["manifest"]["domain_counts"],
                "public_hash": validation["manifest"]["public_hash"],
                "public_output": str(output),
                "private_oracle_output": str(oracle_output),
            },
            indent=2,
        )
    )


@app.command("validate-production-scale")
def validate_production_scale_cmd(
    seed: int = 42,
    train_per_domain: int = 512,
    iid_per_domain: int = 128,
    ood_per_domain: int = 128,
    adversarial_per_domain: int = 128,
) -> None:
    """Compile and validate the production-scale native-ready operational distribution."""
    config = OperationalDistributionConfig(
        seed=seed,
        train_per_domain=train_per_domain,
        iid_per_domain=iid_per_domain,
        ood_per_domain=ood_per_domain,
        adversarial_per_domain=adversarial_per_domain,
    )
    veritas = Veritas(seed=seed)
    cases = veritas.build_distribution(config)
    validation = veritas.validate_distribution(cases, config=config)
    typer.echo(json.dumps(validation, indent=2, default=str))
    if not validation["valid"]:
        raise typer.Exit(1)


@app.command("materialize-native")
def materialize_native_cmd(
    domain: WorldDomain,
    seed: int = 42,
    split: DistributionSplit = DistributionSplit.TRAIN,
    case_index: int = 0,
    output_dir: Path = Path("veritas_native_artifact"),
) -> None:
    """Materialize one generated case as a real native domain artifact.

    This emits only the agent-visible artifact and descriptor. Evaluator oracle
    state remains outside the materialized artifact boundary.
    """
    if case_index < 0:
        raise typer.BadParameter("case-index must be non-negative")
    count = case_index + 1
    config = OperationalDistributionConfig(
        seed=seed,
        train_per_domain=count if split == DistributionSplit.TRAIN else 1,
        iid_per_domain=count if split == DistributionSplit.IID_TEST else 1,
        ood_per_domain=count if split == DistributionSplit.OOD else 1,
        adversarial_per_domain=count if split == DistributionSplit.ADVERSARIAL else 1,
    )
    cases = compile_operational_distribution(config)
    candidates = [
        case
        for case in cases
        if case.episode.task.domain == domain and case.split == split
    ]
    if case_index >= len(candidates):
        raise typer.BadParameter("case-index exceeds generated split size")
    episode = candidates[case_index].episode
    runtime = NativeOperationalRuntime(episode, artifact_root=output_dir)
    artifact_path = runtime.materialize_artifact()
    typer.echo(
        json.dumps(
            {
                "domain": domain.value,
                "split": split.value,
                "task_id": episode.task.task_id,
                "artifact": runtime.artifact_descriptor(),
                "artifact_path": str(artifact_path),
            },
            indent=2,
            default=str,
        )
    )


@app.command("validate-native-fidelity")
def validate_native_fidelity_cmd(
    seed: int = 42,
    cases_per_split: int = 8,
) -> None:
    """Evaluator-only native artifact release gate across all domain × split cells."""
    if cases_per_split < 1:
        raise typer.BadParameter("cases-per-split must be at least one")
    config = OperationalDistributionConfig(
        seed=seed,
        train_per_domain=cases_per_split,
        iid_per_domain=cases_per_split,
        ood_per_domain=cases_per_split,
        adversarial_per_domain=cases_per_split,
    )
    cases = compile_operational_distribution(config)
    report = validate_native_artifact_distribution(cases, seed=seed)
    typer.echo(report.model_dump_json(indent=2))
    if not report.valid:
        raise typer.Exit(1)


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
        "entities": [
            entity.model_dump(mode="json") for entity in company.substrate.entities()
        ],
        "relations": [
            relation.model_dump(mode="json") for relation in company.substrate.relations()
        ],
        "worlds": [episode.public_payload() for episode in company.episodes],
        "event_history": [
            event.model_dump(mode="json") for event in company.substrate.history()
        ],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    snapshot = company.snapshot()
    typer.echo(
        json.dumps(
            {
                "organization_id": organization_id,
                "worlds": len(company.episodes),
                "events": company.substrate.sequence,
                "entities": snapshot.entity_count,
                "relations": snapshot.relation_count,
                "output": str(output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    app()