"""Paired, seed-level summaries for the constructed panel."""
import argparse
import json
import random
import statistics
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('results',type=Path)
parser.add_argument('output',type=Path)
args = parser.parse_args()
panel = json.loads(args.results.read_text())
summary = {}
for experiment,rows in panel.items():
    if experiment == 'NX-010':
        summary[experiment] = rows
        continue
    summary[experiment] = {}
    for key in next(iter(rows.values())):
        values = [row[key] for row in rows.values()]
        columns = zip(*values) if isinstance(values[0],list) else [values]
        summary[experiment][key] = [dict(mean=statistics.mean(v),sd=statistics.stdev(v)) for v in columns]
claims = [
    ('NX-001','trinary','binary_same_threshold',0),
    ('NX-002','native_11_lag16','native_00_lag16',None),
    ('NX-003','verified_old_64','unchecked_first_old_64',None),
    ('NX-003','verified_new_64','unchecked_first_new_64',None),
    ('NX-003','verified_old_64','noisy_verified_old_64',None),
    ('NX-003','versioned_repair','unversioned_repair',None),
    ('NX-004','trace_4','immediate_4',None),
    ('NX-005','tac_1','tac_8',None),
    ('NX-007','grounded','position_baseline',None),
    ('NX-008','search_3','identity_3',None)]
paired = {}
for exp,a,b,column in claims:
    diffs = []
    for row in panel[exp].values():
        x,y = row[a],row[b]
        diffs.append(x-y if column is None else x[column]-y[column])
    rng = random.Random(719)
    draws = sorted(statistics.mean(rng.choices(diffs,k=len(diffs))) for _ in range(5000))
    paired[f'{exp} {a} minus {b}'] = dict(mean=statistics.mean(diffs),percentile95=[draws[124],draws[4874]])
args.output.write_text(json.dumps(dict(by_family=summary,paired_seed_differences=paired),indent=2)+'\n')
