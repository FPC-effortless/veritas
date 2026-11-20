import json
import os
import random
from pathlib import Path
from trainlab.runner import digest
from trainlab.research_adequacy import recipe_identity
from verification import Confidence, reading, stream

def study(seed):
    rng=random.Random(seed+78123)
    mapping=rng.sample(range(8),8)
    def effect(value):
        return reading(rng,mapping[value],.9)
    counts=[[0]*8 for _ in mapping]
    for _ in range(1200):
        value=rng.randrange(8)
        counts[reading(rng,value,.9)][effect(value)]+=1
    predicted=[max(range(8),key=row.__getitem__) for row in counts]
    inverse=[max(range(8),key=lambda i:counts[i][j]) for j in range(8)]
    gate=Confidence(seed+100000)
    events,targets=stream(seed,True)
    dependent=set(rng.sample(range(16),8))
    results={}
    for topology in ('downstream','upstream'):
        active_votes=[0]*16
        sham_votes=[0]*16
        for key in range(16):
            for _ in range(6):
                state=rng.randrange(8)
                primary=reading(rng,state,.9)
                decoy=rng.randrange(8)
                natural=primary if key in dependent else state
                exposed=decoy if key in dependent and topology=='downstream' else natural
                active_votes[key]+=effect(exposed)==predicted[decoy]
                sham_votes[key]+=effect(natural)==predicted[decoy]
        observations=[]
        for _,key,p,probes,gold in events:
            signal=probes[0] if key in dependent else gold
            observations.append((effect(signal),effect(signal)))
        panel={}
        for arm in ('repair','veto','active','sham','oracle'):
            votes=active_votes if arm=='active' else sham_votes
            blocked={k for k,v in enumerate(votes) if v>=3}
            if arm=='oracle':
                blocked=dependent
            elif arm=='repair':
                blocked=set()
            elif arm=='veto':
                blocked=set(range(16))
            memory=[None]*16
            correct=writes=checks=0
            for (_,key,p,probes,gold),(first,second) in zip(events,observations):
                if not gate.accept(p,probes):
                    continue
                checks+=1
                if predicted[p]!=first:
                    if key in blocked:
                        continue
                    p=inverse[first]
                    checks+=1
                    if predicted[p]!=second:
                        continue
                memory[key]=p
                correct+=p==gold
                writes+=1
            panel[arm]=dict(accuracy=sum(x==y for x,y in zip(memory,targets))/16,
                true_positive=len(blocked & dependent),false_positive=len(blocked-dependent),
                correct=correct,writes=writes,checks=checks,
                audit_outcomes=96 if arm in ('active','sham') else 0)
        results[topology]=panel
    return results,len(counts),sum(map(sum,counts))

if __name__=='__main__':
    seeds=json.loads(Path('seeds.json').read_text())
    rows={}
    sizes=[]
    for seed in seeds:
        rows[seed],bins,n=study(seed)
        sizes.append((bins,n))
    dest=Path(os.environ['TRAINLAB_OUTPUT_DIR'])
    config=json.loads(Path('recipe.json').read_text())
    pins={k:digest(Path(k)) for k in config['inputs']}
    obs=dict(seed_count=len(rows),families=1,consequence_rows=min(x for x,_ in sizes),calibration_encounters=min(x for _,x in sizes))
    receipt=dict(schema='trainlab.execution-adequacy-observations.v1',recipe_sha256=recipe_identity(config),inputs=pins,producer=dict(file='suite.py',sha256=pins['suite.py']),observations=obs)
    for name,data in [('results',rows),('metrics',{'experiments':1}),('observations',receipt)]:
        (dest/(name+'.json')).write_text(json.dumps(data))
