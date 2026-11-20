"""Host-only fixture generation. Needs separate review before any held scoring.

This module can emit privately separate learner training observations, unlabelled
queries/identities, and a role-restricted scorer fixture. It does not train or score.
"""
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from random import Random
import json
import sys
from investigation_world.life import Action, LifeWorld
from research_lab.life_study_082_086 import from_visible_frame

SEEDS=(84113,84119,84131)
GROUPS_PER_CAUSAL_PHASE=160
CUES=tuple(f"cue{i:02}" for i in range(8))
TRIALS_PER_PHASE=128
HOLD_CONTEXTS_PER_SKILL=16

def number(*t):
    return int.from_bytes(sha256(":".join(map(str,t)).encode()).digest()[:7],"big")

def branch_observation(seed,seq,setting,outcomes,randomized):
    # Local branch clone from same world identity; returned prefix only.
    world=LifeWorld(seed); port=world.port("p0")
    parents=(); ref=None
    if randomized:
        world.register_probe("isolated",{"zero":{"exposure":0,"consequence":outcomes[0]},
                                        "one":{"exposure":1,"consequence":outcomes[1]}},allowed=("p0",))
        r=port.act(Action("probe","isolated","one" if setting else "zero"))
        if not (r.authorized and r.applied):raise ValueError("safe probe unexpectedly rejected")
        ref=r.observation_id
        parents=(len(world.event_log()),)
    world.inject("life084_transition",{"exposure":setting,"consequence":outcomes[setting],
                 "randomized":randomized,"probe_receipt":ref},("p0",),parents=parents)
    *prefix,frame=port.observe()
    z=asdict(from_visible_frame(frame,prefix,trusted_observer="fixture"))
    z["seq"]=seq
    return z

def risks(phase,u):
    p0=(.15 if phase=="before" else .25)+.55*u
    return p0,p0+(.25 if phase=="before" else -.20)

def make_causal(seed,n):
    if type(n) is not int or n<8 or n%4:raise ValueError("balanced causal group count required")
    rows=[];truth=[]
    for phase in ("before","after"):
        rng=Random(number(seed,"random-allocation",phase))
        # Independent randomized assignment within latent strata, balanced for
        # support. Latent stratum and alternate outcome never reach learner.
        assign={u:[0]*(n//4)+[1]*(n//4) for u in (0,1)}
        for a in assign.values():rng.shuffle(a)
        # Independent shuffle of the balanced latent sequence: visible
        # sequence position cannot deterministically reveal the stratum.
        latent=[0]*(n//2)+[1]*(n//2)
        Random(number(seed,"hidden-latent-permutation",phase)).shuffle(latent)
        seen={0:0,1:0}
        total=0
        for j,u in enumerate(latent):
            active=assign[u][seen[u]];seen[u]+=1
            q=Random(number(seed,"nuisance",phase,j))
            draw=q.random()
            p0,p1=risks(phase,u)
            potential=(int(draw<p0),int(draw<p1))
            # Separate private, evaluator-only population and nuisance draw.
            held=Random(number(seed,"held-nuisance",phase,j)).random()
            total+=int(held<p1)-int(held<p0)
            passive=u if q.random()<.9 else 1-u
            # Add observation-only worlds under the same nuisance/outcomes.
            case=number(seed,"world",phase,j)
            active_obs=branch_observation(case,len(rows),active,potential,True)
            passive_obs=branch_observation(case,len(rows),passive,potential,False)
            rows.append(dict(phase=phase,pair=f"pair-{number(seed,'masked-pair',phase,j):014x}",active=active_obs,passive=passive_obs))
        truth.append(dict(phase=phase,sealed_empirical_effect=total/n,worlds=n))
    return rows,truth

def practice_frame(seed,seq,cues,feedback):
    w=LifeWorld(seed);p=w.port("p0")
    root=w.inject("life086_feedback",{"feedback":feedback},("p0",))
    seen=p.observe()[-1]
    w.inject("life086_practice",{"cues":list(cues),"feedback":feedback,"consequence":seen.id},("p0",),parents=(root,))
    *prefix,frame=p.observe()
    q=asdict(from_visible_frame(frame,prefix,trusted_observer="fixture"));q["seq"]=seq
    return q

def make_practice(seed,n,held):
    if type(n) is not int or n<16 or n%8 or type(held) is not int or held<8 or held%8:
        raise ValueError("balanced synthetic episode bounds required")
    data=[]; queries=[]; truth=[]
    for skill in ("early","later"):
        for j in range(n):
            i=j%8
            cues=(CUES[i], "shared" if j%4!=0 else skill)
            value=int((i<4) if skill=="early" else (i>=4))
            data.append(dict(phase=skill,episode=number(seed,"practice",skill,j),visible=practice_frame(
                number(seed,"practice",skill,j),len(data),cues,value)))
        # No identical world identity across fit and evaluator. Cue repetition
        # is intentional: assesses retained competence, not open-domain transfer.
        for j in range(held):
            i=j%8; ctx=number(seed,"delayed",skill,j); cues=(CUES[i],skill)
            queries.append(dict(query=ctx,phase=skill,cues=list(cues)))
            truth.append(dict(query=ctx,feedback=int((i<4) if skill=="early" else (i>=4))))
    return data,queries,truth

def documents(seeds=SEEDS,n_causal=GROUPS_PER_CAUSAL_PHASE,n_practice=TRIALS_PER_PHASE,held=HOLD_CONTEXTS_PER_SKILL):
    source={"schema":"veritas.life084086.training.v1","runs":[]}
    queries={"schema":"veritas.life084086.queries.v1","runs":[]}
    sealed={"schema":"veritas.life084086.scorer.v1","runs":[]}
    for seed in seeds:
        a,b=make_causal(seed,n_causal); c,d,e=make_practice(seed,n_practice,held)
        run=f"run-{number(seed,'masked-run'):014x}"
        source["runs"].append(dict(run=run,causal=a,practice=c))
        queries["runs"].append(dict(run=run,causal=[{"phase":x["phase"]} for x in b],practice=d))
        sealed["runs"].append(dict(run=run,causal=b,practice=e))
    return source,queries,sealed

def main(directory):
    out=Path(directory);out.mkdir(mode=0o700,parents=True,exist_ok=False)
    names=("training-observations.json","evaluator-queries.json","scorer-only.json")
    for name,obj in zip(names,documents()):
        p=out/name
        with p.open("x") as f:f.write(json.dumps(obj,sort_keys=True,separators=(",",":"))+"\n")
        p.chmod(0o600)
    print("Prepared three separated synthetic role files; no fitting or evaluation.")
if __name__=="__main__":main(*sys.argv[1:])
