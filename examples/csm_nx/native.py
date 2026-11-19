"""Direct interventions in the pinned Neuraxon and CDL public sources."""
import random
from statistics import mean

import neuraxon2 as nx
import pilot
import reader


def decay(seed):
    rng = random.Random(seed)
    episodes = [(rng.choice((-1,1)),[rng.uniform(-.4,.4) for _ in range(16)]) for _ in range(60)]
    scores = {}
    for adaptive in (False,True):
        for complement in (False,True):
            hits = []
            for index,(bit,noise) in enumerate(episodes):
                random.seed(seed*100+index)
                p = nx.NetworkParameters(dsn_enabled=adaptive,ctsn_enabled=complement,spontaneous_firing_rate=0)
                cell = nx.Neuraxon(0,nx.NeuronType.HIDDEN,p)
                for value in [bit,*noise]:
                    cell.update({},[],value,0,{},1)
                hits.append(cell.state_tilde*bit > 0)
            scores[f'native_{int(adaptive)}{int(complement)}_lag16'] = mean(hits)
    return scores


def skills(seed):
    rng = random.Random(seed)
    a,b = rng.sample(range(100),2)
    prog = pilot.learn_trace(((a,b,None),(a,b,a),(b,b,a),(b,a,a),(b,a,None)))
    assert pilot.admit(prog) and not pilot.admit(prog[:-1])
    wins = []
    for _ in range(64):
        x,y,z = rng.sample(range(1000),3)
        code = pilot.bind(prog,(0,1,3)) + pilot.bind(prog,(1,2,3))
        wins.append(pilot.execute((x,y,z,None),code) == (y,z,x,None))
    return {'cdl_composed_swaps':mean(wins)}


def language(seed):
    model = reader.Reader(seed,True)
    for step in range(1,33):
        model.step(reader.data(seed*1000+step,8,'train'),step)
    scores = reader.scores(model,reader.data(seed*1000+800,96,'held'))['sum']
    return {'cdl_held_syntax':scores['route']/scores['n'], 'cdl_updates':step}


def routing(seed):
    from id001.routing import IdentityRouter
    import numpy as np
    rng = np.random.default_rng(seed)
    router = IdentityRouter(16,8,identity_energy_budget=16,seed=seed)
    scores = {1:[],2:[],4:[],8:[]}
    for _ in range(200):
        target = rng.integers(8)
        query = router.identity_embeddings[target] + rng.normal(0,.35,16)
        _,_,weights = router.forward(query)
        bit = rng.choice((-1,1))
        messages = rng.choice((-1,1),8)
        messages[target] = bit
        for k in scores:
            active = np.argsort(-weights)[:k]
            scores[k].append(bool((messages[active].sum() >= 0) == (bit > 0)))
    return {f'tac_{k}':mean(x) for k,x in scores.items()}
