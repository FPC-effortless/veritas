import json,typer
from pathlib import Path
from investigation_world.world.generator import WorldFactory,WorldGenerationConfig,validate_world
from investigation_world.evidence.projector import project
app=typer.Typer(help='Synthetic corporate investigation environment')
@app.command()
def generate_world(seed:int=42,output:Path=Path('world.json')):
 w=WorldFactory.generate(seed,WorldGenerationConfig()); output.parent.mkdir(parents=True,exist_ok=True); output.write_text(w.model_dump_json(indent=2)); typer.echo(f'generated {w.world_id} -> {output}')
@app.command()
def validate_world_cmd(world:Path):
 from investigation_world.core.models import CanonicalWorld
 errors=validate_world(CanonicalWorld.model_validate_json(world.read_text())); typer.echo('valid' if not errors else '\n'.join(errors)); raise typer.Exit(1 if errors else 0)
@app.command()
def render_evidence(world:Path,output:Path=Path('evidence.json'),seed:int=0):
 from investigation_world.core.models import CanonicalWorld
 w,_=project(CanonicalWorld.model_validate_json(world.read_text()),seed); output.write_text(w.model_dump_json(indent=2)); typer.echo(f'rendered {len(w.documents)} documents')
@app.command()
def generate_tasks(world_id:str,output:Path=Path('tasks.json'),count:int=48,seed:int=0):
 from investigation_world.tasks.spec import generate_tasks,split_manifest
 output.write_text(json.dumps({'tasks':[t.model_dump(mode='json') for t in generate_tasks(world_id,count,seed)],'splits':split_manifest()},indent=2)); typer.echo(f'generated {count} tasks')
@app.command()
def build_index(world:Path,database:Path=Path('search.sqlite')):
 from investigation_world.core.models import CanonicalWorld
 from investigation_world.search.index import FrozenSearchIndex
 i=FrozenSearchIndex(str(database)); i.build(CanonicalWorld.model_validate_json(world.read_text())); typer.echo(f'indexed {database}')
if __name__=='__main__': app()
