from __future__ import annotations
from datetime import date
from enum import StrEnum
from pydantic import BaseModel, Field, ConfigDict

class Predicate(StrEnum):
    OWNS="OWNS"; CONTROLS="CONTROLS"; DIRECTOR_OF="DIRECTOR_OF"; EMPLOYED_BY="EMPLOYED_BY"; REGISTERED_AT="REGISTERED_AT"; SUBSIDIARY_OF="SUBSIDIARY_OF"; FORMERLY_NAMED="FORMERLY_NAMED"; AFFILIATED_WITH="AFFILIATED_WITH"
class TruthStatus(StrEnum):
    TRUE="true"; FALSE="false"; PARTIALLY_TRUE="partially_true"; OUTDATED="outdated"; UNKNOWN="unknown"
class Entity(BaseModel):
    model_config=ConfigDict(extra="forbid")
    canonical_id:str; metadata:dict[str,object]=Field(default_factory=dict)
class Person(Entity):
    canonical_name:str; aliases:list[str]=Field(default_factory=list); birth_year:int|None=None; historical_addresses:list[str]=Field(default_factory=list); identifiers:dict[str,str]=Field(default_factory=dict); affiliations:list[str]=Field(default_factory=list)
class Organization(Entity):
    legal_name:str; aliases:list[str]=Field(default_factory=list); registration_number:str; incorporation_date:date; dissolution_date:date|None=None; organization_type:str="company"; historical_addresses:list[str]=Field(default_factory=list); status:str="active"
class Address(Entity):
    synthetic_line:str; city:str; region:str; postal_code:str
class Domain(Entity):
    hostname:str; organization_id:str
class Relationship(BaseModel):
    model_config=ConfigDict(extra="forbid")
    relationship_id:str; subject_id:str; predicate:Predicate; object_id:str; valid_from:date; valid_to:date|None=None; created_by_event_id:str|None=None; ended_by_event_id:str|None=None; attributes:dict[str,object]=Field(default_factory=dict)
class Event(BaseModel):
    event_id:str; event_type:str; timestamp:date; payload:dict[str,object]
class Claim(BaseModel):
    claim_id:str; subject_id:str; predicate:Predicate; object_id:str|None=None; value:object|None=None; valid_from:date|None=None; valid_to:date|None=None; truth_status:TruthStatus; origin_source_id:str; parent_claim_ids:list[str]=Field(default_factory=list); metadata:dict[str,object]=Field(default_factory=dict)
class Source(BaseModel):
    source_id:str; name:str; source_type:str; reliability_baseline:float=0.5; metadata:dict[str,object]=Field(default_factory=dict)
class Document(BaseModel):
    document_id:str; source_id:str; title:str; body:str; published_at:date; entity_ids:list[str]=Field(default_factory=list); claim_ids:list[str]=Field(default_factory=list); cites_document_ids:list[str]=Field(default_factory=list); url:str|None=None
class PublicDocument(BaseModel):
    document_id:str; title:str; body:str; published_at:date; source_type:str; url:str|None=None
class CanonicalWorld(BaseModel):
    world_id:str; seed:int; people:dict[str,Person]=Field(default_factory=dict); organizations:dict[str,Organization]=Field(default_factory=dict); addresses:dict[str,Address]=Field(default_factory=dict); domains:dict[str,Domain]=Field(default_factory=dict); relationships:list[Relationship]=Field(default_factory=list); events:list[Event]=Field(default_factory=list); claims:list[Claim]=Field(default_factory=list); sources:list[Source]=Field(default_factory=list); documents:list[Document]=Field(default_factory=list); metadata:dict[str,object]=Field(default_factory=dict)
    def relationships_at(self, timestamp:date): return [r for r in self.relationships if r.valid_from<=timestamp and (r.valid_to is None or timestamp<=r.valid_to)]
    def entity_state_at(self, entity_id:str, timestamp:date): return [r for r in self.relationships_at(timestamp) if r.subject_id==entity_id or r.object_id==entity_id]
    def public_documents(self): return [PublicDocument(document_id=d.document_id,title=d.title,body=d.body,published_at=d.published_at,source_type=next((s.source_type for s in self.sources if s.source_id==d.source_id),"unknown"),url=d.url) for d in self.documents]

class InvestigationBudget(BaseModel):
    total_cost:int=40; max_tool_calls:int=30; spent:int=0; calls:int=0
    def charge(self,cost:int):
        if self.calls>=self.max_tool_calls or self.spent+cost>self.total_cost: raise ValueError("investigation budget exhausted")
        self.calls+=1; self.spent+=cost
class InvestigationResult(BaseModel):
    entities:list[dict]=Field(default_factory=list); identity_assertions:list[dict]=Field(default_factory=list); relationships:list[dict]=Field(default_factory=list); claims:list[dict]=Field(default_factory=list); evidence:list[dict]=Field(default_factory=list); unknowns:list[str]=Field(default_factory=list); conclusion:str=""; overall_confidence:float=0.0

