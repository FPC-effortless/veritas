from __future__ import annotations

import json
from pathlib import Path

import typer

from investigation_world.evidence.projector import project
from investigation_world.world.generator import WorldFactory, WorldGenerationConfig, validate_world

app = typer.Typer(help="Synthetic corporate investigation environment")


@app.command()
def generate_world(seed: int = 42, output: Path = Path("world.json")):
    world = WorldFactory.generate(seed, WorldGenerationConfig())
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(world.model_dump_json(indent=2))
    typer.echo(f"generated {world.world_id} -> {output}")


@app.command()
def validate_world_cmd(world: Path):
    from investigation_world.core.models import CanonicalWorld

    errors = validate_world(CanonicalWorld.model_validate_json(world.read_text()))
    typer.echo("valid" if not errors else "\n".join(errors))
    raise typer.Exit(1 if errors else 0)


@app.command()
def render_evidence(
    world: Path,
    output: Path = Path("evidence.json"),
    seed: int = 0,
):
    from investigation_world.core.models import CanonicalWorld

    canonical = CanonicalWorld.model_validate_json(world.read_text())
    projected, _ = project(canonical, seed)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(projected.model_dump_json(indent=2))
    typer.echo(f"rendered {len(projected.documents)} documents")


@app.command()
def generate_tasks(
    world: Path,
    output: Path = Path("tasks.json"),
    oracle_output: Path | None = None,
    count: int = 48,
    seed: int = 0,
):
    """Generate public tasks; optionally write privileged oracles to a separate file."""
    from investigation_world.core.models import CanonicalWorld
    from investigation_world.tasks.spec import generate_task_bundle, split_manifest

    canonical = CanonicalWorld.model_validate_json(world.read_text())
    bundle = generate_task_bundle(canonical, count=count, seed=seed)
    public_tasks = [instance.public for instance in bundle]
    payload = {
        "tasks": [task.model_dump(mode="json") for task in public_tasks],
        "splits": split_manifest(public_tasks),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str))
    if oracle_output is not None:
        oracle_output.parent.mkdir(parents=True, exist_ok=True)
        oracle_output.write_text(
            json.dumps(
                {"oracles": [instance.oracle.model_dump(mode="json") for instance in bundle]},
                indent=2,
                default=str,
            )
        )
    typer.echo(f"generated {count} public tasks")


@app.command()
def build_index(world: Path, database: Path = Path("search.sqlite")):
    from investigation_world.core.models import CanonicalWorld
    from investigation_world.search.index import FrozenSearchIndex

    index = FrozenSearchIndex(str(database))
    index.build(CanonicalWorld.model_validate_json(world.read_text()))
    typer.echo(f"indexed {database}")


@app.command()
def validate_companyworld(dataset: Path):
    """Validate a CompanyWorld dataset before compiling operational episodes."""
    from investigation_world.companyworld import CompanyWorldAdapter

    report = CompanyWorldAdapter(dataset).validate()
    typer.echo(json.dumps(report.model_dump(mode="json"), indent=2, default=str))
    raise typer.Exit(0 if report.valid else 1)


@app.command("compile-companyworld")
def compile_companyworld_cmd(
    dataset: Path,
    output: Path = Path("companyworld_episodes.json"),
    oracle_output: Path | None = None,
    limit: int | None = None,
):
    """Compile CompanyWorld into public Veritas episodes plus optional private oracles."""
    from investigation_world.companyworld import write_companyworld_bundle

    result = write_companyworld_bundle(
        dataset,
        output,
        oracle_output=oracle_output,
        limit=limit,
    )
    typer.echo(json.dumps(result, indent=2, default=str))
    if not result["validation"]["errors"]:
        return
    raise typer.Exit(1)


@app.command("benchmark-companyworld")
def benchmark_companyworld_cmd(
    dataset: Path,
    output: Path = Path("companyworld_benchmark_report.json"),
    limit: int | None = None,
    skip_determinism: bool = False,
):
    """Attack and validate a compiled CompanyWorld benchmark at scale."""
    from investigation_world.benchmark import write_companyworld_benchmark_report

    report = write_companyworld_benchmark_report(
        dataset,
        output,
        limit=limit,
        verify_determinism=not skip_determinism,
    )
    typer.echo(
        json.dumps(
            {
                "passed": report.passed,
                "world_id": report.world_id,
                "episodes": report.episodes,
                "task_families": report.task_families,
                "failed_invariants": [
                    item.name for item in report.invariants if not item.passed
                ],
                "report": str(output),
            },
            indent=2,
        )
    )
    raise typer.Exit(0 if report.passed else 1)


if __name__ == "__main__":
    app()
