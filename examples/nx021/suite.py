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
    results={}
    for shared in (False,True):
        observations=[]
        for _,k,p,probes,gold in events:
            latent=probes[0] if shared else gold
            observations.append((effect(latent),effect(latent)))
        for arm in ('veto','inverse','confirmed'):
            memory=[None]*16
            writes=correct=checks=0
            for event,(first,second) in zip(events,observations):
                _,key,p,probes,gold=event
                if not gate.accept(p,probes):
                    continue
                checks+=1
                if predicted[p]!=first:
                    if arm=='veto':
                        continue
                    p=inverse[first]
                    if arm=='confirmed':
                        checks+=1
                        if predicted[p]!=second:
                            continue
                memory[key]=p
                writes+=1
                correct+=p==gold
            results[f'{arm}_{int(shared)}']=dict(writes=writes,correct=correct,checks=checks,
                accuracy=sum(a==b for a,b in zip(memory,targets))/16,coverage=sum(a is not None for a in memory)/16)
    return results,len(counts),sum(map(sum,counts))

if __name__=='__main__':
    seeds=json.loads(Path('seeds.json').read_text())
    rows={}
    for seed in seeds:
        rows[seed],bins,n=study(seed)
    dest=Path(os.environ['TRAINLAB_OUTPUT_DIR'])
    config=json.loads(Path('recipe.json').read_text())
    pins={k:digest(Path(k)) for k in config['inputs']}
    obs=dict(seed_count=len(rows),families=1,confidence_bins=bins,calibration_encounters=n)
    receipt=dict(schema='trainlab.execution-adequacy-observations.v1',recipe_sha256=recipe_identity(config),inputs=pins,producer=dict(file='suite.py',sha256=pins['suite.py']),observations=obs)
    for name,data in [('results',rows),('metrics',{'experiments':1}),('observations',receipt)]:
        (dest/(name+'.json')).write_text(json.dumps(data))
