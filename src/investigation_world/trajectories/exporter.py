import json
from pathlib import Path
from .schema import Trajectory

def export_jsonl(runs:list[Trajectory], path:Path):
    path.write_text("\n".join(r.model_dump_json() for r in runs) + ("\n" if runs else ""))

def export_parquet(runs:list[Trajectory], path:Path):
    try:
        import duckdb
        rows=[json.loads(r.model_dump_json()) for r in runs]
        duckdb.connect().execute("CREATE TABLE trajectories AS SELECT * FROM rows").fetchall()
    except Exception as exc:
        raise RuntimeError("Parquet export requires DuckDB and a configured output adapter") from exc

def failure_labels(result:dict):
    labels=[]
    if result.get('false_merge_count',0): labels.append('FALSE_ENTITY_MERGE')
    if result.get('unsupported_claim_count',0): labels.append('UNSUPPORTED_CLAIM')
    if result.get('overall_reward',0)<.25: labels.append('PREMATURE_CONCLUSION')
    return labels

