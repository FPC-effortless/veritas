import json
import os
import random
import statistics
import time
import tracemalloc
from pathlib import Path
from trainlab.runner import digest
from trainlab.research_adequacy import recipe_identity
from verification import Confidence, capacity, encounter, evaluate, recovery, crosscheck
from procedures import primitive, depth, hierarchy, language, reasoning, compile_benchmark, teaching
from integrated import study

def costs(seed):
    rng = random.Random(seed+113)
    model = Confidence(seed+100000)
    memory = {}
    def call(key,latent):
        proposal,probes = encounter(rng,latent,False)
        if model.accept(proposal,probes):
            memory[key] = proposal
        return memory.get(key)
    requests = [(i%16,i%8) for i in range(256)]
    ns = []
    for key,latent in requests:
        start = time.perf_counter_ns()
        call(key,latent)
        ns.append(time.perf_counter_ns()-start)
    tracemalloc.start()
    for key,latent in requests:
        call(key,latent)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    return dict(single_p50_ns=statistics.median(ns),single_p95_ns=sorted(ns)[242],
                transient_python_peak_bytes=peak,probes_per_proposal=3)

def main():
    seeds = json.loads(Path('seeds.json').read_text())
    rows = {}
    for s in seeds:
        rows[s] = {'011':{'independent':evaluate(s),'common':evaluate(s,True),'cost':costs(s),'followup':crosscheck(s)},
            '012':capacity(s),'013':recovery(s),'014':primitive(s),'015':depth(s),
            '016':hierarchy(s),'017':language(s) | {'teaching_'+k:v for k,v in teaching(s).items()},'018':reasoning(s),'019':compile_benchmark(s),
            '020':{'from_scratch':study(s),'upstream_alias_transfer':study(s,trained=True),'fresh_alias_transfer':study(s,trained=True,load_checkpoint=False)}}
    output = Path(os.environ['TRAINLAB_OUTPUT_DIR'])
    (output/'results.json').write_text(json.dumps(rows,separators=(',',':'))+'\n')
    config = json.loads(Path('recipe.json').read_text())
    pins = {k:digest(Path(k)) for k in config['inputs']}
    observations = dict(seed_count=len(rows),families=min(map(len,rows.values())),
        confidence_bins=min(r['011']['independent']['calibration']['bins'] for r in rows.values()),
        calibration_encounters=min(r['011']['independent']['calibration']['encounters'] for r in rows.values()))
    receipt = dict(schema='trainlab.execution-adequacy-observations.v1',recipe_sha256=recipe_identity(config),
           inputs=pins,producer=dict(file='suite.py',sha256=pins['suite.py']),observations=observations)
    (output/'observations.json').write_text(json.dumps(receipt))
    (output/'metrics.json').write_text(json.dumps({'experiments':observations['families']}))
if __name__=='__main__':
    main()
