"""Bounded COG-LIFE learning/policy mechanisms. No evaluator truth imports.

The host projects authorized observations into these strict records. These
interfaces are not authority: a caller-provided 'visible' record is not proof
of acquisition. Freeze each role's acquisition ledger before evaluation.
"""
from __future__ import annotations
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from math import exp, isfinite
from random import Random
import re
from typing import Literal

def require(ok, msg):
    if not ok:
        raise ValueError(msg)

def token(s):
    return type(s) is str and re.fullmatch(r"[a-zA-Z0-9_-]{1,48}", s) is not None

def opaque(s):
    return type(s) is str and re.fullmatch(r"[a-zA-Z0-9_.:-]{1,160}", s) is not None

def bit(x):
    return type(x) is int and x in (0, 1)

def vector(x):
    return type(x) is tuple and len(x)==3 and all(type(v) is int and -8<=v<=8 for v in x)

def words(s):
    require(type(s) is str and 0<len(s)<=256, "invalid verbal observation")
    return tuple(re.findall(r"[a-z0-9]+", s.lower()))

@dataclass(frozen=True, slots=True)
class WitnessedAction:
    """Utterance/effect pair witnessed in the actor's authorized visible stream."""
    seq: int
    event_id: str
    action: str
    phrase: str
    before: tuple[int, int, int]
    after: tuple[int, int, int]
    observed_consequence_id: str

class GroundedLearner:
    """Learn lexical signals and model effects; compose unsupplied action sequences."""
    def __init__(self, capabilities, *, exact_only=False, min_effect_support=2):
        self.menu=tuple(sorted(capabilities))
        require(6<=len(self.menu)<=24 and len(set(self.menu))==len(self.menu)
                and all(token(t) for t in self.menu), "independent bounded candidate menu required")
        require(type(min_effect_support) is int and 2<=min_effect_support<=8,
                "at least two distinct witnessed starts")
        self.exact_only=exact_only
        self.min_effect_support=min_effect_support
        self.sequence=-1
        self.events=set()
        self.consequences=set()
        self.phrases=defaultdict(Counter)
        self.tokens=defaultdict(Counter)
        self.effects=defaultdict(dict)

    def learn(self, witness: WitnessedAction):
        require(type(witness) is WitnessedAction and type(witness.seq) is int
                and witness.seq>self.sequence and opaque(witness.event_id)
                and opaque(witness.observed_consequence_id) and witness.event_id not in self.events
                and witness.observed_consequence_id not in self.consequences,
                "nonmonotonic, repeated or unsupported witness")
        p=words(witness.phrase)
        require(bool(p) and witness.action in self.menu and vector(witness.before)
                and vector(witness.after), "unsupported observed action effect")
        self.sequence=witness.seq; self.events.add(witness.event_id)
        self.consequences.add(witness.observed_consequence_id)
        self.phrases[p][witness.action]+=1
        for w in set(p):
            self.tokens[w][witness.action]+=1
        delta=tuple(b-a for a,b in zip(witness.before,witness.after))
        self.effects[witness.action].setdefault(witness.before,set()).add(delta)

    def rank(self, phrase, *, k=5):
        require(type(k) is int and 1<=k<=len(self.menu),"invalid candidate boundary")
        p=words(phrase)
        scores=Counter(self.phrases.get(p,{}))
        if not self.exact_only:
            for w in sorted(set(p)):
                obs=self.tokens.get(w)
                if obs:
                    total=sum(obs.values())
                    for action,n in obs.items():
                        scores[action]+=n/total
        if not scores:return ()
        # No padded ties from unknown actions. Report actual returned coverage.
        return tuple(sorted(scores,key=lambda a:(-scores[a],a))[:k])

    def inferred_effects(self):
        out={}
        for a, states in self.effects.items():
            if len(states)<self.min_effect_support:continue
            alternatives=set().union(*states.values())
            if len(alternatives)==1:
                delta=next(iter(alternatives))
                if delta!=(0,0,0) and max(map(abs,delta))<=2:
                    out[a]=delta
        return dict(sorted(out.items()))

    def synthesize(self, before, goal, *, max_steps=3):
        """No supplied macro/action label; goal and current state are observable."""
        require(vector(before) and vector(goal) and type(max_steps) is int
                and 1<=max_steps<=4,"invalid bounded observable goal")
        if before==goal:return ()
        effects=self.inferred_effects(); q=deque([(before,())]); seen={before}
        while q:
            state,path=q.popleft()
            if len(path)==max_steps:continue
            for act,delta in effects.items():
                nxt=tuple(x+d for x,d in zip(state,delta))
                if not vector(nxt) or nxt in seen:continue
                if nxt==goal:return (*path,act)
                seen.add(nxt);q.append((nxt,(*path,act)))
        return None

@dataclass(frozen=True, slots=True)
class BeliefObservation:
    seq: int
    event_id: str
    claim: str
    source: str
    kind: Literal["report","firsthand"]
    proposition: int
    root: str | None
    acquisition: str | None = None

class BeliefLedger:
    """Learn source reliability from observed resolution; reports remain provisional."""
    def __init__(self, *, last_heard=False):
        self.last_heard=last_heard
        self.rows=defaultdict(list)
        self.track=defaultdict(lambda:[2,2])
        self.events=set();self.resolved=set();self.seq=-1

    def update(self, obs: BeliefObservation):
        require(type(obs) is BeliefObservation and type(obs.seq) is int and obs.seq>self.seq
                and opaque(obs.event_id) and all(token(x) for x in (obs.claim,obs.source))
                and obs.event_id not in self.events and bit(obs.proposition)
                and obs.kind in ("report","firsthand"),"invalid belief record")
        require(obs.root is None or opaque(obs.root),"malformed lineage")
        require((obs.kind=="firsthand" and opaque(obs.acquisition)) or
                (obs.kind=="report" and obs.acquisition is None),"role lineage mismatch")
        # Reports, even many mutually agreeing reports, never grant firsthand status.
        self.rows[obs.claim].append(obs);self.events.add(obs.event_id);self.seq=obs.seq
        if obs.kind!="firsthand":return
        for rep in self.rows[obs.claim][:-1]:
            if rep.kind!="report" or rep.root is None:continue
            key=(obs.claim,rep.root,rep.source)
            if key not in self.resolved:
                self.resolved.add(key)
                self.track[rep.source][int(rep.proposition!=obs.proposition)]+=1

    def belief(self, claim):
        seq=self.rows.get(claim,())
        firsthand=[o for o in seq if o.kind=="firsthand"]
        if firsthand:
            latest=firsthand[-1]
            p=1. if latest.proposition else 0.
            return {"probability_one":p,"level":"observed","basis":(latest.event_id,)}
        if not seq:return {"probability_one":.5,"level":"unresolved","basis":()}
        if self.last_heard:
            rep=seq[-1];p=.75 if rep.proposition else .25
            return {"probability_one":p,"level":"provisional","basis":(rep.event_id,)}
        # Same acquisition root cannot become several votes. Unknown roots are
        # conservatively collapsed and capped, not inferred to be independent.
        roots={}
        for rep in seq:
            roots.setdefault(rep.root,rep)
        latent=0.; basis=[]
        for root,rep in roots.items():
            good,bad=self.track[rep.source]
            direction=2*rep.proposition-1
            gain=min(.35 if root is None else 2.,max(0.,(good-bad)/(good+bad))+0.2)
            latent+=direction*gain;basis.append(rep.event_id)
        p=1/(1+exp(-max(-8.,min(8.,latent))))
        return {"probability_one":p,"level":"provisional","basis":tuple(basis)}

@dataclass(frozen=True, slots=True)
class CausalObservation:
    seq: int
    event_id: str
    exposure: int
    consequence: int
    randomized: bool
    probe_receipt: str | None

class CausalEstimator:
    """One-bit causal effect from equally counted observation opportunities."""
    def __init__(self, mode):
        require(mode in ("probe","passive","frozen"),"unrecognized causal arm")
        self.mode=mode;self.sequence=-1;self.seen=set();self.probes=set()
        self.counts=[[0,0],[0,0]];self.cost=Counter();self.is_frozen=False

    def freeze(self):
        self.is_frozen=True

    def observe(self, x: CausalObservation):
        require(type(x) is CausalObservation and type(x.seq) is int and x.seq>self.sequence
                and opaque(x.event_id) and x.event_id not in self.seen
                and bit(x.exposure) and bit(x.consequence) and type(x.randomized) is bool,
                "malformed/out-of-order causal observation")
        require((x.randomized and opaque(x.probe_receipt) and x.probe_receipt not in self.probes)
                or (not x.randomized and x.probe_receipt is None),"invalid probe lineage")
        require(not x.randomized or self.mode=="probe","non-probe arm received an intervention")
        self.seen.add(x.event_id);self.sequence=x.seq
        self.cost["opportunities"]+=1
        if x.randomized:
            self.probes.add(x.probe_receipt);self.cost["probes"]+=1
        if self.mode=="frozen" and self.is_frozen:return
        if x.randomized==(self.mode=="probe"):
            self.counts[x.exposure][x.consequence]+=1
            self.cost["updates"]+=1

    def estimate(self, *, min_per_cell=20):
        groups=[sum(g) for g in self.counts]
        if min(groups)<min_per_cell:return {"effect":None,"exposure_groups":tuple(groups),"cost":dict(self.cost)}
        a,b=self.counts
        return {"effect":(b[1]+.5)/(groups[1]+1)-(a[1]+.5)/(groups[0]+1),
                "exposure_groups":tuple(groups),"cost":dict(self.cost)}

@dataclass(frozen=True, slots=True)
class DecisionInput:
    candidates: tuple[str,...]
    confidence: float
    risk: Literal["low","high"]
    authority_present: bool
    verification_present: bool
    clarification_available: bool

def graded_commit(obs: DecisionInput, arm="graded"):
    """Choose an intelligence action; underlying world retains final write authority."""
    require(type(obs) is DecisionInput and obs.risk in ("low","high") and bool(obs.candidates)
            and len(set(obs.candidates))==len(obs.candidates)
            and all(token(x) for x in obs.candidates) and type(obs.confidence) in (int,float)
            and isfinite(obs.confidence) and 0<=obs.confidence<=1
            and all(type(x) is bool for x in (obs.authority_present,obs.verification_present,obs.clarification_available)),
            "invalid commitment observation")
    require(arm in ("graded","always","defer"),"unknown frozen policy")
    x=obs.candidates[0]
    if arm=="defer":return ("defer",None)
    if arm=="always":return ("commit",x) # requests transaction; host may refuse
    if obs.authority_present and obs.verification_present and obs.confidence>=(.95 if obs.risk=="high" else .80):
        return ("commit",x)
    if obs.clarification_available and obs.confidence>=.45:return ("clarify",None)
    if obs.risk=="low" and obs.confidence>=.60:return ("recommend",x) # reversible, no write
    return ("defer",None)

@dataclass(frozen=True, slots=True)
class PracticeObservation:
    seq: int
    event_id: str
    cues: tuple[str,...]
    feedback: int
    observed_outcome_id: str

class ReplayLearner:
    """Matched update slots; experience source, not extra work, defines intervention."""
    def __init__(self, mode, seed, *, capacity=32):
        require(mode in ("current","uniform","selective") and type(capacity) is int
                and 1<=capacity<=128,"invalid replay arm/storage")
        self.mode=mode;self.rng=Random(seed);self.bank=deque(maxlen=capacity)
        self.weights=defaultdict(float);self.cost=Counter();self.events=set()
        self.outcomes=set();self.sequence=-1

    def predict(self,cues):
        require(type(cues) is tuple and 0<len(cues)<=16 and all(token(k) for k in cues),
                "invalid observed practice features")
        s=sum(self.weights.get(k,0.) for k in sorted(set(cues)))+self.weights.get("::bias",0.)
        return 1/(1+exp(-max(-16,min(16,s))))

    def _update(self,o):
        err=o.feedback-self.predict(o.cues)
        for k in sorted(set(o.cues)):
            self.weights[k]+=.12*err/(len(set(o.cues))+1)
        self.weights["::bias"]+=.12*err/(len(set(o.cues))+1)
        self.cost["updates"]+=1
        self.cost["features_touched"]+=len(set(o.cues))+1

    def observe(self,o: PracticeObservation):
        require(type(o) is PracticeObservation and type(o.seq) is int and o.seq>self.sequence
                and opaque(o.event_id) and o.event_id not in self.events and bit(o.feedback)
                and opaque(o.observed_outcome_id) and o.observed_outcome_id not in self.outcomes,
                "noncausal, repeated, or unsupported practice")
        pred=self.predict(o.cues)
        self.sequence=o.seq;self.events.add(o.event_id);self.outcomes.add(o.observed_outcome_id)
        self.cost["presented"]+=1
        self._update(o)
        selected=o
        if self.mode!="current" and self.bank:
            if self.mode=="uniform":
                selected=self.bank[self.rng.randrange(len(self.bank))]
                self.cost["retrieval_inspections"]+=1
            else:
                pool=list(self.bank)
                self.cost["retrieval_inspections"]+=len(pool)
                selected=max(pool,key=lambda old:(abs(old.feedback-self.predict(old.cues)), -old.seq))
            require(selected.seq<o.seq,"replay cannot read future episodes")
            self.cost["replayed_updates"]+=1
        self._update(selected)
        self.bank.append(o)
        return {"pre_feedback_probability":pred,"secondary_observation_id":selected.event_id}

def from_visible_frame(frame, prefix, *, trusted_observer):
    """Project only authorized prefix records; never use host/evaluator objects."""
    visible=tuple(prefix)
    refs={x.id:x for x in visible}
    require(len(refs)==len(visible) and all(x.seq<frame.seq for x in visible),
            "duplicate or future visible lineage")
    require(trusted_observer and frame.source==trusted_observer and frame.id not in refs,
            "unsupported sensory source")
    require(all(p in refs for p in frame.parents),"frame depends on unobserved parent")
    d=frame.payload
    require(hasattr(d,'keys'),"frame payload not mapping")
    keys=set(d)
    if frame.kind=="life082_witness":
        require(keys=={"action","phrase","before","after","consequence"} and
                d["consequence"] in frame.parents and
                refs[d["consequence"]].kind=="life082_effect",
                "witness lacks prior visible consequence")
        effect=refs[d["consequence"]]
        require(effect.source==trusted_observer and
                set(effect.payload)=={"action","before","after"} and
                all(effect.payload[k]==d[k] for k in ("action","before","after")),
                "witness did not match visible sensory effect")
        return WitnessedAction(frame.seq,frame.id,d["action"],d["phrase"],tuple(d["before"]),tuple(d["after"]),d["consequence"])
    if frame.kind=="life083_belief":
        require(keys=={"claim","speaker","kind","proposition","root","acquisition"},"invalid belief projection")
        if d["kind"]=="firsthand":
            require(d["acquisition"] in frame.parents and refs[d["acquisition"]].kind=="life083_direct",
                    "reported acquisition cannot become direct observation")
            sensed=refs[d["acquisition"]]
            require(sensed.source==trusted_observer and
                    sensed.payload=={"claim":d["claim"],"proposition":d["proposition"]},
                    "firsthand payload did not match acquisition")
        else:
            require(d["root"] is None or d["root"] in frame.parents,
                    "unknown root must remain unattributed")
        return BeliefObservation(frame.seq,frame.id,d["claim"],d["speaker"],d["kind"],d["proposition"],d["root"],d["acquisition"])
    if frame.kind=="life084_transition":
        require(keys=={"exposure","consequence","randomized","probe_receipt"}, "invalid causal projection")
        if d["randomized"]:
            require(d["probe_receipt"] in frame.parents and refs[d["probe_receipt"]].kind=="probe",
                    "randomized result lacks paired native observed receipt")
            receipt=refs[d["probe_receipt"]]
            r=receipt.payload
            require(r.get("action")=="probe" and r.get("authorized") is True and r.get("applied") is True
                    and r.get("effect",{}).get("observation")=={"exposure":d["exposure"],"consequence":d["consequence"]},
                    "observed probe setting/consequence mismatch")
        return CausalObservation(frame.seq,frame.id,d["exposure"],d["consequence"],d["randomized"],d["probe_receipt"])
    if frame.kind=="life086_practice":
        require(keys=={"cues","feedback","consequence"} and d["consequence"] in frame.parents
                and refs[d["consequence"]].kind=="life086_feedback","practice lacks witnessed learning consequence")
        feedback=refs[d["consequence"]]
        require(feedback.source==trusted_observer and feedback.payload=={"feedback":d["feedback"]},
                "practice-feedback binding mismatch")
        return PracticeObservation(frame.seq,frame.id,tuple(d["cues"]),d["feedback"],d["consequence"])
    raise ValueError("unsupported projection")
