from __future__ import annotations

from typing import Any

from ..models import get_model_profile
from ..routing.catalog import cloud_candidate
from ..routing.model_profile import from_local_profile
from ..routing.policy import RoutingPolicy
from ..routing.router import LearnedRouter
from ..routing.session import RoutingSession
from ..routing.task_profile import profile_task
from ..runtime import detect_hardware
from .events import build_routing_event
from .queue import enqueue
from .settings import enabled


def _verification_flags(result: dict[str, Any]) -> dict[str, bool | None]:
    flags: dict[str, bool | None] = {
        "compile_passed": None,
        "tests_passed": None,
        "lint_passed": None,
        "validator_passed": None,
    }
    verification = result.get("verification") or {}
    checks = verification.get("checks") or []
    for check in checks:
        if not isinstance(check, dict):
            continue
        name = str(check.get("name", "")).lower()
        status = str(check.get("status", "")).lower()
        passed = status == "passed"
        if "compile" in name:
            flags["compile_passed"] = passed
        elif "test" in name:
            flags["tests_passed"] = passed
        elif "lint" in name or "ruff" in name:
            flags["lint_passed"] = passed
        elif "validator" in name:
            flags["validator_passed"] = passed

    if flags["validator_passed"] is None:
        overall = verification.get("passed")
        if overall is not None:
            flags["validator_passed"] = bool(overall)
    return flags


def record_agent_outcome(
    *,
    task: str,
    repo_path: str,
    result: dict[str, Any],
    model_id: str,
    backend: str,
    router_mode: str,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    latency_ms: float | None = None,
    cost_usd: float | None = None,
    cloud_costs: tuple[float, float] = (0.0, 0.0),
    context_limit: int = 128000,
    escalated: bool = False,
) -> bool:
    if not enabled():
        return False

    hardware = detect_hardware()
    context_tokens = int(result.get("context_tokens_before") or 0)
    task_profile = profile_task(
        task,
        repo_path,
        context_estimate=context_tokens,
    )

    if backend == "local":
        model = from_local_profile(get_model_profile(model_id))
        policy = RoutingPolicy(mode=router_mode, allow_cloud=False)
    else:
        model = cloud_candidate(
            provider=backend,
            model_id=model_id,
            input_cost=cloud_costs[0],
            output_cost=cloud_costs[1],
            context_limit=context_limit,
        )
        policy = RoutingPolicy(
            mode=router_mode,
            allow_cloud=True,
            allowed_providers=(backend,),
        )

    decision = LearnedRouter().route(
        task=task_profile,
        models=[model],
        policy=policy,
        session=RoutingSession(),
    )

    calls = result.get("tool_calls") or []
    edit_attempts = sum(
        1
        for call in calls
        if isinstance(call, dict)
        and str(call.get("tool", ""))
        in {
            "write_file",
            "replace_in_file",
            "replace_symbol",
            "insert_after_symbol",
            "delete_path",
        }
    )
    flags = _verification_flags(result)
    event = build_routing_event(
        task=task_profile,
        decision=decision,
        hardware=hardware,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
        tool_calls=len(calls),
        edit_attempts=edit_attempts,
        escalated=escalated,
        user_reverted=bool(result.get("rollback_performed")),
        router_mode=router_mode,
        actual_cost=cost_usd,
        **flags,
    )
    enqueue(event.to_dict())
    return True
