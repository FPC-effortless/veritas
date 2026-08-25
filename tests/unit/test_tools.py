import pytest
from investigation_world.tools.budget import BudgetManager

def test_tool_costs_and_limits():
 b=BudgetManager(total_cost=4,max_tool_calls=2); b.charge('web_search'); b.charge('registry_search')
 with pytest.raises(ValueError): b.charge('open_page')
