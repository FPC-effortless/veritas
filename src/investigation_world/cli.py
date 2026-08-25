import json, typer
from pathlib import Path
from investigation_world.world.generator import WorldFactory,WorldGenerationConfig,validate_world
from investigation_world.evidence.projector import project
app=typer.Typer(help="Synthetic corporate investigation environment")
@app.command()
def generate_world(seed:int=42, output:Path=Path("world.json")):
    w=WorldFactory.generate(seed,WorldGenerationConfig()); output.write_text(w.model_dump_json(indent=2)); typer.echo(f"generated {w.world_id} -> {output}")
@app.command()
def validate_world_cmd(world:Path):
    from investigation_world.core.models import CanonicalWorld
    errors=validate_world(CanonicalWorld.model_validate_json(world.read_text())); typer.echo("valid" if not errors else "\\n".join(errors)); raise typer.Exit(1 if errors else 0)
@app.command()
def render_evidence(world:Path, output:Path=Path("evidence.json"), seed:int=0):
    from investigation_world.core.models import CanonicalWorld
    w,_=project(CanonicalWorld.model_validate_json(world.read_text()),seed); output.write_text(w.model_dump_json(indent=2)); typer.echo(f"rendered {len(w.documents)} documents")
if __name__=="__main__": app()

