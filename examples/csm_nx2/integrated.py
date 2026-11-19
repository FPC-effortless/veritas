"""One train/verify/compile/execute path with pinned upstream components."""
import random
import time
import statistics
import numpy as np
import neuraxon2 as nx
import pilot
import reader
from id001.routing import IdentityRouter
from procedures import IDENTITY, compose, world
from verification import Confidence


def assemble(permutation,swap):
    order = list(IDENTITY)
    code = []
    for dest,source in enumerate(permutation):
        pos = order.index(source)
        if pos!=dest:
            code.extend(pilot.bind(swap,(dest,pos,len(order))))
            order[dest],order[pos] = order[pos],order[dest]
    return tuple(code)


def study(seed, trained=False, load_checkpoint=True):
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    ops = world(seed)
    verifier = Confidence(seed+100000)
    random.seed(seed)
    params = nx.NetworkParameters()
    router = IdentityRouter(16,4,identity_energy_budget=32,seed=seed)
    assoc = reader.Reader(seed,True)
    if trained:
        if load_checkpoint:
            with np.load('reader-11.npz') as checkpoint:
                for name in ('E','a','b'):
                    getattr(assoc,name)[:] = checkpoint[name]
        pair_ids = rng.sample(range(8),4)
        tokens = [reader.WORDS[2*i+j] for i in pair_ids for j in range(2)]
    else:
        tokens = rng.sample(reader.WORDS,8)
    def descriptor(word):
        phrase = reader.encode('entry '+word)
        return assoc.forward(np.array([phrase]))[0][0]
    # Hebbian feature-to-module associations receive context feedback after three blank ticks.
    weights = np.zeros((32,16))
    immediate = np.zeros_like(weights)
    synapse = nx.Synapse(0,1,0,params)
    for _ in range(8):
        for index,token in enumerate(tokens):
            if trained and index%2:
                continue
            feature = descriptor(token)
            synapse.eligibility = 0
            synapse.update_eligibility(1,1,params)
            distractor = descriptor(rng.choice(tokens))
            for _ in range(3):
                synapse.update_eligibility(0,0,params)
            reward_vector = router.identity_embeddings[index//2]
            weights += np.outer(synapse.eligibility*feature+distractor,reward_vector)
            immediate += np.outer(distractor,reward_vector)
    # Native CDL induction from a demonstration; verified swap compiles all permutations.
    swap = pilot.learn_trace(((8,3,None),(8,3,8),(3,3,8),(3,8,8),(3,8,None)))
    assert pilot.admit(swap)
    encounters = []
    for _ in range(8):
        for module,op in enumerate(ops):
            before = tuple(rng.sample(range(64),len(IDENTITY)))
            def observe():
                permutation = op if rng.random()<.8 else rng.choice(ops)
                after = compose(before,permutation)
                return tuple(before.index(v) for v in after)
            encounters.append((module,observe(),tuple(observe() for _ in range(3))))
    requests = []
    for _ in range(96):
        cmd = rng.choices(range(1,8,2) if trained else range(8),k=rng.choice((1,3,8)))
        x = tuple(rng.sample(range(64),6))
        y = x
        for t in cmd:
            y = compose(y,ops[t//2])
        requests.append(([tokens[t] for t in cmd],x,y))
    result = {}
    for arm in ('full','unchecked','no_trace','flat_execution','known_route'):
        memory = {}
        for module,p,probes in encounters:
            if module not in memory and (arm=='unchecked' or verifier.accept(p,probes)):
                memory[module] = (p,assemble(p,swap))
        correct,ns = [],[]
        for command,x,y in requests:
            start = time.perf_counter_ns()
            state = x
            for word in command:
                q = descriptor(word) @ (immediate if arm=='no_trace' else weights)
                _,route,_ = router.forward(q)
                if arm=='known_route':
                    route = tokens.index(word)//2
                if route not in memory:
                    state = None
                    break
                perm,code = memory[route]
                state = compose(state,perm) if arm=='flat_execution' else pilot.execute((*state,None),code)[:-1]
            ns.append(time.perf_counter_ns()-start)
            correct.append(state==y)
        result[arm] = dict(accuracy=statistics.mean(correct),single_ns=statistics.median(ns),
                           coverage=len(memory)/4)
    return result
