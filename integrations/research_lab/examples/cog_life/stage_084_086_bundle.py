"""Prepare exact COG-084 or COG-086 role-specific bundles; never author approvals."""
from hashlib import sha256
from pathlib import Path
import argparse,json,shutil,sys

from forge_data.diagnostics import diagnose
from trainlab.research_adequacy import recipe_identity,assess
from trainlab.execution_adequacy import validate_execution
from trainlab.runner import contained_file,load_config
from stage_084_086_data import documents,make_causal,make_practice,SEEDS,TRIALS_PER_PHASE,HOLD_CONTEXTS_PER_SKILL,number
from stage_086_trajectory import practice_trajectory
import conductor

HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
MODEL=REPO/'integrations/research_lab/src/research_lab/life_study_082_086.py'
WORKER='stage_084_086_worker.py'
PROTOCOL='PROTOCOL_082_086.md'
MODES=('cog084','cog086')
CLAIM={'cog084':'Probe versus passive and frozen after bounded synthetic confounding shift',
       'cog086':'Selective replay versus update-matched controls on synthetic cue retention'}

def require(ok,msg):
    if not ok:raise ValueError(msg)
def wire(d):
    return json.dumps(d,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
def digest_file(path):return sha256(Path(path).read_bytes()).hexdigest()
def write(path,d):
    with path.open('xb') as f:f.write(wire(d))
    path.chmod(0o600)
def copy(src,dst):
    require(src.is_file() and not src.is_symlink(),'source path not a regular file')
    with dst.open('xb') as f:f.write(src.read_bytes())
    dst.chmod(0o600)
def read(p):return json.loads(p.read_bytes())

def data_for(study,dest):
    require(study in MODES,'unknown study')
    dest.mkdir(mode=0o700,parents=True,exist_ok=False)
    lane='causal' if study=='cog084' else 'practice'
    if study=='cog084':s,q,t=documents()
    else:
        s,q,t=({'runs':[]} for _ in range(3))
        for seed in SEEDS:
            run=f"run-{number(seed,'masked-run'):014x}"
            items=practice_trajectory(seed,TRIALS_PER_PHASE,HOLD_CONTEXTS_PER_SKILL)
            for d,v in zip((s,q,t),items):d['runs'].append({'run':run,'practice':v})
    for filename,role,obj in (
        ('training-observations.json','training',s),
        ('evaluator-queries.json','query',q),
        ('scorer-only.json','truth',t)):
        write(dest/filename,{'study':study,'role':role,'runs':[dict(run=r['run'],cases=r[lane]) for r in obj['runs']]})
    # Fresh, separately seeded small acquisition anchors check the synthetic
    # instrument, with no tuning and no learning updates from these examples.
    if study=='cog084': anchors=make_causal(84301,8)[0][:8]
    else: anchors=make_practice(86301,16,8)[0][:8]
    write(dest/'calibration-observations.json',{'study':study,'cases':anchors})
    cases=read(dest/'training-observations.json')['runs']
    rows=[]
    for k,g in enumerate(cases):
        for i,row in enumerate(g['cases']):
            group=sha256(f'{g["run"]}:{row.get("pair",row.get("episode"))}'.encode()).hexdigest()
            rows.append(dict(id=f'train-{k}-{i}',split='train',features={'identity':group},groups={'acquisition':group}))
    for i,row in enumerate(anchors):
        group=sha256(f'calstrument:{study}:{i}'.encode()).hexdigest()
        rows.append(dict(id=f'cal-{i}',split='validation',features={'identity':group},groups={'acquisition':group}))
    view=dest/'FORGE_VIEW.json'
    write(view,dict(schema='forge.diagnostic-input.v1',feature_fields=['identity'],group_fields=['acquisition'],rows=rows))
    receipt=diagnose(view,sha256=digest_file(view),max_rows=100000,max_findings=0)
    write(dest/'FORGE_RECEIPT.json',receipt)
    rt=REPO/'src/investigation_world/life'
    world=dict(schema='cog-life.host-source.v1',scope=study,constructed=1,
               role_private=1,handed_evaluation_answer_to_learner=0,
               world_hashes={p.name:digest_file(p) for p in sorted(rt.glob('*.py'))},
               data_builder=digest_file(HERE/'stage_084_086_data.py'))
    if study=='cog086':world['distinct_trajectory_builder']=digest_file(HERE/'stage_086_trajectory.py')
    write(dest/'WORLD_SPEC.json',world)
    write(dest/'DATA_HASHES.json',{p.name:digest_file(p) for p in sorted(dest.iterdir()) if p.is_file()})

def has(stage,execution,study):
    pred={'predict':('fit','checkpoint.json'),'verify':('predict','predictions.json')}[stage]
    parent,artifact=pred
    receipt=execution/study/parent/'stage-receipt.json'
    r=conductor.provenance(receipt,parent,study)
    native=(receipt.parent/'runs'/r['id']).resolve(strict=True)
    p=contained_file(native/'output',artifact)
    require(digest_file(p)==r['artifacts'][artifact],'exact predecessor artifact invalid')
    return p,artifact

def stage_bundle(study,phase,data,execution,dest,author,reviewer):
    require(study in MODES and phase in ('fit','predict','verify'),'unknown scoped stage')
    require(author.strip() and reviewer.strip() and author.strip().casefold()!=reviewer.strip().casefold(),'designated independent reviewer needed')
    manifest=read(data/'DATA_HASHES.json')
    # Verify only role files this stage is permitted to stage.
    selected={'fit':{'training-observations.json':'train','calibration-observations.json':'cal'},
              'predict':{'evaluator-queries.json':'request'},
              'verify':{'scorer-only.json':'truth'}}[phase]
    selected|={'WORLD_SPEC.json':'world_spec','FORGE_RECEIPT.json':'forge_receipt'}
    for name in selected:require(digest_file(data/name)==manifest[name],'role source changed')
    art=None
    if phase!='fit':art=has(phase,execution,study)
    dest.mkdir(mode=0o700,parents=True,exist_ok=False)
    sources={name:(data/name,role) for name,role in selected.items()}
    worker=WORKER if study=='cog084' else 'stage_086_worker.py'
    sources|={worker:(HERE/worker,'code')}
    if phase=='fit':sources[MODEL.name]=(MODEL,'code')
    else:
        p,name=art
        sources[name]=(p,'fit_artifact' if phase=='predict' else 'prediction_artifact')
    for name,(src,_) in sources.items():copy(src,dest/name)
    # Bundle a role-safe protocol excerpt. Exact host seeds and generator
    # implementation stay in the independent data-owner closure.
    protocol=(HERE/PROTOCOL).read_text()
    old='Exact seeds 84113, 84119 and 84131.'
    require(protocol.count(old)==1,'cannot construct safe protocol excerpt')
    protocol=protocol.replace(old,'Three fixed paired seeds, recorded with the separately sealed world generator.')
    if study=='cog086':
        protocol+='\n## 086 pre-outcome acquisition-order amendment\n\nIndependently shuffle the fixed within-phase exposure order in each matched run; only the run IDs and this order reach the learner. Each matched run derives a distinct replay RNG from its opaque run identity; replay arms held equal opportunity and feature work. Sealed candidate worlds still repeat eight motifs per phase and are not independent observations or external transfer. Refuse fit if the model-consumed cue/feedback schedules or replay RNGs are not three distinct streams. Original inert identical-schedule draft is retained, not tested.\n'
    with (dest/'PROTOCOL_ROLE.md').open('x',encoding='utf-8') as f:f.write(protocol)
    (dest/'PROTOCOL_ROLE.md').chmod(0o600)
    role_metrics={'fit':('checkpoint.json','paired_seeds'),'predict':('predictions.json','predicted_cases'),'verify':('aggregates.json','verified_seeds')}
    artifact,metric=role_metrics[phase]
    plan=dict(seeds=3,causal_bins=4,replay_parameter_cap=12,planned_causal_opportunities=960,
              planned_replay_updates=4608,expected_cal_anchors=8,expected_predicted_cases=6 if study=='cog084' else 96,
              max_prediction_updates=0,fit_role_separation=1,predict_role_separation=1,score_role_separation=1)
    write(dest/'PLAN_SCALARS.json',plan)
    roles={n:role for n,(_,role) in sources.items()}
    roles|={'PLAN_SCALARS.json':'forge_receipt','adequacy.json':'protocol','PROTOCOL_ROLE.md':'protocol'}
    config=dict(schema='trainlab.experiment.v1',execution_purpose='research',name=f'{study}-{phase}',
                description=CLAIM[study],command=[sys.executable,worker,phase],seed=62084 if study=='cog084' else 62086,
                timeout_seconds=120 if phase=='fit' else 60,inputs=sorted(roles),artifacts=[artifact,'observations.json'],
                metrics={metric:'max'},source_kind='CONSTRUCTED',split_identity='THREE_PAIRED_CONSTRUCTED_LIFE_SCENARIOS',budget={'cpu':1})
    dnames=('model_size','training_duration','datasets','training_regime')
    lane='cog084'==study
    before=list(zip(dnames,[(('causal_bins',4) if lane else ('replay_parameter_cap',12)),
            (('planned_causal_opportunities',960) if lane else ('planned_replay_updates',4608)),
            ('seeds',3),({'fit':'fit_role_separation','predict':'predict_role_separation','verify':'score_role_separation'}[phase],1)]))
    if phase=='fit':
        if lane:
            after=[('causal_count_bins','eq',4),('presented_opportunities','eq',960),('min_per_setting','ge',20),('measured_native_probes','eq',960)]
        else:
            after=[('max_replay_parameters','le',12),('measured_replay_updates','eq',4608),('calibration_observations','eq',8),('measured_equal_work_slots','eq',1)]
    elif phase=='predict':after=[('paired_seeds','eq',3),('parameter_updates','eq',0),('predicted_cases','eq',plan['expected_predicted_cases']),('query_role_only','eq',1)]
    else:after=[('verified_seeds','eq',3),('fit_or_prediction_operations','eq',0),('verified_seeds','eq',3),('score_only','eq',1)]
    contract=dict(schema='trainlab.research-adequacy.v1',claim=CLAIM[study],claim_kind='bounded_diagnostic',
       scope=f'{study} {phase} constructed, exact reviewed phase role only',
       excluded_claims='No scientific promotion, external transfer, real legal actions, full-cost dominance or authenticated independent populations.',
       recipe_sha256=recipe_identity(config),inputs={n:digest_file(dest/n) for n in roles if n!='adequacy.json'},
       review=dict(author=author,reviewer=reviewer,basis='Designated independently reviewed stage; actual GO token is external and mandatory',criteria_frozen_before_evaluation=True),
       dimensions={},execution={'artifact':'observations.json','dimensions':{}})
    for (dim,(key,n)),(field,op,bound) in zip(before,after,strict=True):
        contract['dimensions'][dim]=dict(configuration=f'Frozen bounded {study} {phase}: {key}',
         justification='Necessary explicit condition, not sufficient scientific validation.',
         limitations='Constructed fixed cohorts; no protected TEST or causal population qualification.',
         criteria=[dict(id=key,rationale='Prespecified phase necessary condition',evidence='PLAN_SCALARS.json',field=key,operator='eq',threshold=n)])
        rules=[dict(field=field,operator=op,threshold=bound,rationale='Prespecified executed observation bound')]
        if phase=='fit' and dim=='datasets' and field!='calibration_observations':
            rules.append(dict(field='calibration_observations',operator='eq',threshold=8,rationale='Exact separate observed instrument anchors, not fitted'))
        if phase=='fit' and study=='cog086' and dim=='training_regime':
            rules.extend(dict(field=x,operator='eq',threshold=3,rationale='Distinct optimization trajectories, proof is not extra statistical sample size') for x in ('independent_trajectory_orders','distinct_matched_replay_rngs'))
        contract['execution']['dimensions'][dim]=rules
    write(dest/'adequacy.json',contract);config['research_adequacy']={'file':'adequacy.json','sha256':digest_file(dest/'adequacy.json')}
    write(dest/'recipe.json',config)
    require(load_config(dest/'recipe.json')==config,'native schema mismatch')
    validate_execution(contract,config)
    pins={n:digest_file(dest/n) for n in roles}
    verdict=assess(config,dest,pins)
    require(verdict['status']=='DECLARED_CRITERIA_MET','native numeric plan did not pass')
    write(dest/'DRAFT_ROLE_INVENTORY.json',dict(study=study,phase=phase,input_roles=roles,inputs=pins,recipe_sha256=digest_file(dest/'recipe.json'),review='NOT_ISSUED',execution='NOT_STARTED'))
    print(json.dumps({'study':study,'phase':phase,'recipe_sha256':digest_file(dest/'recipe.json'),'numeric_declarations':len(verdict['checks']),'launch':'NOT_AUTHORIZED_BY_BUILDER'}))

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('data');d.add_argument('study',choices=MODES);d.add_argument('dest',type=Path)
    b=sub.add_parser('stage');b.add_argument('study',choices=MODES);b.add_argument('phase',choices=('fit','predict','verify'))
    for name in ('data','execution','dest'):b.add_argument(name,type=Path)
    b.add_argument('--author',required=True);b.add_argument('--reviewer',required=True)
    a=p.parse_args()
    if a.command=='data':data_for(a.study,a.dest)
    else:stage_bundle(a.study,a.phase,a.data,a.execution,a.dest,a.author,a.reviewer)
if __name__=='__main__':main()
