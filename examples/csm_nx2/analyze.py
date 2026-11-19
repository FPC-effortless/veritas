"""Aggregate execution data by paired environment seed."""
import argparse
import json
import random
import statistics as st
from pathlib import Path


def analyze(panel):
    rows = list(panel.values())
    def column(fn):
        return [fn(r) for r in rows]
    def avg(fn):
        return st.mean(column(fn))
    def difference(fn):
        values = column(fn)
        rng = random.Random(91233)
        draws = sorted(st.mean(rng.choices(values,k=len(values))) for _ in range(5000))
        return dict(mean=st.mean(values),interval95=[draws[124],draws[4874]])
    result = {'seeds':len(rows)}
    gates = {}
    for name in ('independent','common'):
        gates[name] = {}
        for arm in ('learned','two_agree','always','never','blind_first'):
            cells = [r['011'][name][arm] for r in rows]
            total = lambda k:sum(v[k] for v in cells)
            writes = total('writes')
            precision = total('correct_writes')/writes if writes else None
            coverage,old,new = [st.mean(v[k] for v in cells) for k in ('coverage','old','new')]
            recovered = [t for v in cells for t in v['recovery_ticks']]
            gates[name][arm] = dict(precision=precision,writes=writes,errors=writes-total('correct_writes'),
                write_fraction=writes/total('opportunities'),coverage=coverage,old=old,new=new,
                shifted=st.mean(v['shifted'] for v in cells),
                online=total('deployed_correct')/total('opportunities'),
                median_resolved_ticks=st.median(recovered) if recovered else None,
                resolved=len(recovered),unresolved=total('unresolved'),
                meets_rule=bool(precision is not None and precision>=.95 and coverage>=.75 and min(old,new)>=.85))
    result['011']=gates
    costs=rows[0]['011']['cost']
    result['011_cost']={k:avg(lambda r:r['011']['cost'][k]) for k in costs}
    if 'followup' in rows[0]['011']:
        follow = {}
        for scenario in ('independent','shared'):
            cells=[r['011']['followup'][scenario] for r in rows]
            follow[scenario]=dict(precision=sum(c['correct'] for c in cells)/sum(c['writes'] for c in cells),
                    coverage=st.mean(c['coverage'] for c in cells), accuracy=st.mean(c['accuracy'] for c in cells))
        result['011_intervention']=follow
    result['012']={k:avg(lambda r:r['012'][k]) for k in rows[0]['012']}
    result['013']={}
    for arm in rows[0]['013']:
        result['013'][arm]={}
        for k in ('first','sustained'):
            ticks = [t for r in rows for t in r['013'][arm][k]]
            observed=[t for t in ticks if t<=16]
            result['013'][arm][k]=dict(resolved=len(observed)/len(ticks),median_observed=st.median(observed) if observed else None,
                restricted_mean_ticks=st.mean(min(16,t) for t in ticks),censored=len(ticks)-len(observed))
    for name in ('014','016','017'):
        result[name]={k:avg(lambda r:r[name][k]) for k in rows[0][name]}
    result['015']={d:[avg(lambda r:r['015'][d][i]) for i in range(3)] for d in rows[0]['015']}
    result['018']={a:{k:avg(lambda r:r['018'][a][k]) for k in rows[0]['018'][a]} for a in ('primitive','mined','random')}
    result['018']['unique_goals_per_seed']=avg(lambda r:r['018']['unique_heldout_goals'])
    perf={}
    for a in ('compiled','interpreter','vectorized'):
        perf[a]={k:avg(lambda r:r['019'][a][k]) for k in rows[0]['019'][a]}
    for k in ('compile_ns','acquisition_ns'):
        perf[k]=avg(lambda r:r['019'][k])
    # Library has 16 programs sharing acquisition. Charge each program 1/16 of both one-off costs.
    perf['weighted_us_per_program']={a:avg(lambda r:(r['019']['acquisition_ns']/16+
        (r['019']['compile_ns']/16 if a=='compiled' else 0)+12*r['019'][a]['single_p50_ns'])/1000)
        for a in ('compiled','interpreter')}
    perf['break_even_reuses_per_program']=st.median(
        r['019']['compile_ns']/16/(r['019']['interpreter']['single_p50_ns']-r['019']['compiled']['single_p50_ns'])
        for r in rows if r['019']['interpreter']['single_p50_ns']>r['019']['compiled']['single_p50_ns'])
    result['019']=perf
    runs=rows[0]['020']
    if 'full' in runs:
        runs={'from_scratch':runs}
    result['020']={}
    for mode,arms in runs.items():
        result['020'][mode]={a:{k:avg(lambda r:r['020'].get(mode,r['020'])[a][k]) for k in arms[a]} for a in arms}
    result['paired_seed_differences']={
        'independent_old_learned_minus_always':difference(lambda r:r['011']['independent']['learned']['old']-r['011']['independent']['always']['old']),
        'independent_new_learned_minus_always':difference(lambda r:r['011']['independent']['learned']['new']-r['011']['independent']['always']['new']),
        'mined_minus_random_planning':difference(lambda r:r['018']['mined']['success']-r['018']['random']['success'])}
    if 'fresh_alias_transfer' in runs:
        result['paired_seed_differences']['checkpoint_minus_fresh_held_alias'] = difference(
            lambda r:r['020']['upstream_alias_transfer']['full']['accuracy']-r['020']['fresh_alias_transfer']['full']['accuracy'])
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('raw',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    args.output.write_text(json.dumps(analyze(json.loads(args.raw.read_text())),indent=2)+'\n')
