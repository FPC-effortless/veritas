"""Paired constructed mechanism experiments. All policies train from episode feedback."""
import concurrent.futures
import itertools
import json
import resource
import math
import os
import random
import statistics
import time
import tracemalloc
from collections import Counter
from pathlib import Path

mean = statistics.mean


def controls(r):
    scores = [[], [], [], [], []]
    for _ in range(200):
        target = r.choice((-1, 1))
        xs = [r.gauss(target, 1.7) for _ in range(6)]
        for arm in range(5):
            state = 0
            for step, x in enumerate(xs, 1):
                state += x
                value = (x if arm == 0 else state)
                threshold = (0, 2, 2, float("inf"),2)[arm]
                # Trinary discards analog amplitude before integration.
                if arm in (1,3,4):
                    value = sum((int(y > .5) - int(y < -.5) if arm == 1 else (1 if y >= 0 else -1)) for y in xs[:step])
                if abs(value) >= threshold or step == len(xs):
                    scores[arm].append(((value >= 0) == (target > 0), step))
                    break
    return {name: [mean(x) for x in zip(*rows)] for name, rows in zip(
        ('binary', 'trinary', 'continuous', 'binary_fixed_six','binary_same_threshold'), scores)}


def decay(r):
    scores = {}
    episodes = [(r.choice((-1, 1)), [r.uniform(-1, 1) for _ in range(48)]) for _ in range(150)]
    for adaptive, complement in itertools.product((False, True), repeat=2):
        for lag in (4, 16, 48):
            hits = []
            for bit, noise in episodes:
                state = float(bit)
                slow = bit * .2
                for x in noise[:lag]:
                    alpha = .97 if adaptive and abs(x) < .8 else .75
                    state = alpha * state + (1-alpha)*x
                    slow = .98*slow + .02*x
                hits.append((state + complement*slow)*bit > 0)
            scores[f'{int(adaptive)}{int(complement)}_lag{lag}'] = mean(hits)
    return scores


def update_record(records, key, proposal, accepted):
    if accepted and key not in records:
        from pilot import execute
        records[key] = execute((None,proposal),((0,1),))[0]


def correct(records, key, proposal, revision, accepted):
    from pilot import execute
    previous = records.get(key)
    if accepted and (previous is None or revision > previous[0]):
        value = execute((None,proposal),((0,1),))[0]
        records[key] = (revision,value)


def repairs(r):
    goals = r.sample(range(16),16)
    changed = set(r.sample(range(16),8))
    revised = goals.copy()
    for key in changed:
        revised[key] = (goals[key] + r.randrange(1,16))%16
    stream = []
    for key in changed:
        stream.extend([(key,revised[key],1,True),(key,goals[key],0,True),
                       (key,(revised[key]+1)%16,2,False)])
    r.shuffle(stream)
    result = {}
    for name in ('versioned','unversioned','frozen'):
        records = {k:(0,v) for k,v in enumerate(goals)}
        for key,value,revision,accepted in stream:
            if name == 'versioned':
                correct(records,key,value,revision,accepted)
            elif name == 'unversioned' and accepted:
                records[key] = (revision,value)
        result[name+'_repair'] = mean(records[k][1] == revised[k] for k in changed)
        result[name+'_unaffected'] = mean(records[k][1] == revised[k] for k in range(16) if k not in changed)
    return result


def plasticity(r):
    # Two procedural cycles share an aliased synaptic bank. Exact keys retain context.
    cycles = [r.sample(range(i, i+8), 8) for i in (0, 8)]
    curriculum = []
    for cycle in cycles:
        for i in range(48):
            key, target = cycle[i%8], cycle[(i+1)%8]
            proposal = target if r.random() > .2 else r.randrange(16)
            curriculum.append((key, target, proposal))
    result = {}
    # Compute every candidate update on the same stream once. Readout selects
    # the visible bank. This matches executed work across counterfactual views.
    banks = {name:[[0.]*16 for _ in range(8)] for name in ('frozen','hebbian','modulated')}
    import neuraxon2 as nx
    random.seed(r.getrandbits(32))
    params = nx.NetworkParameters()
    synapses = {}
    last_touch = {}
    verified, unchecked, first, noisy = {}, {}, {}, {}
    arms = (*banks, 'verified', 'exact_unchecked','unchecked_first','noisy_verified')
    cursors = {arm:[] for arm in arms}
    def predict(arm, key):
        row = banks.get(arm,banks['modulated'])[key%8]
        fallback = max(range(16),key=row.__getitem__)
        if arm == 'noisy_verified':
            return noisy.get(key,fallback)
        if arm == 'verified':
            return verified.get(key,fallback)
        if arm == 'unchecked_first':
            return first.get(key,fallback)
        if arm == 'exact_unchecked':
            return unchecked.get(key,fallback)
        return fallback
    def assess(arm, cycle, cursor):
        hits = []
        for j in range(1,17):
            cursor = predict(arm,cursor)
            hits.append(cursor == cycle[j%8])
        return mean(hits)
    for index,(key,target,proposal) in enumerate(curriculum):
        reward = 1 if proposal == target else -1
        banks['hebbian'][key%8][proposal] += 1
        edge = (key%8,proposal)
        if edge not in synapses:
            synapses[edge] = nx.Synapse(*edge,0,params)
        synapse = synapses[edge]
        if edge in last_touch:
            synapse.eligibility *= params.agmp_lambda_e**(index-last_touch[edge]-1)
        synapse.update_eligibility(1,1,params)
        last_touch[edge] = index
        banks['modulated'][key%8][proposal] += reward*synapse.eligibility
        update_record(verified,key,proposal,reward > 0)
        update_record(noisy,key,proposal,(reward > 0) != (r.random() < .1))
        update_record(first,key,proposal,True)
        unchecked[key] = proposal
        if index in (47,95):
            for arm in arms:
                cursors[arm].append(predict(arm,key))
                if index == 47:
                    result[f'{arm}_before'] = assess(arm,cycles[0],cursors[arm][0])
    for delay in range(65):
        if delay in (0,8,64):
            for arm in arms:
                for name,cycle,cursor in zip(('old','new'),cycles,cursors[arm]):
                    result[f'{arm}_{name}_{delay}'] = assess(arm,cycle,cursor)
        # No external input. Labile synapses discretely leak during silent time.
        for bank in banks.values():
            for row in bank:
                for i,w in enumerate(row):
                    row[i] = math.trunc(.98*w*16)/16
    result['bank_scalars'] = sum(map(len,banks['modulated']))
    result['verified_records'] = len(verified)
    result['unchecked_records'] = len(unchecked)
    result.update(repairs(r))
    return result


def delayed(r):
    result = {}
    for lag in (0, 4, 16):
        trials = [(r.randrange(8), r.randrange(2), [r.randrange(8) for _ in range(lag)])
                  for _ in range(600)]
        goals = [r.randrange(2) for _ in range(8)]
        for name, retention in [('immediate', 0), ('trace', .9)]:
            weights = [[0.,0.] for _ in goals]
            for cue, action, intervening in trials:
                trace = [0.]*8
                for x in [cue, *intervening]:
                    trace = [v*retention for v in trace]
                    trace[x] += 1
                reward = 1 if action == goals[cue] else -1
                for i, strength in enumerate(trace):
                    weights[i][action] += strength*reward
            result[f'{name}_{lag}'] = mean((w[1] > w[0]) == goal for w, goal in zip(weights, goals))
    return result


def routing(r):
    scores = {k:[] for k in (1,2,4,8)}
    for _ in range(300):
        target = r.choice((-1,1))
        packets = sorted([(r.gauss(1,1),target)]+[(r.gauss(0,1),r.choice((-1,1))) for _ in range(7)], reverse=False, key=lambda p:-p[0])
        for k in scores:
            scores[k].append((sum(v for _,v in packets[:k]) >= 0) == (target > 0))
    return {str(k):mean(v) for k,v in scores.items()}


def compose(r):
    funcs = [lambda x:(x+1)%7, lambda x:(2*x)%7, lambda x:(6-x)%7]
    lex = r.sample(['da','ki','mu'],3)
    learned = {}
    for word, f in zip(lex,funcs):
        examples = [(x,f(x)) for x in r.sample(range(7),3)]
        learned[word] = next(g for g in funcs if all(g(x)==y for x,y in examples))
    # Exact sequence lookup sees primitives and pairs, never triples.
    table = {}
    scores = []
    baseline = []
    for length in (1,2,3):
        for seq in itertools.product(range(3), repeat=length):
            for x in range(7):
                pred = target = x
                for i in seq:
                    target = funcs[i](target)
                    pred = learned[lex[i]](pred)
                if length < 3:
                    table[seq,x] = target
                else:
                    scores.append(pred == target)
                    baseline.append(table.get((seq,x),x) == target)
    return {'composition':mean(scores),'lookup_identity_backoff':mean(baseline)}


def grounding(r):
    words = r.sample(['lom','rek','pav','zut','fig','nel'],6)
    counts = {word:Counter() for word in words}
    for _ in range(300):
        a,b = r.randrange(3),r.randrange(3)
        if (a+b)%3 == 0:
            continue
        scene = [(a,b)] + [(r.randrange(3), r.randrange(3)) for _ in range(3)]
        action = r.randrange(4)
        if scene[action] == (a,b):
            for word in (words[a],words[3+b]):
                counts[word].update(enumerate(scene[action]))
    def select(command, scene):
        return max(range(len(scene)), key=lambda j:sum(counts[w][(axis,v)] for w in command for axis,v in enumerate(scene[j])))
    hits = []
    chance = []
    for _ in range(150):
        a = r.randrange(3)
        target = (a,(-a)%3)
        scene = r.sample([p for p in itertools.product(range(3),repeat=2) if p!=target],3)
        scene.insert(r.randrange(4),target)
        hits.append(scene[select([words[a],words[3+target[1]]],scene)] == target)
        chance.append(scene[0]==target)
    return {'grounded':mean(hits),'position_baseline':mean(chance)}


def transform(grid, rule):
    if rule == 0:
        return tuple(zip(*grid[::-1]))
    if rule == 1:
        return tuple(row[::-1] for row in grid)
    return tuple(tuple((x+1)%3 for x in row) for row in grid)


def apply(grid, rule):
    for op in rule:
        grid = transform(grid,op)
    return grid


def grids(r):
    result = {}
    candidates = list(itertools.product(range(3),repeat=2))
    for depth in (2,3):
        hits = []
        base = []
        for _ in range(80):
            rule = r.choices(range(3),k=depth)
            cases = [tuple(tuple(r.randrange(3) for _ in range(4)) for _ in range(4)) for _ in range(4)]
            found = next((c for c in candidates if all(apply(g,c)==apply(g,rule) for g in cases[:3])), ())
            target = apply(cases[3],rule)
            hits.append(apply(cases[3],found)==target)
            base.append(cases[3]==target)
        result[f'search_{depth}'] = mean(hits)
        result[f'identity_{depth}'] = mean(base)
    # Interactive grid world: controls have a hidden, per-world action mapping.
    # Explore on one marker, then plan for fresh start/goal coordinates on a torus.
    moves = ((0,1),(1,0),(0,-1),(-1,0))
    mapping_scores = []
    fixed_scores = []
    costs = []
    for _ in range(80):
        mapping = r.sample(moves,4)
        pos = (0,0)
        learned = []
        for action in range(4):
            nxt = tuple((p+d)%5 for p,d in zip(pos,mapping[action]))
            learned.append(tuple((q-p+2)%5-2 for p,q in zip(pos,nxt)))
            pos = nxt
        start = (r.randrange(5),r.randrange(5))
        goal = r.choice([q for q in itertools.product(range(5),repeat=2) if q != start])
        for model, scores in ((learned,mapping_scores),(moves,fixed_scores)):
            pos = start
            count = 0
            for axis in (0,1):
                delta = (goal[axis]-start[axis]+2)%5-2
                direction = tuple((1 if delta>0 else -1) if i==axis else 0 for i in (0,1))
                for _ in range(abs(delta)):
                    pos = tuple((p+d)%5 for p,d in zip(pos,mapping[model.index(direction)]))
                    count += 1
            scores.append(pos == goal)
            if model is learned:
                costs.append(count+4)
    result.update(interactive_probe=mean(mapping_scores),interactive_fixed=mean(fixed_scores),
                  interactive_actions=mean(costs))
    return result


def batch(payload):
    candidates = list(itertools.product(range(3), repeat=2))
    outputs = []
    for demos, query in payload:
        rule = next(c for c in candidates if all(apply(x,c) == y for x,y in demos))
        outputs.append(apply(query,rule))
    return outputs


def indexed_batch(payload):
    outputs = []
    candidates = list(itertools.product(range(3), repeat=2))
    for demos, query in payload:
        # Cache each first transform once per demonstration. Eliminate rules
        # on the first mismatch, stop checking once a unique rule survives.
        viable = candidates
        for grid, expected in demos:
            prefixes = {op:transform(grid,op) for op in {c[0] for c in viable}}
            viable = [c for c in viable if transform(prefixes[c[0]],c[1]) == expected]
            if len(viable) == 1:
                break
        outputs.append(apply(query,viable[0]))
    return outputs


def throughput(r):
    payload = []
    targets = []
    for _ in range(128):
        grids = [tuple(tuple(r.randrange(3) for _ in range(8)) for _ in range(8)) for _ in range(4)]
        rule = r.choices(range(3), k=2)
        payload.append(([(g,apply(g,rule)) for g in grids[:3]], grids[3]))
        targets.append(apply(grids[3],rule))
    reference = batch(payload)
    result = {}
    for workers in (1,2,4):
        tracemalloc.start()
        start = time.perf_counter()
        if workers == 1:
            output = batch(payload)
        else:
            with concurrent.futures.ProcessPoolExecutor(workers) as pool:
                output = list(itertools.chain.from_iterable(pool.map(batch,[payload[i:i+32] for i in range(0,len(payload),32)])))
        seconds = time.perf_counter()-start
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        assert output == reference
        result[str(workers)] = [seconds, len(payload)/seconds, peak, mean(x == y for x,y in zip(output, targets)),
                                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                                resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss]
    for name,solver in [('serial',batch),('cached',indexed_batch)]:
        times = []
        for episode, target in zip(payload,targets):
            start = time.perf_counter_ns()
            pred = solver([episode])[0]
            times.append((time.perf_counter_ns()-start)/1000)
            assert pred == target
        result[name+'_microseconds'] = [statistics.median(times),sorted(times)[121]]
    return result


def proof():
    # Exhaustive inductive step over Q={-2,-1,0,1,2}, ternary memory cells
    # (empty,-1,+1), two addresses and all combinations of protection bits.
    checked = 0
    for s,x,a in itertools.product(range(-2,3),range(-2,3),range(5)):
        successor = (a*s + (4-a)*x)//4
        assert -2 <= successor <= 2
        checked += 1
    transitions = 0
    for cells,key,value,ok in itertools.product(itertools.product((-1,0,1),repeat=2),
            range(2),(-1,1),(False,True)):
        records = {i:v for i,v in enumerate(cells) if v}
        old = records.copy()
        update_record(records, key, value, ok)
        assert all(records[i] == v for i,v in old.items())
        assert records == (old | {key:value} if ok and key not in old else old)
        transitions += 1
    repair_steps = 0
    for key,rev,old_rev,accepted,value in itertools.product(range(2),range(3),range(3),(False,True),(-1,1)):
        records = {0:(old_rev,-1),1:(old_rev,1)}
        old = records.copy()
        correct(records,key,value,rev,accepted)
        assert records[1-key] == old[1-key]
        assert records[key] == ((rev,value) if accepted and rev > old_rev else old[key])
        repair_steps += 1
    import ctypes
    import ctypes.util
    lib = ctypes.CDLL(ctypes.util.find_library('z3') or 'libz3.so.4')
    lib.Z3_mk_config.restype = ctypes.c_void_p
    lib.Z3_mk_context.argtypes = [ctypes.c_void_p]
    lib.Z3_mk_context.restype = ctypes.c_void_p
    lib.Z3_eval_smtlib2_string.argtypes = [ctypes.c_void_p,ctypes.c_char_p]
    lib.Z3_eval_smtlib2_string.restype = ctypes.c_char_p
    cfg = lib.Z3_mk_config()
    ctx = lib.Z3_mk_context(cfg)
    answers = lib.Z3_eval_smtlib2_string(ctx,Path('invariants.smt2').read_bytes()).decode().split()
    assert answers == ['unsat','unsat']
    return {'decay_transitions':checked,'memory_transitions':transitions,'repair_transitions':repair_steps,'smt_counterexample_queries':answers}


if __name__ == '__main__':
    dest = Path(os.environ.get('TRAINLAB_OUTPUT_DIR','.'))
    seeds = json.loads(Path('seeds.json').read_text())
    experiments = [controls,decay,plasticity,delayed,routing,compose,grounding,grids,throughput]
    rows = {f'NX-{i:03}':{str(s):fn(random.Random(s)) for s in seeds}
            for i,fn in enumerate(experiments,1)}
    import native
    for seed in seeds:
        for name,fn in [('NX-002',native.decay),('NX-005',native.routing),('NX-006',native.skills),('NX-007',native.language)]:
            rows[name][str(seed)].update(fn(seed))
    rows['NX-010'] = proof()
    from trainlab.runner import digest
    from trainlab.research_adequacy import recipe_identity
    config = json.loads(Path('recipe.json').read_text())
    pins = {name:digest(Path(name)) for name in config['inputs']}
    obs = {'seed_count':len(rows['NX-003']), 'bank_scalars':next(iter(rows['NX-003'].values()))['bank_scalars'], 'updates':min(v['cdl_updates'] for v in rows['NX-007'].values()),'families':len(rows)}
    receipt = dict(schema='trainlab.execution-adequacy-observations.v1',recipe_sha256=recipe_identity(config),inputs=pins,producer=dict(file='suite.py',sha256=pins['suite.py']),observations=obs)
    (dest/'observations.json').write_text(json.dumps(receipt))
    (dest/'results.json').write_text(json.dumps(rows,indent=2)+'\n')
    (dest/'metrics.json').write_text(json.dumps({'experiments':len(rows)}))
