import json,tempfile
from pathlib import Path
from .schema import Trajectory
def export_jsonl(runs:list[Trajectory],path:Path):
 path.parent.mkdir(parents=True,exist_ok=True); path.write_text(''.join(r.model_dump_json()+'\n' for r in runs))
def export_parquet(runs:list[Trajectory],path:Path):
 import duckdb
 path.parent.mkdir(parents=True,exist_ok=True)
 with tempfile.NamedTemporaryFile(mode='w',suffix='.jsonl',delete=False) as f:
  for r in runs: f.write(r.model_dump_json()+'\n')
  source=f.name
 con=duckdb.connect(); con.execute('CREATE OR REPLACE TABLE trajectories AS SELECT * FROM read_json_auto(?)',(source,)); con.execute('COPY trajectories TO ? (FORMAT PARQUET)',(str(path),)); con.close(); Path(source).unlink(missing_ok=True)
def failure_labels(result:dict):
 labels=[]
 if result.get('false_merge_count',0): labels.append('FALSE_ENTITY_MERGE')
 if result.get('unsupported_claim_count',0): labels.append('UNSUPPORTED_CLAIM')
 if result.get('calibration',1)<.4: labels.append('OVERCONFIDENCE')
 if result.get('efficiency',1)<.25: labels.append('LOW_VALUE_SEARCH')
 if result.get('overall_reward',0)<.25: labels.append('PREMATURE_CONCLUSION')
 return labels
