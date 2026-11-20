import json
import random
import statistics
import sys
from pathlib import Path

def summarize(rows):
    result={}
    for topology in ('downstream','upstream'):
        cells=[v[topology] for v in rows.values()]
        panel={}
        for arm in cells[0]:
            vals=[c[arm] for c in cells]
            avg=lambda k:statistics.mean(v[k] for v in vals)
            sensitivity=avg('true_positive')/8
            specificity=1-avg('false_positive')/8
            panel[arm]=dict(accuracy=avg('accuracy'),coverage=avg('coverage'),
                precision=sum(v['correct'] for v in vals)/sum(v['writes'] for v in vals),
                sensitivity=sensitivity,specificity=specificity,balanced=(sensitivity+specificity)/2,
                deployment_outcomes=avg('checks'),audit_outcomes=avg('audit_outcomes'),
                fault_overlap=avg('biased_dependent_keys'))
        for baseline in ('veto','repair'):
            diffs=[v['active']['accuracy']-v[baseline]['accuracy'] for v in cells]
            rng=random.Random(881)
            boot=sorted(statistics.mean(rng.choices(diffs,k=len(diffs))) for _ in range(5000))
            panel['gain_over_'+baseline]=[statistics.mean(diffs),boot[124],boot[4874]]
        result[topology]=panel
    return dict(seeds=len(rows),panels=result)

if __name__=='__main__':
    print(json.dumps(summarize(json.loads(Path(sys.argv[1]).read_text())),indent=2))
