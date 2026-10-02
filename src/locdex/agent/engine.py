from __future__ import annotations

from ..context import ContextBudget, ContextCompiler
from ..models import selected_model_key
from ..routing import LearnedRouter, RoutingPolicy, RoutingSession, local_candidates, plan_execution, profile_task
from ..runtime import detect_hardware
from .state import AgentState


class AgentEngine:
    def __init__(self, model_key: str | None = None):
        self.model_key = model_key or selected_model_key()
        self.context = ContextCompiler()
        self.router = LearnedRouter()

    def prepare(self, task: str, repo_path: str, *, cloud_enabled: bool = False, routing_mode: str = "balanced") -> dict:
        state = AgentState(task, phase="retrieve")
        pack = self.context.compile(repo_path, task, ContextBudget(), cloud=cloud_enabled)
        hardware = detect_hardware()
        profile = profile_task(task, repo_path, context_estimate=pack.total_tokens)
        candidates = local_candidates(hardware)
        policy = RoutingPolicy(mode=routing_mode, allow_cloud=cloud_enabled)
        decision = self.router.route(task=profile, models=candidates, policy=policy, session=RoutingSession())
        plan = plan_execution(
            local_model=decision.model,
            cloud_enabled=cloud_enabled,
            complexity="hard" if profile.reasoning_complexity >= .75 else "normal",
        )
        return {
            "state": state,
            "plan": plan,
            "context": pack,
            "task_profile": profile,
            "routing_decision": decision,
            "hardware": hardware,
            "selected_model": self.model_key,
        }
