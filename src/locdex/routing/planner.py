from dataclasses import dataclass
from .cost_controller import CostBudget
@dataclass(frozen=True)
class ExecutionPlan:
    route:str; local_model:str; cloud_provider:str|None=None; cloud_model:str|None=None; context_policy:str="minimal"; budget:CostBudget=CostBudget(); reason:str="local-first default"

def plan_execution(*,local_model,cloud_enabled,complexity="normal"):
    if cloud_enabled and complexity in {"hard","architectural"}: return ExecutionPlan("local_then_cloud",local_model,context_policy="minimal",reason="hard task with explicit cloud availability")
    return ExecutionPlan("local",local_model,reason="local-first path")
