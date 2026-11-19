"""Predictive admission. Only the evaluator has access to latent values."""
import math
import random
import time
from collections import Counter, defaultdict

ACTIONS = 8
KEYS = 16


def reading(rng, target, p):
    if rng.random() < p:
        return target
    return (target + rng.randrange(1, ACTIONS)) % ACTIONS


def encounter(rng, target, common):
    perceived = (target + 1) % ACTIONS if common else target
    proposal = reading(rng, perceived, .68)
    probes = tuple(reading(rng, perceived, .90) for _ in range(3))
    return proposal, probes


class Confidence:
    def __init__(self, seed):
        rng = random.Random(seed)
        self.counts = [[1, 2] for _ in range(4)]
        for _ in range(1200):
            latent = rng.randrange(ACTIONS)
            proposal, probes = encounter(rng, latent, False)
            future = reading(rng, latent, .90)
            self.observe(proposal, probes, future)

    def observe(self, proposal, probes, future_observation):
        row = self.counts[probes.count(proposal)]
        row[0] += proposal == future_observation
        row[1] += 1

    def accept(self, proposal, probes):
        yes, total = self.counts[probes.count(proposal)]
        return yes / total >= .75


def stream(seed, stress):
    rng = random.Random(seed)
    targets = [rng.randrange(ACTIONS) for _ in range(KEYS)]
    bad = set(rng.sample(range(KEYS), 4)) if stress else set()
    events = []
    for epoch in range(12):
        if epoch == 6:
            for k in range(4):
                targets[k] = (targets[k] + 1) % ACTIONS
        keys = list(range(8 if epoch < 4 else KEYS))
        rng.shuffle(keys)
        for k in keys:
            proposal, probes = encounter(rng, targets[k], k in bad)
            events.append((epoch,k,proposal,probes,targets[k]))
    return events, targets


def evaluate(seed, stress=False):
    model = Confidence(seed + 100000)
    events, targets = stream(seed, stress)
    result = {}
    for arm in ('learned','always','never','two_agree','blind_first'):
        memory = [None] * KEYS
        counts = Counter()
        bad_since = {}
        resolved = []
        latencies = []
        for t,(epoch,key,proposal,probes,gold) in enumerate(events):
            start = time.perf_counter_ns()
            if arm == 'learned':
                accepted = model.accept(proposal,probes)
            elif arm == 'two_agree':
                accepted = probes.count(proposal) >= 2
            elif arm == 'blind_first':
                accepted = memory[key] is None
            else:
                accepted = arm == 'always'
            if accepted:
                memory[key] = proposal
            answer = memory[key]
            latencies.append(time.perf_counter_ns()-start)
            counts['writes'] += accepted
            counts['correct_writes'] += accepted and proposal == gold
            counts['deployed_correct'] += answer == gold
            if accepted and proposal != gold and key not in bad_since:
                bad_since[key] = t
            if answer == gold and key in bad_since:
                resolved.append(t-bad_since.pop(key))
        result[arm] = dict(counts, opportunities=len(events),
            coverage=sum(x is not None for x in memory)/KEYS,
            old=sum(memory[k]==targets[k] for k in range(4,8))/4,
            new=sum(memory[k]==targets[k] for k in range(8,16))/8,
            shifted=sum(memory[k]==targets[k] for k in range(4))/4,
            recovery_ticks=resolved, unresolved=len(bad_since),
            inference_ns=sorted(latencies)[len(latencies)//2])
    result['calibration'] = dict(bins=len(model.counts), encounters=sum(n-2 for _,n in model.counts), counts=model.counts)
    return result


def capacity(seed):
    events, targets = stream(seed,False)
    model = Confidence(seed+100000)
    result = {}
    for rule in ('frozen','hebbian','eligibility','exact','verified'):
        bank = [[0.] * ACTIONS for _ in range(KEYS)]
        trace = [[0.] * ACTIONS for _ in range(KEYS)]
        for epoch,k,p,probes,_ in events:
            row = bank[k]
            if rule == 'hebbian':
                row[p] += 1
            elif rule == 'eligibility':
                for j in range(ACTIONS):
                    trace[k][j] *= .6
                trace[k][p] += 1
                consequence = (2*probes.count(p)/3)-1
                for j in range(ACTIONS):
                    row[j] += trace[k][j]*consequence
            elif rule == 'exact' or (rule == 'verified' and model.accept(p,probes)):
                row[:] = [float(j==p) for j in range(ACTIONS)]
        guess = [max(range(ACTIONS),key=row.__getitem__) if any(row) else None for row in bank]
        result[rule] = sum(v==y for v,y in zip(guess,targets))/KEYS
    return result


def recovery(seed):
    rng = random.Random(seed+98000)
    model = Confidence(seed+100000)
    result = {}
    for mode in ('independent','common'):
        traces = []
        for _ in range(64):
            target = rng.randrange(ACTIONS)
            traces.append([encounter(rng,target,mode=='common' and t<8) for t in range(16)]+[target])
        for policy in ('learned','unconditional','locked'):
            first, lasting = [], []
            for trace in traces:
                target = trace[-1]
                mem = (target+1)%ACTIONS
                hits = []
                for proposal,probes in trace[:-1]:
                    if policy=='unconditional' or (policy=='learned' and model.accept(proposal,probes)):
                        mem = proposal
                    hits.append(mem==target)
                first.append(next((i+1 for i,x in enumerate(hits) if x),17))
                lasting.append(next((i+1 for i in range(16) if all(hits[i:])),17))
            result[mode+'_'+policy] = {'first':first,'sustained':lasting}
    return result


def crosscheck(seed):
    """Follow-up. A different actuation path produces an observable encoded consequence."""
    def emit(rng,value):
        return reading(rng,(3*value+1)%ACTIONS,.90)
    rng = random.Random(seed+51234)
    # The effect model learns calibration from observable cue/action pairs in a nominal simulator.
    # The cue is fallible; during evaluation learner receives only the consequence of its probe.
    effects = [[0]*ACTIONS for _ in range(ACTIONS)]
    for _ in range(1200):
        value = rng.randrange(ACTIONS)
        cue = reading(rng,value,.90)
        effects[cue][emit(rng,value)] += 1
    predicted = [max(range(ACTIONS),key=row.__getitem__) for row in effects]
    gate = Confidence(seed+100000)
    out = {}
    for shared in (False,True):
        events,targets = stream(seed,True)
        memory = [None]*KEYS
        correct = writes = checks = 0
        for _,k,p,probes,latent in events:
            if gate.accept(p,probes):
                checks+=1
                target = probes[0] if shared else latent
                observed = emit(rng,target)
                if predicted[p]==observed:
                    memory[k]=p
                    writes+=1
                    correct+=p==latent
        out['shared' if shared else 'independent'] = dict(correct=correct,writes=writes,
            probes=checks,coverage=sum(v is not None for v in memory)/KEYS,
            accuracy=sum(v==t for v,t in zip(memory,targets))/KEYS)
    return out
