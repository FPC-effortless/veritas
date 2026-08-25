from __future__ import annotations
from datetime import date, timedelta
from random import Random
from investigation_world.core.models import *

class WorldGenerationConfig(BaseModel):
    num_people:int=100; num_organizations:int=50; num_addresses:int=50; timeline_start:date=date(2018,1,1); timeline_end:date=date(2026,1,1); relationship_density:float=.12; alias_rate:float=.35; identity_collision_rate:float=.12; ownership_chain_depth:int=3; rename_rate:float=.2; address_change_rate:float=.2; shared_address_rate:float=.25

class WorldFactory:
    @staticmethod
    def generate(seed:int, config:WorldGenerationConfig|None=None)->CanonicalWorld:
        c=config or WorldGenerationConfig(); rng=Random(seed); w=CanonicalWorld(world_id=f"WORLD-{seed:06d}",seed=seed)
        def ident(prefix,n): return f"{prefix}-{n:06d}"
        first=["Avery","Daniel","Mira","Jonah","Leila","Chuka","Nadia","Rowan","Sana","Theo"]; last=["Okafor","Ibarra","Voss","Marlowe","Chen","Bennett","Kline","Sato"]
        for i in range(1,c.num_addresses+1):
            aid=ident("ADDR",i); w.addresses[aid]=Address(canonical_id=aid,synthetic_line=f"{100+i} Meridian Loop",city=f"New {['Aster','Briar','Cedar'][i%3]}",region=f"R-{i%9:02d}",postal_code=f"SYN-{i:04d}")
        for i in range(1,c.num_people+1):
            pid=ident("PER",i); name=f"{first[i%len(first)]} {last[i%len(last)]}"; aliases=[name.replace(" "," C. ",1)] if rng.random()<c.alias_rate else []
            w.people[pid]=Person(canonical_id=pid,canonical_name=name,aliases=aliases,birth_year=1965+rng.randrange(35),historical_addresses=[ident("ADDR",1+(i%c.num_addresses))])
        for i in range(1,c.num_organizations+1):
            oid=ident("ORG",i); stem=["Meridian","Northstar","Cobalt","Juniper","Palisade","Lattice"][i%6]; suffix=["Industrial Systems","Strategic Holdings","Civic Works","Analytics Group"][i%4]; name=f"{stem} {suffix} Ltd"; addr=ident("ADDR",1+(i%c.num_addresses))
            w.organizations[oid]=Organization(canonical_id=oid,legal_name=name,aliases=[name.replace(" Ltd","")] if rng.random()<c.rename_rate else [],registration_number=f"SYN-REG-{i:05d}",incorporation_date=c.timeline_start+timedelta(days=rng.randrange(900)),historical_addresses=[addr])
        ev=1; rel=1
        def addrel(s,p,o,start,end=None,attrs=None):
            nonlocal rel; w.relationships.append(Relationship(relationship_id=ident("REL",rel),subject_id=s,predicate=p,object_id=o,valid_from=start,valid_to=end,created_by_event_id=ident("EVENT",ev),attributes=attrs or {})); rel+=1
        for i in range(1,c.num_organizations+1):
            oid=ident("ORG",i); pid=ident("PER",1+(i*7%c.num_people)); dt=c.timeline_start+timedelta(days=(i*37)%1200); addrel(pid,Predicate.DIRECTOR_OF,oid,dt); w.events.append(Event(event_id=ident("EVENT",ev),event_type="DirectorAppointed",timestamp=dt,payload={"person_id":pid,"organization_id":oid})); ev+=1
            addrel(oid,Predicate.REGISTERED_AT,ident("ADDR",1+(i%c.num_addresses)),c.timeline_start)
            if i>1: owner=ident("ORG",max(1,i//2)); addrel(owner,Predicate.OWNS,oid,c.timeline_start+timedelta(days=100+i),attrs={"percentage":75.0})
        for i in range(1,c.num_people+1):
            if i%3==0: addrel(ident("PER",i),Predicate.EMPLOYED_BY,ident("ORG",1+(i%c.num_organizations)),c.timeline_start+timedelta(days=200+i))
        for i in range(1, min(10,c.num_organizations)+1):
            dt=c.timeline_start+timedelta(days=500+i*23); w.events.append(Event(event_id=ident("EVENT",ev),event_type="OrganizationRenamed",timestamp=dt,payload={"organization_id":ident("ORG",i)})); ev+=1
        w.metadata={"generator_version":"0.1.0","config":c.model_dump(mode="json")}; return w

def validate_world(w:CanonicalWorld)->list[str]:
    errors=[]; ids=list(w.people)+list(w.organizations)+list(w.addresses)+list(w.domains)
    if len(ids)!=len(set(ids)): errors.append("duplicate canonical IDs")
    known=set(ids)
    for r in w.relationships:
        if r.subject_id not in known or r.object_id not in known: errors.append(f"dangling relationship {r.relationship_id}")
        if r.valid_to and r.valid_to<r.valid_from: errors.append(f"invalid temporal ordering {r.relationship_id}")
    for e in w.events:
        if e.event_id not in {x.event_id for x in w.events}: errors.append("duplicate event")
    return errors

