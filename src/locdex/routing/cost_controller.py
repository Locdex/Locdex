from dataclasses import dataclass
@dataclass(frozen=True)
class CostBudget:
    max_task_cost:float|None=None; max_initial_input_tokens:int=8000; max_output_tokens:int=3000; max_total_task_tokens:int=20000

def within_budget(estimated_cost,budget): return estimated_cost is None or budget.max_task_cost is None or estimated_cost<=budget.max_task_cost
