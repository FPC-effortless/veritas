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


if __name__ == "__main__":
    app()
