from typing import Any
from pydantic import BaseModel,Field
class InvestigationState(BaseModel):
 objective:str=''; local_entities:list[str]=Field(default_factory=list); hypotheses:list[dict[str,Any]]=Field(default_factory=list); claims:list[dict[str,Any]]=Field(default_factory=list); evidence:list[str]=Field(default_factory=list); contradictions:list[str]=Field(default_factory=list); unresolved_questions:list[str]=Field(default_factory=list); confidence:float=0.0; remaining_budget:dict[str,int]=Field(default_factory=dict); action_history:list[dict[str,Any]]=Field(default_factory=list)
class Action(BaseModel):
 action_type:str; payload:dict[str,Any]=Field(default_factory=dict); rationale:str=''
