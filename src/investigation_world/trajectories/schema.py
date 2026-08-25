from datetime import datetime, timezone
from pydantic import BaseModel, Field
class Trajectory(BaseModel):
    run_id:str; task_id:str; world_id:str; world_seed:int; agent_metadata:dict[str,object]=Field(default_factory=dict); objective:str=''; tool_calls:list[dict]=Field(default_factory=list); actions:list[dict]=Field(default_factory=list); states:list[dict]=Field(default_factory=list); budget_consumption:dict[str,int]=Field(default_factory=dict); final_findings:dict=Field(default_factory=dict); verifier_result:dict=Field(default_factory=dict); failure_labels:list[str]=Field(default_factory=list); runtime_ms:int=0; recorded_at:datetime=Field(default_factory=lambda:datetime.now(timezone.utc))
"}},{
