"""Procedures acting on ordered records. The evaluator owns the environment operators."""
import itertools
import random
import statistics
import time
import tracemalloc
from collections import Counter, deque

SIZE = 6
IDENTITY = tuple(range(SIZE))


def compose(left, right):
    return tuple(left[i] for i in right)


def apply_program(state, program, table):
    for token in program:
        state = compose(state,table[token])
    return state


def world(seed):
    rng = random.Random(seed)
    return rng.sample([p for p in itertools.permutations(IDENTITY) if p!=IDENTITY],4)


def infer(examples):
    # Intersect antecedent-slot candidates, then enforce a one-to-one assignment.
    slots = [{i for i in IDENTITY if all(before[i]==after[j] for before,after in examples)}
             for j in IDENTITY]
    return next((p for p in itertools.permutations(IDENTITY)
                 if all(i in allowed for i,allowed in zip(p,slots))),None)


def learn(rng, ops, n):
    learned = []
    for op in ops:
        episodes = []
        for _ in range(n):
            state = tuple(rng.randrange(3) for _ in IDENTITY)
            episodes.append((state,compose(state,op)))
        learned.append(infer(episodes))
    return learned


def primitive(seed):
    ops = world(seed)
    result = {}
    for n in (1,3,8):
        learned = learn(random.Random(seed+231),ops,n)
        result[str(n)] = sum(a==b for a,b in zip(ops,learned))/4
    result['identity'] = sum(p==IDENTITY for p in ops)/4
    rng = random.Random(seed+218)
    axis = rng.randrange(SIZE)
    examples = []
    for _ in range(30):
        x = tuple(rng.sample(range(64),SIZE))
        examples.append((x,compose(x,ops[x[axis]%2])))
    conditional = None
    for candidate in IDENTITY:
        parts = [[ex for ex in examples if ex[0][candidate]%2==flag] for flag in (0,1)]
        if not all(parts):
            continue
        maps = [infer(group) for group in parts]
        if all(m is not None for m in maps):
            conditional = candidate,maps
            break
    hits,flat = [],[]
    for _ in range(80):
        x = tuple(rng.sample(range(64),SIZE))
        gold = compose(x,ops[x[axis]%2])
        hits.append(conditional is not None and compose(x,conditional[1][x[conditional[0]]%2])==gold)
        flat.append(compose(x,ops[0])==gold)
    result.update(conditional=statistics.mean(hits),single_map_oracle=statistics.mean(flat))
    return result


def depth(seed):
    rng = random.Random(seed+774)
    ops = world(seed)
    table = learn(rng,ops,8)
    two = {apply_program(IDENTITY,s,table) for n in (0,1,2)
           for s in itertools.product(range(4),repeat=n)}
    result = {}
    for n in (3,4,8,16,32):
        counts = [0,0,0]
        for _ in range(96):
            seq = rng.choices(range(4),k=n)
            x = tuple(rng.sample(range(100),SIZE))
            goal = apply_program(x,seq,ops)
            pred = apply_program(x,seq,table)
            counts[0] += pred==goal
            counts[1] += apply_program(x,seq[:2],table)==goal
            counts[2] += any(compose(x,p)==goal for p in two)
        result[str(n)] = [c/96 for c in counts]
    return result


def replace_pair(seq,pair,token):
    result = []
    i = 0
    while i < len(seq):
        if tuple(seq[i:i+2]) == pair:
            result.append(token)
            i += 2
        else:
            result.append(seq[i])
            i += 1
    return result


def motifs(rng):
    primitives = list(range(4))
    rng.shuffle(primitives)
    a,b,c,d = primitives
    return [(a,b,a,c),(d,c,b,d),(a,b,a,c,d,c,b,d)]


def hierarchy(seed):
    rng = random.Random(seed)
    blocks = motifs(rng)
    def sample():
        return [x for block in rng.choices(blocks,k=rng.randint(2,6)) for x in block]
    training = [sample() for _ in range(64)]
    ops = world(seed)
    table = learn(rng,ops,8)
    merges = []
    levels = [0]*4
    for _ in range(8):
        counts = Counter((a,b) for seq in training for a,b in zip(seq,seq[1:]))
        pair,_ = counts.most_common(1)[0]
        token = len(table)
        table.append(compose(table[pair[0]],table[pair[1]]))
        levels.append(1+max(levels[x] for x in pair))
        training = [replace_pair(seq,pair,token) for seq in training]
        merges.append((pair,token))
    ratios,correct = [],[]
    for _ in range(96):
        seq = sample()
        compact = seq
        for pair,token in merges:
            compact = replace_pair(compact,pair,token)
        ratios.append(len(compact)/len(seq))
        correct.append(apply_program(IDENTITY,compact,table)==apply_program(IDENTITY,seq,ops))
    return dict(fraction_calls=statistics.mean(ratios),accuracy=statistics.mean(correct),
                levels=max(levels),macros=len(merges))


def plan(start,goal,actions,budget):
    queue = deque([(start,())])
    seen = {start}
    checks = 0
    while queue:
        state,path = queue.popleft()
        if state==goal:
            return path,checks
        for i,op in enumerate(actions):
            if checks>=budget:
                return None,checks
            checks+=1
            nxt = compose(state,op)
            if nxt==goal:
                return path+(i,),checks
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt,path+(i,)))
    return None,checks


def reasoning(seed):
    rng = random.Random(seed+181)
    ops = world(seed)
    learned = learn(rng,ops,8)
    blocks = motifs(rng)
    # Mine adjacent subplans from successful training traces; compile by their learned effects.
    pairs = Counter()
    for _ in range(96):
        path = [x for block in rng.choices(blocks,k=2) for x in block]
        pairs.update(zip(path,path[1:]))
    library = [p for p,_ in pairs.most_common(4)]
    result = {}
    training_goals = {apply_program(IDENTITY,a+b,ops) for a in blocks for b in blocks}
    goals = []
    for _ in range(4000):
        seq = [x for b in rng.choices(blocks,k=3) for x in b]
        at = rng.randrange(len(seq)+1)
        seq.insert(at,rng.randrange(4))
        goal = apply_program(IDENTITY,seq,ops)
        if goal not in training_goals and goal not in goals:
            goals.append(goal)
        if len(goals)==40:
            break
    result['unique_heldout_goals'] = len(goals)
    random_pairs = rng.sample(list(itertools.product(range(4),repeat=2)),4)
    for name,macros in [('primitive',[]),('mined',library),('random',random_pairs)]:
        vocab = [(i,) for i in range(4)] + macros
        actions = [apply_program(IDENTITY,p,learned) for p in vocab]
        hits, costs = [],[]
        for goal in goals:
            path,cost = plan(IDENTITY,goal,actions,160)
            flat = [] if path is None else [x for a in path for x in vocab[a]]
            hits.append(path is not None and apply_program(IDENTITY,flat,ops)==goal)
            costs.append(cost)
        result[name] = dict(success=statistics.mean(hits),checks=statistics.mean(costs))
    return result


def language(seed):
    rng = random.Random(seed+17)
    # A referential game. A speaker observes the chosen object and names its color and shape.
    words = rng.sample('lom rek pav zut fig nel'.split(),6)
    attributes = list(itertools.product(range(3), repeat=2))
    counts = {w:Counter() for w in words}
    for _ in range(160):
        color,shape = rng.choice(attributes)
        if (color+shape)%3==0:
            continue
        for w in (words[color],words[3+shape]):
            counts[w].update([(0,color),(1,shape)])
    meanings = {w:c.most_common(1)[0][0] for w,c in counts.items()}
    lexicon = {v:k for k,v in meanings.items()}
    # The environment can answer a question about a concealed gate. The learner
    # discovers from action consequences when each conditional word calls for selection.
    class Scene:
        def __init__(self, gate):
            self.gate = gate
        def ask(self):
            return ('dus','ven')[self.gate]
    trigger = rng.sample([0,1],2)
    grammar = Counter()
    for _ in range(128):
        condition,flag,act = (rng.randrange(2) for _ in range(3))
        feedback = act == int(flag==trigger[condition])
        if feedback:
            grammar[condition,Scene(flag).ask(),act] += 1
    scores = Counter()
    for _ in range(120):
        color = rng.randrange(3)
        shape = (-color)%3
        hidden,condition = rng.randrange(2),rng.randrange(2)
        scene = rng.sample([p for p in attributes if p!=(color,shape)],3)
        scene.insert(rng.randrange(4),(color,shape))
        command = (words[color],words[3+shape])
        wanted = [meanings[w] for w in command]
        gold = scene.index((color,shape)) if hidden==trigger[condition] else -1
        env = Scene(hidden)
        for asking in (False,True):
            signal = env.ask() if asking else 'ven'
            select = grammar[condition,signal,1]>grammar[condition,signal,0]
            action = next((i for i,p in enumerate(scene) if all(p[a]==v for a,v in wanted)),-1) if select else -1
            scores['ask' if asking else 'silent'] += action==gold
            scores['questions'] += asking
        scores['description'] += (lexicon.get((0,color)),lexicon.get((1,shape)))==command
    return {k:v/120 for k,v in scores.items()}


def compile_benchmark(seed):
    rng = random.Random(seed)
    ops = world(seed)
    begin = time.perf_counter_ns()
    table = learn(rng,ops,8)
    acquisition_ns = time.perf_counter_ns()-begin
    programs = {i:rng.choices(range(4),k=32) for i in range(16)}
    start = time.perf_counter_ns()
    compiled = {k:apply_program(IDENTITY,seq,table) for k,seq in programs.items()}
    compile_ns = time.perf_counter_ns()-start
    queries = [(rng.randrange(16),tuple(rng.sample(range(64),SIZE))) for _ in range(256)]
    gold = [apply_program(x,programs[k],ops) for k,x in queries]
    import numpy as np
    result = {'compile_ns':compile_ns,'acquisition_ns':acquisition_ns}
    for name in ('interpreter','compiled','vectorized'):
        def run():
            if name=='interpreter':
                return [apply_program(x,programs[k],table) for k,x in queries]
            if name=='compiled':
                return [compose(x,compiled[k]) for k,x in queries]
            ks = np.array([compiled[k] for k,_ in queries])
            xs = np.array([x for _,x in queries])
            return list(map(tuple,np.take_along_axis(xs,ks,axis=1).tolist()))
        durations = []
        for _ in range(7):
            start = time.perf_counter_ns()
            outputs = run()
            durations.append(time.perf_counter_ns()-start)
        tracemalloc.start()
        run()
        peak = tracemalloc.get_traced_memory()[1]
        tracemalloc.stop()
        result[name] = dict(ns_per_query=statistics.median(durations)/len(queries),
            accuracy=sum(x==y for x,y in zip(outputs,gold))/len(gold),peak_bytes=peak)
    for name in ('compiled','interpreter'):
        times = []
        for k,x in queries:
            start = time.perf_counter_ns()
            value = compose(x,compiled[k]) if name=='compiled' else apply_program(x,programs[k],table)
            times.append(time.perf_counter_ns()-start)
        result[name]['single_p50_ns'] = statistics.median(times)
        result[name]['single_p95_ns'] = sorted(times)[242]
    return result


def teaching(seed):
    """Learn a shared action vocabulary, explain an observed event, transfer the explanation."""
    rng = random.Random(seed+671)
    pairs = list(itertools.combinations(range(4),2))
    labels = rng.sample(['lor','gev','mun','tav','rok','zar'],len(pairs))
    def act(state,pair):
        i,j = pair
        state = list(state)
        state[i],state[j] = state[j],state[i]
        return tuple(state)
    def ground():
        votes = {w:Counter() for w in labels}
        for _ in range(96):
            state = tuple(rng.choices(range(5),k=4))
            i = rng.randrange(len(pairs))
            nxt = act(state,pairs[i])
            changed = tuple(j for j in range(4) if state[j]!=nxt[j])
            if changed:
                votes[labels[i]][changed] += 1
        return {w:c.most_common(1)[0][0] for w,c in votes.items() if c}
    speaker,listener = ground(),ground()
    scramble = dict(zip(labels,labels[1:]+labels[:1]))
    scores = Counter()
    lengths = []
    for _ in range(100):
        old = tuple(rng.sample(range(32),4))
        perm = tuple(rng.sample(range(4),4))
        after = compose(old,perm)
        current = old
        message = []
        for i in range(4):
            if current[i] != after[i]:
                pair = tuple(sorted((i,current.index(after[i]))))
                word = next((w for w,p in speaker.items() if p==pair),None)
                if word is None:
                    break
                message.append(word)
                current = act(current,pair)
        scores['explained'] += current==after
        lengths.append(len(message))
        fresh = tuple(rng.sample(range(100,164),4))
        for policy in ('taught','scrambled','silent'):
            state = fresh
            for word in ([] if policy=='silent' else message):
                mapping = listener.get(scramble[word] if policy=='scrambled' else word)
                if mapping:
                    state = act(state,mapping)
            scores[policy] += state==compose(fresh,perm)
    return dict({k:v/100 for k,v in scores.items()},utterance_tokens=statistics.mean(lengths))
