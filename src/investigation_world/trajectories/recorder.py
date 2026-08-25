from time import perf_counter
from .schema import Trajectory
from .exporter import failure_labels
class TrajectoryRecorder:
 def __init__(self,run_id,task_id,world_id,world_seed,objective='',agent_metadata=None):
  self.started=perf_counter(); self.t=Trajectory(run_id=run_id,task_id=task_id,world_id=world_id,world_seed=world_seed,objective=objective,agent_metadata=agent_metadata or {})
 def tool_call(self,tool,observation): self.t.tool_calls.append({'tool':tool,'observation':observation})
 def action(self,action): self.t.actions.append(action)
 def state(self,state): self.t.states.append(state)
 def finish(self,findings,verifier_result,budget):
  self.t.final_findings=findings; self.t.verifier_result=verifier_result; self.t.budget_consumption=budget; self.t.failure_labels=failure_labels(verifier_result); self.t.runtime_ms=round((perf_counter()-self.started)*1000); return self.t
