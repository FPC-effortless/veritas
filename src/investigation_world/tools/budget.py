from investigation_world.core.models import InvestigationBudget
TOOL_COSTS={'web_search':1,'open_page':1,'registry_search':3,'registry_record':2,'news_search':1,'document_search':2,'archive_lookup':4}
class BudgetManager:
 def __init__(self,total_cost=40,max_tool_calls=30): self.budget=InvestigationBudget(total_cost=total_cost,max_tool_calls=max_tool_calls)
 def charge(self,tool:str): self.budget.charge(TOOL_COSTS.get(tool,1)); return self.budget
 def snapshot(self): return self.budget.model_dump()
