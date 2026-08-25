from __future__ import annotations
from datetime import date,timedelta
from random import Random
from pydantic import BaseModel
from investigation_world.core.models import *
class WorldGenerationConfig(BaseModel):
 num_people:int=100; num_organizations:int=50; num_addresses:int=50; timeline_start:date=date(2018,1,1); timeline_end:date=date(2026,1,1); relationship_density:float=.12; alias_rate:float=.35; rename_rate:float=.2; ownership_chain_depth:int=3
class WorldFactory:
 @staticmethod
 def generate(seed:int,config:WorldGenerationConfig|None=None)->CanonicalWorld:
  c=config or WorldGenerationConfig(); r=Random(seed); w=CanonicalWorld(world_id=f'WORLD-{seed:06d}',seed=seed); iid=lambda p,n:f'{p}-{n:06d}'
  for i in range(1,c.num_addresses+1): w.addresses[iid('ADDR',i)]=Address(canonical_id=iid('ADDR',i),synthetic_line=f'{100+i} Meridian Loop',city=f'New {("Aster","Briar","Cedar")[i%3]}',region=f'R-{i%9:02d}',postal_code=f'SYN-{i:04d}')
  first=['Avery','Daniel','Mira','Jonah','Leila','Chuka','Nadia','Rowan','Sana','Theo']; last=['Okafor','Ibarra','Voss','Marlowe','Chen','Bennett','Kline','Sato']
  for i in range(1,c.num_people+1):
   pid=iid('PER',i); name=f'{first[i%len(first)]} {last[i%len(last)]}'; aliases=[name.replace(' ',' C. ',1)] if r.random()<c.alias_rate else []
   w.people[pid]=Person(canonical_id=pid,canonical_name=name,aliases=aliases,birth_year=1965+r.randrange(35),historical_addresses=[iid('ADDR',1+(i%c.num_addresses))])
  for i in range(1,c.num_organizations+1):
   oid=iid('ORG',i); name=f'{("Meridian","Northstar","Cobalt","Juniper","Palisade","Lattice")[i%6]} {("Industrial Systems","Strategic Holdings","Civic Works","Analytics Group")[i%4]} Ltd'
   w.organizations[oid]=Organization(canonical_id=oid,legal_name=name,aliases=[name[:-4]] if r.random()<c.rename_rate else [],registration_number=f'SYN-REG-{i:05d}',incorporation_date=c.timeline_start+timedelta(days=r.randrange(900)),historical_addresses=[iid('ADDR',1+(i%c.num_addresses))])
  ev=1; rel=1
  def add(s,p,o,dt,attrs=None):
   nonlocal rel; rid=iid('REL',rel); w.relationships.append(Relationship(relationship_id=rid,subject_id=s,predicate=p,object_id=o,valid_from=dt,created_by_event_id=iid('EVENT',ev),attributes=attrs or {})); rel+=1
  for i in range(1,c.num_organizations+1):
   oid=iid('ORG',i); pid=iid('PER',1+(i*7%c.num_people)); dt=c.timeline_start+timedelta(days=(i*37)%1200); add(pid,Predicate.DIRECTOR_OF,oid,dt); w.events.append(Event(event_id=iid('EVENT',ev),event_type='DirectorAppointed',timestamp=dt,payload={'person_id':pid,'organization_id':oid})); ev+=1; add(oid,Predicate.REGISTERED_AT,iid('ADDR',1+(i%c.num_addresses)),c.timeline_start)
   if i>1: add(iid('ORG',max(1,i//2)),Predicate.OWNS,oid,c.timeline_start+timedelta(days=100+i),{'percentage':75.0})
  for i in range(1,c.num_people+1):
   if i%3==0: add(iid('PER',i),Predicate.EMPLOYED_BY,iid('ORG',1+(i%c.num_organizations)),c.timeline_start+timedelta(days=200+i))
  for i in range(1,min(10,c.num_organizations)+1):
   dt=c.timeline_start+timedelta(days=500+i*23); w.events.append(Event(event_id=iid('EVENT',ev),event_type='OrganizationRenamed',timestamp=dt,payload={'organization_id':iid('ORG',i),'new_name':f'Legacy {w.organizations[iid("ORG",i)].legal_name}'})); ev+=1
  for i in range(1,c.num_people+1):
   if i % 4 == 0:
    dt=c.timeline_start+timedelta(days=700+i*11); w.events.append(Event(event_id=iid('EVENT',ev),event_type='AddressChanged',timestamp=dt,payload={'person_id':iid('PER',i),'address_id':iid('ADDR',1+(i*3%c.num_addresses))})); ev+=1
  for i in range(1,c.num_organizations+1):
   if i % 2 == 0:
    dt=c.timeline_start+timedelta(days=900+i*7); w.events.append(Event(event_id=iid('EVENT',ev),event_type='OrganizationDissolved',timestamp=dt,payload={'organization_id':iid('ORG',i)})); ev+=1
  # Add a deterministic dense relationship layer so reference worlds exercise graph traversal.
  for i in range(1,c.num_organizations+1):
   for hop in range(1,5):
    j=((i+hop*7-1)%c.num_people)+1
    add(iid('PER',j),Predicate.AFFILIATED_WITH,iid('ORG',i),c.timeline_start+timedelta(days=300+hop*17+i))
  for i in range(1,c.num_organizations+1):
   for phase in range(2):
    dt=c.timeline_start+timedelta(days=1200+phase*600+i*5); w.events.append(Event(event_id=iid('EVENT',ev),event_type='OwnershipTransferred',timestamp=dt,payload={'organization_id':iid('ORG',i),'from_person_id':iid('PER',1+(i%c.num_people)),'to_person_id':iid('PER',1+((i+phase+11)%c.num_people)),'percentage':25.0})); ev+=1
  w.metadata={'generator_version':'0.3.0','config':c.model_dump(mode='json')}; w.validate(); return w
def validate_world(w):
 try: w.validate(); return []
 except AssertionError as e: return [str(e) or 'world validation failed']
