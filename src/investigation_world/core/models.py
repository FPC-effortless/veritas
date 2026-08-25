from __future__ import annotations
from datetime import date
from enum import StrEnum
from typing import Any
from pydantic import BaseModel, Field, ConfigDict

class Predicate(StrEnum):
    OWNS='OWNS'; CONTROLS='CONTROLS'; DIRECTOR_OF='DIRECTOR_OF'; EMPLOYED_BY='EMPLOYED_BY'; REGISTERED_AT='REGISTERED_AT'; SUBSIDIARY_OF='SUBSIDIARY_OF'; FORMERLY_NAMED='FORMERLY_NAMED'; AFFILIATED_WITH='AFFILIATED_WITH'
class TruthStatus(StrEnum):
    TRUE='true'; FALSE='false'; PARTIALLY_TRUE='partially_true'; OUTDATED='outdated'; UNKNOWN='unknown'
class SourceType(StrEnum):
    REGISTRY='registry'; COMPANY_SITE='company_site'; NEWS='news'; FILING='filing'; ARCHIVE='archive'; DIRECTORY='directory'
class Entity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    canonical_id:str; metadata:dict[str,Any]=Field(default_factory=dict)
class Person(Entity):
    canonical_name:str; aliases:list[str]=Field(default_factory=list); birth_year:int|None=None; historical_addresses:list[str]=Field(default_factory=list); identifiers:dict[str,str]=Field(default_factory=dict); affiliations:list[str]=Field(default_factory=list)
class Organization(Entity):
    legal_name:str; aliases:list[str]=Field(default_factory=list); registration_number:str; incorporation_date:date; dissolution_date:date|None=None; organization_type:str='company'; historical_addresses:list[str]=Field(default_factory=list); status:str='active'
class Address(Entity):
    synthetic_line:str; city:str; region:str; postal_code:str
class Domain(Entity):
    hostname:str; organization_id:str
class Relationship(BaseModel):
    model_config=ConfigDict(extra='forbid')
    relationship_id:str; subject_id:str; predicate:Predicate; object_id:str; valid_from:date; valid_to:date|None=None; created_by_event_id:str|None=None; ended_by_event_id:str|None=None; attributes:dict[str,Any]=Field(default_factory=dict)
class Event(BaseModel):
    event_id:str; event_type:str; timestamp:date; payload:dict[str,Any]
class Claim(BaseModel):
    claim_id:str; subject_id:str; predicate:Predicate; object_id:str|None=None; value:Any=None; valid_from:date|None=None; valid_to:date|None=None; truth_status:TruthStatus=TruthStatus.UNKNOWN; origin_source_id:str; parent_claim_ids:list[str]=Field(default_factory=list); metadata:dict[str,Any]=Field(default_factory=dict)
class Source(BaseModel):
    source_id:str; name:str; source_type:SourceType; reliability_baseline:float=.5; metadata:dict[str,Any]=Field(default_factory=dict)
class Document(BaseModel):
    document_id:str; source_id:str; title:str; body:str; published_at:date; entity_ids:list[str]=Field(default_factory=list); claim_ids:list[str]=Field(default_factory=list); cites_document_ids:list[str]=Field(default_factory=list); url:str|None=None; is_stale:bool=False
class PublicDocument(BaseModel):
    document_id:str; title:str; body:str; published_at:date; source_type:SourceType; url:str|None=None; cites_document_ids:list[str]=Field(default_factory=list)
class CanonicalWorld(BaseModel):
    world_id:str; seed:int; people:dict[str,Person]=Field(default_factory=dict); organizations:dict[str,Organization]=Field(default_factory=dict); addresses:dict[str,Address]=Field(default_factory=dict); domains:dict[str,Domain]=Field(default_factory=dict); relationships:list[Relationship]=Field(default_factory=list); events:list[Event]=Field(default_factory=list); claims:list[Claim]=Field(default_factory=list); sources:list[Source]=Field(default_factory=list); documents:list[Document]=Field(default_factory=list); metadata:dict[str,Any]=Field(default_factory=dict)
    def relationships_at(self,timestamp:date): return [r for r in self.relationships if r.valid_from<=timestamp and (r.valid_to is None or timestamp<=r.valid_to)]
    def entity_state_at(self,entity_id:str,timestamp:date): return [r for r in self.relationships_at(timestamp) if r.subject_id==entity_id or r.object_id==entity_id]
    def public_documents(self):
        types={s.source_id:s.source_type for s in self.sources}; return [PublicDocument(document_id=d.document_id,title=d.title,body=d.body,published_at=d.published_at,source_type=types.get(d.source_id,SourceType.DIRECTORY),url=d.url,cites_document_ids=d.cites_document_ids) for d in self.documents]
    def validate(self):
        ids=set(self.people)|set(self.organizations)|set(self.addresses)|set(self.domains)
        assert len(ids)==len(self.people)+len(self.organizations)+len(self.addresses)+len(self.domains)
        for r in self.relationships: assert r.subject_id in ids and r.object_id in ids and (r.valid_to is None or r.valid_from<=r.valid_to)
        assert len({r.relationship_id for r in self.relationships})==len(self.relationships)
        assert len({e.event_id for e in self.events})==len(self.events)
        return True
class InvestigationBudget(BaseModel):
    total_cost:int=40; max_tool_calls:int=30; spent:int=0; calls:int=0
    def charge(self,cost:int):
        if self.calls>=self.max_tool_calls or self.spent+cost>self.total_cost: raise ValueError('investigation budget exhausted')
        self.calls+=1; self.spent+=cost
class InvestigationResult(BaseModel):
    entities:list[dict[str,Any]]=Field(default_factory=list); identity_assertions:list[dict[str,Any]]=Field(default_factory=list); relationships:list[dict[str,Any]]=Field(default_factory=list); claims:list[dict[str,Any]]=Field(default_factory=list); evidence:list[dict[str,Any]]=Field(default_factory=list); unknowns:list[str]=Field(default_factory=list); conclusion:str=''; overall_confidence:float=0.0
class VerificationResult(BaseModel):
    identity:float=0; relationships:float=0; temporal:float=0; evidence_support:float=0; provenance:float=0; calibration:float=0; abstention:float=0; efficiency:float=0; false_merge_count:int=0; unsupported_claim_count:int=0; overall_reward:float=0

def typed_id(prefix:str,n:int)->str: return f'{prefix}-{n:06d}'
