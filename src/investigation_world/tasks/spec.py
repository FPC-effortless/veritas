from pydantic import BaseModel, Field
from enum import StrEnum
class TaskFamily(StrEnum):
    ENTITY_RESOLUTION='entity_resolution'; OWNERSHIP='ownership_reconstruction'; TEMPORAL='temporal_reconstruction'; PROVENANCE='provenance'; CONFLICT='conflict_resolution'; DUE_DILIGENCE='due_diligence'
class TaskSpec(BaseModel):
    task_id:str; world_id:str; family:TaskFamily; objective:str; answerable:bool=True; difficulty:dict[str,float]=Field(default_factory=dict); metadata:dict[str,object]=Field(default_factory=dict)
def generate_tasks(world_id:str,count:int=24,seed:int=0):
    return [TaskSpec(task_id=f'TASK-{i+1:06d}',world_id=world_id,family=list(TaskFamily)[(i+seed)%6],objective=f'Investigate synthetic corporate question {i+1}',answerable=((i+seed)%7!=0),difficulty={'candidate_entities':float(2+(i%8))}) for i in range(count)]
