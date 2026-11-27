"""Exact reduced witnesses, not native model execution or learned data.
PSN routing.py 2826d07acd87e7293496b44792098c8a003b6f22
USEF models.py b9f1229f982b09f6c41639c068d7db0b3c9639d4
USEF intent_field.py a44a19eb620f6a2e345cf620fb11c554ea528661
"""
from fractions import Fraction as F
from itertools import product, combinations
import json

def require(x, msg):
    if not x: raise RuntimeError(msg)

# Exact simplex abstraction: omit tiny epsilon (which further reduces floor).
# Source clamps to floor and renormalizes; candidate affine simplex map.
n=5; floor=F(1,20); denom=20
cases=violations=upper_violations=candidate_failures=0
minimum=F(1); maximum=F(0)
for a,b,c,d in product(range(denom+1), repeat=4):
    e=denom-a-b-c-d
    if e<0: continue
    p=[F(i,denom) for i in (a,b,c,d,e)]
    q=[max(floor,v) for v in p]; q=[v/sum(q) for v in q]
    z=[floor+(1-n*floor)*v for v in p]
    cases+=1; violations+=min(q)<floor; upper_violations+=max(q)>1-(n-1)*floor
    minimum=min(minimum,min(q)); maximum=max(maximum,max(q))
    candidate_failures+=sum(z)!=1 or min(z)<floor or max(z)>1-(n-1)*floor
require(cases==10626 and violations>0 and candidate_failures==0,'simplex control failed')
# USEF route broadcasts one alpha row. For an abstract task requiring one
# specific expert per example, compute oracle *coverage bound*, not model accuracy.
# Four experts, 2 selected per batch, all ordered batches of four required labels.
batches=0; limited=0; counts={str(i):0 for i in range(5)}; total=0
for labels in product(range(4), repeat=4):
    shared=max(sum(x in S for x in labels) for S in combinations(range(4),2))
    counts[str(shared)]+=1; total+=shared; batches+=1; limited+=shared<4
require(batches==256 and limited>0,'shared routing control failed')
# USEF _match_batch: shape change mixes identities, same-size returns unchanged.
# Distinct histories with identical mean become identical after resizing.
resize_a=(F(1),F(-1)); resize_b=(F(0),F(0))
mean=lambda v:sum(v)/len(v)
require(resize_a!=resize_b and mean(resize_a)==mean(resize_b),'resize collision failed')
report={'scope':'source-equation and combinatorial witness only','dataset':None,'seed':None,
 'psn_floor':{'grid_denominator':denom,'cases':cases,'floor_violations':violations,'upper_bound_violations':upper_violations,'minimum':str(minimum),'maximum':str(maximum),'candidate_failures':candidate_failures},
 'usef_shared_route':{'experts':4,'top_k':2,'batch_size':4,'ordered_batches':batches,'limited_batches':limited,'oracle_covered_rows_histogram':counts,'oracle_shared_coverage':str(F(total,batches*4)),'per_row_oracle_coverage':'1'},
 'usef_resize':{'collision_a':['1','-1'],'collision_b':['0','0'],'both_resized_to':'0'}}
print(json.dumps(report,sort_keys=True,indent=2))
