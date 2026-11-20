"""Run from this directory with the Veritas ecosystem on PYTHONPATH."""
import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

from forge_data.core import canonical, release
from forge_data.dataset import Dataset
from investigation_world.evidence import EvidenceRecord
from research_lab.adapters import import_forge, import_trainlab
from research_lab.core import Controller
from research_lab.evidence import link, put_node
from trainlab.runner import digest, run_experiment, verify_run, write_json
from trainlab.research_adequacy import recipe_identity

parser = argparse.ArgumentParser()
parser.add_argument('out',type=Path)
parser.add_argument('--fresh',action='store_true')
args = parser.parse_args()
root = args.out.resolve()
root.mkdir(parents=True,exist_ok=False)
stage = root/'stage'
stage.mkdir()
here = Path(__file__).resolve().parent
for name in ('suite.py','run.py','PROTOCOL.md'):
    shutil.copyfile(here/name,stage/name)
shutil.copyfile(here.parent/'csm_nx2/verification.py',stage/'verification.py')
cutoff = '2026-01-01T00:00:00Z'
spec = dict(dataset_id='nx-seed-panel',source_id='constructed/nx',source_version='1',adapter='operations-jsonl',license_id='Apache-2.0',provenance_uri='https://github.com/FPC-effortless/veritas',ai_use_allowed=True,redistribution_allowed=True,privacy_reviewed=True,split_salt='nx-autonomous-v1')
write_json(root/'spec.json',spec)
with (root/'source.jsonl').open('wb') as stream:
    for i in (range(12000,12320) if args.fresh else range(11000,11320)):
        stream.write(canonical(dict(episode_id=str(i),subject_id=str(i),record_id=str(i),observed_at=cutoff,available_at=cutoff,observation={'seed':i},action=None,outcome={'status':'unknown','verified':False})))
dataset = root/'dataset'
release(root/'source.jsonl',root/'spec.json',dataset)
pin = digest(dataset/'manifest.json')
rows = Dataset(dataset,manifest_sha256=pin).examples('validation',cutoff=cutoff,feature_fields=['seed'])
seeds = sorted(row['features']['seed'] for row in rows)
write_json(stage/'seeds.json',seeds)
pre = dict(seed_count=len(seeds),consequence_rows=8,calibration_encounters=1200,families=1)
write_json(stage/'design.json',pre)
inputs = sorted(str(p.relative_to(stage)) for p in stage.rglob('*') if p.is_file())
recipe = dict(schema='trainlab.experiment.v1',execution_purpose='research',name='NX-021 inverse consequence repair',description='Paired consequence intervention under persistent sensor corruption',command=[sys.executable,'suite.py'],seed=0,timeout_seconds=600,source_kind='CONSTRUCTED',split_identity=pin,inputs=[*inputs,'adequacy.json'],artifacts=['results.json','observations.json'],metrics={'experiments':'max'},budget={'replicates':len(seeds),'consequence_calibration_encounters':1200})
dimensions,execution = {},{}
for dim,field,threshold,op,reason in [
    ('model_size','consequence_rows',8,'eq','Fit eight consequence distributions.'),
    ('training_duration','calibration_encounters',1200,'eq','Use a fixed number of future consequences in calibration.'),
    ('datasets','seed_count',12,'ge','Require at least twelve independent procedural realizations.'),
    ('training_regime','families',1,'eq','Execute each specified bounded diagnostic.')]:
    criterion = dict(field=field,operator=op,threshold=threshold,rationale=reason)
    dimensions[dim] = dict(configuration=reason,justification='Compare paired methods within the defined public synthetic generator.',limitations='Small constructed regime with hand-specified hypothesis classes.',criteria=[dict(criterion,id=field,evidence='design.json')])
    execution[dim] = [criterion]
contract = dict(schema='trainlab.research-adequacy.v1',claim_kind='bounded_diagnostic',claim='Measure mechanism behavior on fixed synthetic tasks.',scope='Seeded public NX panel',excluded_claims='Architecture ranking, external benchmark scores and general intelligence',recipe_sha256=recipe_identity(recipe),inputs={n:digest(stage/n) for n in inputs},review=dict(author='NX implementation session',reviewer='Veritas independent review session',basis='Prospective protocol and independent source review of learner/scorer separation, stress conditions and evaluation.',criteria_frozen_before_evaluation=True),dimensions=dimensions,execution=dict(artifact='observations.json',dimensions=execution))
write_json(stage/'adequacy.json',contract)
recipe['research_adequacy'] = dict(file='adequacy.json',sha256=digest(stage/'adequacy.json'))
write_json(stage/'recipe.json',recipe)
run = run_experiment(stage/'recipe.json',root/'runs')
directory = root/'runs'/run['id']
if run['status'] != 'succeeded' or not verify_run(directory)['valid']:
    raise RuntimeError(f'Inspect {directory}')
lab = Controller(root/'lab')
import_forge(lab,dataset,pin)
import_trainlab(lab,directory)
record = EvidenceRecord(evidence_type='csm.nx021_repair',outcome='OBSERVED',visibility='public',claim='Constructed NX panel executed.',subjects=[dict(kind='dataset',subject_id='nx-seeds',content_sha256=pin)],producer=dict(producer_id='nx-suite',producer_version='1',content_sha256=digest(stage/'suite.py')),artifacts=[dict(artifact_id='results',content_sha256=digest(directory/'output/results.json'))],observed_at=datetime.fromisoformat(run['finished_at']),provenance={'qualification':'NOT_QUALIFIED','run_id':run['id']})
body = record.model_dump(mode='json')
write_json(root/'evidence.json',body)
put_node(lab,'nx021.finding','finding',body)
link(lab,'nx021.finding','derived_from','trainlab.'+run['id'])
link(lab,'nx021.finding','derived_from','forge.'+pin[:24])
print(directory)
