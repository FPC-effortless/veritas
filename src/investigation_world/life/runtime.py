"""Seeded append-only local world; exact restore re-executes the event transcript.

AgentPort is a cooperative data-minimizing API, not a Python security sandbox.
A candidate worker must receive serialized observations only, not a live world.
"""
from __future__ import annotations
from dataclasses import asdict, replace
from hashlib import sha256
import hmac
import json
import os
from pathlib import Path
import re
import tempfile

from investigation_world.core.provenance import ProvenanceDAG
from .models import Action, Observation, Receipt, PEOPLE, LOCATIONS, OBJECTS, MILESTONES

SCHEMA = "veritas.cog-life.v1"
MAX_TICK = 10_000
MAX_EVENTS = 65_536
NAME = re.compile(r"[a-z][a-z0-9_-]{0,63}\Z")

def wire(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)

def clone(obj):
    return json.loads(wire(obj))

def hash_obj(obj):
    return sha256(wire(obj).encode()).hexdigest()

def no_duplicate(items):
    out = {}
    for k, v in items:
        if k in out:
            raise ValueError("duplicate JSON property")
        out[k] = v
    return out

class AgentPort:
    __slots__ = ("_get", "_send")
    def __init__(self, get, send):
        self._get, self._send = get, send
    def observe(self, since_seq=0):
        return self._get(since_seq)
    def act(self, action):
        return self._send(action)

class LifeWorld:
    """Controller-side deterministic world. No data, external actions, or tools."""
    def __init__(self, seed: int, *, _factory_bound: bool = False):
        if type(_factory_bound) is not bool:
            raise ValueError("factory binding marker must be Boolean")
        if type(seed) is not int or not 0 <= seed < 2**63:
            raise ValueError("seed must be a nonnegative 63-bit integer")
        self._seed = seed
        self._key = sha256(f"{SCHEMA}:{seed}:observation".encode()).digest()
        self._events: list[str] = []
        self._views: dict[str,list[str]] = {p: [] for p in PEOPLE}
        self._visible: dict[str,dict[str,int]] = {p: {} for p in PEOPLE}
        self._view_by_host_seq: dict[str,dict[int,str]] = {p: {} for p in PEOPLE}
        self._provenance = ProvenanceDAG()
        self._ids: dict[tuple[str,str], tuple[str,Receipt]] = {}
        self._tick = 0
        self._stage = "childhood"
        self._person = {p: LOCATIONS[self._number(0,p) % len(LOCATIONS)] for p in PEOPLE}
        self._native = None
        if _factory_bound:
            from .native_bridge import canonical_seed
            self._native = canonical_seed(seed)
            self._person = dict(self._native["initial_locations"])
        self._objects = {o: {"owner": PEOPLE[i], "location": LOCATIONS[self._number(0,o) % len(LOCATIONS)], "version": 0}
                         for i,o in enumerate(OBJECTS)}
        self._probes: dict = {}
        self._promises: list[dict] = []
        self._append("genesis", "genesis", "world", PEOPLE, {"schema":SCHEMA,"seed":seed,"factory_bound":_factory_bound},
                     private={"people":self._person,"objects":self._objects,"native":self._native})

    @classmethod
    def from_world_factory(cls, seed: int):
        return cls(seed, _factory_bound=True)

    def native_identity(self):
        """Evaluator-only WorldFactory provenance and identity; no worker access."""
        if self._native is None:
            raise ValueError("world was not derived from the canonical WorldFactory")
        return clone(self._native)

    @property
    def tick(self):
        return self._tick

    @property
    def stage(self):
        return self._stage

    def _number(self, tick, tag):
        return int.from_bytes(hmac.digest(self._key, f"{tick}:{tag}".encode(), "sha256")[:8], "big")

    def _view_id(self, agent, sequence):
        return "v" + hmac.digest(self._key, f"view:{agent}:{sequence}".encode(),"sha256").hex()[:32]

    def _append(self, op, kind, source, audience, instruction, *, public=None, private=None, parents=()):
        if len(self._events) >= MAX_EVENTS:
            raise ValueError("event counter exhausted")
        audience = tuple(sorted(set(audience)))
        parents = tuple(sorted(set(parents)))
        if any(p not in PEOPLE for p in audience) or any(type(x) is not int or not 1 <= x <= len(self._events) for x in parents):
            raise ValueError("invalid audience or parent")
        seq = len(self._events) + 1
        prev = json.loads(self._events[-1])["digest"] if self._events else "0"*64
        event = {"seq":seq,"tick":self._tick,"op":op,"kind":kind,"source":source,"audience":audience,
                 "instruction":instruction,"public":public,"private":private,"parents":parents,"previous":prev}
        event["digest"] = hash_obj(event)
        encoded = wire(event)
        projected = {}
        for agent in audience:
            local_index = len(self._views[agent])+1
            ident = self._view_id(agent, local_index)
            index = self._view_by_host_seq[agent]
            shown = tuple(index[p] for p in parents if p in index)
            payload = ({"person":agent,"location":self._person[agent],"stage":self._stage}
                       if op=="genesis" else (public or {}))
            projected[agent] = (ident, wire(asdict(Observation(
                local_index, self._tick, kind, source, "life", payload, shown, ident))))
        for p in parents:
            self._provenance.add_citation(str(seq),str(p))
        self._events.append(encoded)
        for agent, (ident, item) in projected.items():
            self._views[agent].append(item)
            self._visible[agent][ident] = seq
            self._view_by_host_seq[agent][seq] = ident
        return seq

    def _people_at(self, location):
        return tuple(p for p in PEOPLE if self._person[p] == location)

    def _observe(self, agent, since_seq):
        if type(since_seq) is not int or not 0 <= since_seq <= len(self._views[agent]):
            raise ValueError("cursor must refer to this observer prefix")
        return tuple(Observation(**{**row, "parents":tuple(row["parents"])})
                     for row in map(json.loads,self._views[agent][since_seq:]))

    def port(self, agent):
        if agent not in PEOPLE:
            raise ValueError("unknown local agent")
        return AgentPort(lambda seq:self._observe(agent,seq), lambda action:self._act(agent,action))

    def advance(self, tick):
        if type(tick) is not int or not self._tick <= tick <= MAX_TICK:
            raise ValueError("invalid logical time")
        if len(self._events) + tick-self._tick > MAX_EVENTS:
            raise ValueError("event counter exhausted")
        while self._tick < tick:
            self._tick += 1
            self._automatic()
        return self._tick

    def _automatic(self):
        t = self._tick
        a = PEOPLE[self._number(t,"person") % len(PEOPLE)]
        p = PEOPLE[(PEOPLE.index(a)+1+self._number(t,"other")%7)%8]
        o = OBJECTS[self._number(t,"item") % len(OBJECTS)]
        loc = LOCATIONS[self._number(t,"location") % 3]
        if t in MILESTONES:
            self._stage = MILESTONES[t]
            self._append("advance","milestone","world",PEOPLE,{},public={"stage":self._stage})
        elif t % 7 == 0:
            self._person[a] = loc
            self._append("advance","arrival",a,self._people_at(loc),{},public={"person":a,"location":loc})
        elif t % 7 in (1,2,6):
            v = self._objects[o]
            v["location"] = loc
            v["version"] += 1
            self._append("advance","placement",a,self._people_at(loc),{},
                         public={"object":o,"location":loc,"version":v["version"]})
        elif t % 7 == 3:
            data = {"from":a,"to":p,"object":o}
            self._promises.append(data.copy())
            self._append("advance","promise",a,(a,p),{},public=data)
        elif t % 7 == 4:
            # An attributed report is not the placement oracle, even if accurate.
            self._append("advance","testimony",a,(a,p),{},public={"from":a,"to":p,"object":o,"claimed_location":loc,"epistemic":"claim"})
        else:
            self._append("advance","request",a,(a,p),{},public={"from":a,"to":p,"object":o})

    def inject(self, kind, payload, audience, source="fixture", parents=()):
        """Trusted host-only inert event; cannot edit persons, ownership, or time."""
        reserved = {"genesis","milestone","advice","action_receipt","probe_registered","arrival",
                    "placement","promise","testimony","request","move","place","inspect","testify","probe","wait"}
        if type(kind) is not str or not NAME.fullmatch(kind) or kind in reserved:
            raise ValueError("invalid fixture event kind")
        if type(source) is not str or not NAME.fullmatch(source) or source == "world" or source in PEOPLE:
            raise ValueError("fixture provenance cannot impersonate native actors")
        if type(payload) is not dict or len(wire(payload)) > 64_000:
            raise ValueError("fixture payload must be a bounded JSON object")
        if not isinstance(audience,(tuple,list)):
            raise ValueError("fixture audience must be explicit")
        audience = tuple(sorted(set(audience)))
        parents = tuple(sorted(set(parents)))
        return self._append("inject",kind,source,audience,{"payload":clone(payload)},public=clone(payload),parents=parents)

    def register_probe(self, name, transitions, allowed=PEOPLE):
        """Host-only fixture: each allowed named setting produces a local read."""
        if type(name) is not str or not NAME.fullmatch(name) or name in self._probes:
            raise ValueError("invalid or duplicate fixture name")
        if type(transitions) is not dict or not transitions or len(transitions)>16 or len(wire(transitions))>32_000:
            raise ValueError("probe response map must be bounded")
        if any(not NAME.fullmatch(k) or type(v) is not dict for k,v in transitions.items()):
            raise ValueError("probe labels or typed outcomes invalid")
        allowed = tuple(sorted(set(allowed)))
        if not allowed or any(a not in PEOPLE for a in allowed):
            raise ValueError("invalid probe authority")
        record = {"name":name,"transitions":clone(transitions),"allowed":allowed}
        seq = self._append("register","probe_registered","fixture",(),record)
        self._probes[name] = record
        return seq

    def _act(self, actor, action):
        if type(action) is not Action:
            raise TypeError("use the typed local Action")
        if (type(action.kind) is not str or not NAME.fullmatch(action.kind) or
            type(action.target) is not str or not NAME.fullmatch(action.target) or
            type(action.evidence) is not tuple or len(action.evidence) > 16 or
            any(type(e) is not str or len(e)>64 for e in action.evidence)):
            raise ValueError("invalid Action envelope")
        if action.expected_version is not None and (type(action.expected_version) is not int or action.expected_version<0):
            raise ValueError("invalid expected version")
        rid = action.request_id
        if rid is not None and (type(rid) is not str or not NAME.fullmatch(rid)):
            raise ValueError("invalid request identity")
        packet = clone(asdict(action))
        request = wire(packet)
        if len(request)>64_000:
            raise ValueError("action payload too large")
        if rid is not None and (actor,rid) in self._ids:
            previous, receipt = self._ids[actor,rid]
            if previous!=request:
                raise ValueError("idempotency conflict")
            return replace(receipt,replayed=True,cost=0)
        if len(self._events)>=MAX_EVENTS:
            raise ValueError("event counter exhausted")
        evidence = self._visible[actor]
        if any(x not in evidence for x in action.evidence):
            decision = (False,False,"evidence outside visible prefix",{},(actor,))
            ancestors=()
        else:
            decision = self._apply(actor,action)
            ancestors=tuple(evidence[x] for x in action.evidence)
        auth, applied, reason, payload, audience=decision
        contents={"action":action.kind,"target":action.target,"authorized":auth,"applied":applied,
                  "reason":reason,"effect":payload}
        seq=self._append("act",action.kind if applied else "action_receipt",actor,audience,
                        {"action":packet},public=contents,parents=ancestors)
        receipt=Receipt(action.kind,auth,applied,reason,self._view_by_host_seq[actor][seq])
        if rid is not None:self._ids[actor,rid]=(request,receipt)
        return receipt

    def _apply(self, actor, a):
        kind, target, value=a.kind,a.target,a.value
        deny=lambda reason:(False,False,reason,{},(actor,))
        reject=lambda reason:(True,False,reason,{},(actor,))
        ok=lambda effect,audience=(actor,):(True,True,"applied",effect,audience)
        if kind == "wait" and target == actor and value is None:
            return ok({})
        if kind == "move" and target in LOCATIONS and value is None:
            self._person[actor]=target
            return ok({"person":actor,"location":target},self._people_at(target))
        if kind in ("inspect","place"):
            if target not in self._objects:
                return deny("unknown placement scope")
            o=self._objects[target]
            if o["location"] != self._person[actor]:
                return deny("object not in local scope")
            if kind == "inspect" and value is None:
                return ok({"object":target,"location":o["location"],"version":o["version"]})
            if kind!="place" or type(value) is not str or value not in LOCATIONS or o["owner"]!=actor:
                return deny("placement not authorized")
            if a.expected_version != o["version"]:
                return reject("stale or missing object version")
            o["location"]=value
            o["version"]+=1
            return ok({"object":target,"location":value,"version":o["version"]},
                      tuple(set((actor,)+self._people_at(value))))
        if kind in ("promise","request","testify") and target in PEOPLE and target!=actor:
            if kind in ("promise","request") and type(value) is str and value in OBJECTS:
                effect={"from":actor,"to":target,"object":value}
                if kind=="promise":self._promises.append(effect.copy())
                return ok(effect,(actor,target))
            if kind=="testify" and type(value) is str and 0<len(value)<=256:
                return ok({"from":actor,"to":target,"text":value,"epistemic":"claim"},(actor,target))
        if kind == "probe" and target in self._probes:
            fixture=self._probes[target]
            if actor not in fixture["allowed"]:
                return deny("probe outside local authority")
            if type(value) is not str or value not in fixture["transitions"]:
                return reject("probe setting unavailable")
            return ok({"fixture":target,"setting":value,"observation":clone(fixture["transitions"][value])})
        return deny("unsupported local action")

    def event_log(self):
        """Host-only defensive copy of host truth and every checked transition."""
        return tuple(map(json.loads,self._events))

    def truth(self):
        """Host/evaluator only. Never use this method in a candidate process."""
        return clone({"tick":self._tick,"stage":self._stage,"people":self._person,
                      "objects":self._objects,"promises":self._promises})

    def provenance_roots(self, *host_sequences):
        """Host roots only, not statistical independence or actor-visible truth."""
        if not host_sequences or any(type(n) is not int or not 1<=n<=len(self._events) for n in host_sequences):
            raise ValueError("unknown host provenance event")
        return tuple(sorted(map(int,self._provenance.get_root_sources(map(str,host_sequences)))))

    @classmethod
    def replay(cls, events):
        rows = list(events)
        if not rows or len(rows)>MAX_EVENTS or rows[0].get("op")!="genesis":
            raise ValueError("missing genesis or oversized replay")
        world = cls(rows[0]["instruction"]["seed"], _factory_bound=rows[0]["instruction"]["factory_bound"])
        if wire(rows[0])!=world._events[0]:
            raise ValueError("noncanonical genesis")
        for row in rows[1:]:
            op=row["op"]
            n=len(world._events)
            if op=="advance":
                if row["tick"]!=world._tick+1:
                    raise ValueError("nonconsecutive autonomous tick")
                world.advance(row["tick"])
            elif op=="inject":
                world.inject(row["kind"],row["instruction"]["payload"],row["audience"],row["source"],row["parents"])
            elif op=="register":
                world.register_probe(**row["instruction"])
            elif op=="act":
                a=clone(row["instruction"]["action"])
                a["evidence"]=tuple(a["evidence"])
                world.port(row["source"]).act(Action(**a))
            else:
                raise ValueError("unknown event operation")
            if len(world._events)!=n+1 or world._events[-1]!=wire(row):
                raise ValueError("replay diverged")
        return world

    def fork(self, seq):
        if type(seq) is not int or not 1 <= seq <= len(self._events):
            raise ValueError("unknown fork prefix")
        return self.replay(self.event_log()[:seq])

    def save(self, path):
        target=Path(path)
        data=wire({"schema":SCHEMA,"events":self.event_log()})+"\n"
        if len(data.encode("utf-8"))>64*1024**2:
            raise ValueError("life world checkpoint too large")
        pending=None
        try:
            with tempfile.NamedTemporaryFile(mode="w",encoding="utf-8",dir=target.parent, delete=False) as f:
                pending=Path(f.name)
                f.write(data)
                f.flush()
                os.fsync(f.fileno())
            pending.replace(target)
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)

    @classmethod
    def load(cls, path):
        with Path(path).open("rb") as f:
            raw=f.read(64*1024**2+1)
        if len(raw)>64*1024**2:
            raise ValueError("life world checkpoint too large")
        r=json.loads(raw,object_pairs_hook=no_duplicate)
        if type(r) is not dict or set(r)!={"schema","events"} or r["schema"]!=SCHEMA:
            raise ValueError("unsupported life world checkpoint")
        return cls.replay(r["events"])
