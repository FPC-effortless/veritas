"""Stage-stopped stdlib child. Conductor gates exact role bytes before launch."""
from hashlib import sha256
import json,os,sys
from math import exp,isfinite
from pathlib import Path

MODES={'cog084':('probe','passive','frozen'),'cog086':('current','uniform','selective')}
READ={'fit':{'training-observations.json','calibration-observations.json'},
      'predict':{'checkpoint.json','evaluator-queries.json'},
      'verify':{'predictions.json','scorer-only.json'}}

def require(ok,msg):
    if not ok:raise ValueError(msg)

def read(name):return json.loads(Path(name).read_bytes())
def wire(x):return json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def put(root,n,x):(root/n).write_bytes(wire(x)+b'\n')
def identity(p):return sha256(Path(p).read_bytes()).hexdigest()

def fit_causal(events):
    from life_study_082_086 import CausalEstimator,CausalObservation
    require(len(events)==320 and len({a['pair'] for a in events})==320,'causal support or scope')
    arms={k:CausalEstimator(k) for k in MODES['cog084']}
    estimates={}
    for i,b in enumerate(events):
        phase='before' if i<160 else 'after'
        require(set(b)=={'phase','pair','active','passive'} and b['phase']==phase,'causal chronology changed')
        for k,arm in arms.items():
            x=CausalObservation(**b['active' if k=='probe' else 'passive'])
            require(x.seq==i,'paired observation order changed')
            arm.observe(x)
        if i in (159,319):
            estimates[phase]={k:a.estimate(min_per_cell=20) for k,a in arms.items()}
            require(all(x['effect'] is not None for x in estimates[phase].values()),'causal cell lacks support')
        if i==159:
            arms['frozen'].freeze()
            for k in ('probe','passive'):arms[k].counts=[[0,0],[0,0]]
    return estimates

def fit_practice(events, replay_seed):
    from life_study_082_086 import ReplayLearner,PracticeObservation
    require(len(events)==256 and len({a['episode'] for a in events})==256,'practice support or scope')
    arms={k:ReplayLearner(k,replay_seed,capacity=32) for k in MODES['cog086']}
    earlier={}
    for i,row in enumerate(events):
        phase='early' if i<128 else 'later'
        require(set(row)=={'phase','episode','visible'} and row['phase']==phase,'practice chronology changed')
        raw=row['visible'];x=PracticeObservation(**(raw|{'cues':tuple(raw['cues'])}))
        require(x.seq==i and len(set(x.cues))==2,'practice exposure work mismatch')
        for m in arms.values():m.observe(x)
        if i==127:earlier={k:dict(a.weights) for k,a in arms.items()}
    return {k:dict(pre=earlier[k],post=dict(a.weights),cost=dict(a.cost)) for k,a in arms.items()}

def calibration(study,anchors):
    """Independent benign observation fixtures used for schema/lineage inspection only."""
    rows=anchors['cases']
    require(anchors['study']==study and len(rows)==8,'calibration instrument extent')
    from life_study_082_086 import CausalObservation,PracticeObservation, bit
    if study=='cog084':
        require(len({x['pair'] for x in rows})==8,'duplicate cal groups')
        active=[CausalObservation(**x['active']) for x in rows]
        passive=[CausalObservation(**x['passive']) for x in rows]
        require({x.exposure for x in active}=={0,1} and all(x.randomized and x.probe_receipt and bit(x.consequence) for x in active) and all(not x.randomized and x.probe_receipt is None and bit(x.consequence) for x in passive),'unusable causal instrument')
    else:
        r=[PracticeObservation(**(x['visible']|{'cues':tuple(x['visible']['cues'])})) for x in rows]
        require(all(len(set(x.cues))==2 and bit(x.feedback) and x.observed_outcome_id for x in r),'unusable practice instrument')
    return 8

def lineage(document,study,role):
    require(set(document)=={'study','role','runs'} and document['study']==study and document['role']==role,'input-role schema mismatch')
    rows=document['runs']
    require(len(rows)==3 and len({r['run'] for r in rows})==3 and all(set(r)=={'run','cases'} for r in rows),'incomplete pair inventory')
    return rows

def fit(study):
    train=lineage(read('training-observations.json'),study,'training')
    n=calibration(study,read('calibration-observations.json'))
    if study!='cog086':raise ValueError('wrong preregistered worker scope')
    sequences=[sha256(wire([{'phase':row['phase'],'cues':row['visible']['cues'],
                   'feedback':row['visible']['feedback']} for row in run['cases']])).hexdigest()
               for run in train]
    seeds=[int.from_bytes(sha256(('bounded-replay-rng:'+r['run']).encode()).digest()[:8],'big') for r in train]
    require(len(set(sequences))==len(set(seeds))==3,'duplicate model-consumed trajectories or replay streams')
    result=[dict(run=r['run'],cases=fit_practice(r['cases'],seed)) for r,seed in zip(train,seeds)]
    observations=dict(calibration_observations=n,paired_seeds=len(result),learner_role_only=1,fits_or_contrasts=len(result)*3)
    if study=='cog084':
        observations.update(causal_count_bins=4,presented_opportunities=sum(len(r['cases']) for r in train),
            measured_native_probes=sum(x['cases']['after']['probe']['cost']['probes'] for x in result),
            min_per_setting=min(n for r in result for phase in r['cases'].values() for arm in phase.values() for n in arm['exposure_groups']))
    else:
        observations.update(max_replay_parameters=max(len(z['post']) for r in result for z in r['cases'].values()),
            measured_replay_updates=sum(z['cost']['updates'] for r in result for z in r['cases'].values()),
            measured_feature_touches=sum(z['cost']['features_touched'] for r in result for z in r['cases'].values()),
            measured_equal_work_slots=int(len({z['cost']['updates'] for r in result for z in r['cases'].values()})==1),
            independent_trajectory_orders=len(set(sequences)),distinct_matched_replay_rngs=len(set(seeds)))
    return {'study':study,'role':'checkpoint','runs':result},observations

def align(study,a,ar,b,br):
    first=lineage(a,study,ar); second=lineage(b,study,br)
    require([x['run'] for x in first]==[x['run'] for x in second],'paired run ID mismatch')
    return zip(first,second)

def pval(w,c):
    s=sum(w.get(k,0.) for k in sorted(set(c)))+w.get('::bias',0.)
    require(isfinite(s),'nonfinite model')
    return 1/(1+exp(-max(-16,min(16,s))))

def predict(study):
    out=[]
    for m,q in align(study,read('checkpoint.json'),'checkpoint',read('evaluator-queries.json'),'query'):
        if study=='cog084':
            require(q['cases']==[{'phase':'before'},{'phase':'after'}] and set(m['cases'])=={'before','after'},'causal query schema')
            cases=m['cases']
        else:
            require(len(q['cases'])==32 and len({x['query'] for x in q['cases']})==32,'practice query extent')
            cases=[]
            for x in q['cases']:
                require(set(x)=={'query','phase','cues'} and len(x['cues'])==2,'unexpected query or gold field')
                cases.append(dict(query=x['query'],phase=x['phase'],
                                  p={a:{k:pval(m['cases'][a][k],x['cues']) for k in ('pre','post')} for a in MODES[study]}))
            cases={'predictions':cases,'accounting':{k:v['cost'] for k,v in m['cases'].items()}}
        out.append(dict(run=q['run'],cases=cases))
    n=6 if study=='cog084' else 96
    return {'study':study,'role':'prediction','runs':out},dict(predicted_cases=n,paired_seeds=len(out),query_role_only=1,parameter_updates=0)

def score(study):
    details=[];gates=[]
    for p,s in align(study,read('predictions.json'),'prediction',read('scorer-only.json'),'truth'):
        if study=='cog084':
            require(len(s['cases'])==2 and {x['phase'] for x in s['cases']}=={'before','after'},'causal truth population')
            cases={}
            for gold in s['cases']:
                phase=gold['phase'];truth=gold['sealed_empirical_effect']
                require(set(gold)=={'phase','sealed_empirical_effect','worlds'} and gold['worlds']==160 and -1<=truth<=1,'causal held support')
                z=p['cases'][phase]
                require(set(z)==set(MODES[study]),'causal arm inventory')
                values={}
                for k,x in z.items():
                    q=x['effect']
                    require(isfinite(q) and -1<=q<=1 and min(x['exposure_groups'])>=20,'unsupported prediction')
                    values[k]=dict(effect=q,absolute_error=abs(q-truth),sign_correct=None if truth==0 else q*truth>0,cost=x['cost'],support=x['exposure_groups'])
                cases[phase]={'reference':truth,'worlds':160,'arms':values}
            a=cases['after']['arms'];delta=a['probe']['absolute_error']-min(a[k]['absolute_error'] for k in ('passive','frozen'))
            cases['post_shift_error_advantage']=delta;gates.append(delta<=-.10 and a['probe']['sign_correct'] is True)
        else:
            r=p['cases']['predictions'];truth={x['query']:x['feedback'] for x in s['cases']}
            require(len(s['cases'])==32 and len(truth)==32 and len(r)==32 and {x['query'] for x in r}==set(truth),'practice truth population')
            cases={}
            for phase in ('early','later'):
                cohort=[x for x in r if x['phase']==phase];require(len(cohort)==16,'practice phase')
                cases[phase]={}
                for arm in MODES[study]:
                    cases[phase][arm]={}
                    for period in ('pre','post'):
                        rows=[(x['p'][arm][period],truth[x['query']]) for x in cohort]
                        require(all(isfinite(v) and 0<=v<=1 and y in (0,1) for v,y in rows),'invalid probability or reference')
                        cases[phase][arm][period]=dict(accuracy=sum((v>=.5)==y for v,y in rows)/16,brier=sum((v-y)**2 for v,y in rows)/16)
            early,later=[cases[k]['selective']['post']['brier']-cases[k]['current']['post']['brier'] for k in ('early','later')]
            gates.append(early<=-.02 and later<=.05);cases['accounting']=p['cases']['accounting']
        details.append(dict(run=p['run'],cases=cases))
    return {'study':study,'qualification':'NOT_QUALIFIED','directional_gate':all(gates),'runs':details},dict(verified_seeds=len(details),score_only=1,fit_or_prediction_operations=0)

def main(phase):
    require(phase in READ,"unknown local worker phase")
    recipe=read('recipe.json');study=recipe['name'].split('-')[0]
    require(study=='cog086' and all(Path(n).is_file() for n in READ[phase]),'invalid role mount')
    all_roles=set().union(*READ.values())
    observed={x for x in all_roles if Path(x).exists()}
    require(observed==READ[phase] and set(recipe['inputs'])&all_roles==observed,'role mount mixed')
    f,name,metric={'fit':(fit,'checkpoint.json','paired_seeds'),'predict':(predict,'predictions.json','predicted_cases'),'verify':(score,'aggregates.json','verified_seeds')}[phase]
    result,obs=f(study);output=Path(os.environ['TRAINLAB_OUTPUT_DIR'])
    producer=Path(__file__).name;pins={n:identity(n) for n in recipe['inputs']}
    evidence=dict(schema='trainlab.execution-adequacy-observations.v1',
                  recipe_sha256=sha256(wire({k:v for k,v in recipe.items() if k!='research_adequacy'})).hexdigest(),
                  inputs=pins,producer={'file':producer,'sha256':pins[producer]},observations=obs)
    put(output,name,result);put(output,'observations.json',evidence);put(output,'metrics.json',{metric:obs[metric]})
if __name__=='__main__':main(*sys.argv[1:])
