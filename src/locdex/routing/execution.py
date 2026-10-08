from __future__ import annotations

from typing import Any

from ..agent import AgentEngine
from ..providers.openai_compatible import CloudConfig, OpenAICompatibleSession
from ..sandbox import SandboxMode, profile_for_mode
from ..telemetry.outcome import record_agent_outcome


def _safe_record_outcome(**kwargs: Any) -> None:
    # Telemetry is best-effort and must not change execution behavior.
    try:
        record_agent_outcome(**kwargs)
    except Exception:
        pass


def _escalation_packet(result: dict[str, Any]) -> str:
    verification = result.get("verification") or {}
    attempted = result.get("attempted_files_modified") or result.get("files_modified") or []
    failures = result.get("failures") or []
    return (
        "LOCAL ATTEMPT HANDOFF\n"
        "The local model could not finish. Reuse only this bounded evidence; "
        "retrieve exact current source with tools before editing.\n\n"
        f"status={result.get('status')}\n"
        f"summary={str(result.get('summary', ''))[:1200]}\n"
        f"attempted_files={attempted[:20]}\n"
        f"failures={failures[:8]}\n"
        f"verification={verification}\n"
    )[:6000]


def _should_escalate(result: dict[str, Any]) -> bool:
    if result.get("status") in {"escalate", "incomplete", "error"}:
        return True
    verification = result.get("verification") or {}
    return bool(
        result.get("status") != "completed"
        or verification.get("passed") is False
    )


def execute_with_escalation(
    engine: AgentEngine,
    task: str,
    repo_path: str = ".",
    *,
    max_steps: int = 6,
    routing_mode: str = "balanced",
    permission_controller=None,
    sandbox_mode: str | SandboxMode = SandboxMode.WORKSPACE_WRITE,
    event_bus=None,
    additional_context: str | None = None,
    steering_queue=None,
    progress=None,
    write_scope: list[str] | None = None,
) -> dict[str, Any]:
    local = engine.execute(
        task,
        repo_path,
        max_steps=max_steps,
        routing_mode=routing_mode,
        permission_controller=permission_controller,
        sandbox_mode=sandbox_mode,
        event_bus=event_bus,
        additional_context=additional_context,
        steering_queue=steering_queue,
        progress=progress,
        write_scope=write_scope,
    )
    local["route"] = "local"
    local["escalation_reason"] = None

    _safe_record_outcome(
        task=task,
        repo_path=repo_path,
        result=local,
        model_id=engine.model_key,
        backend="local",
        router_mode=routing_mode,
        escalated=_should_escalate(local),
    )

    if not _should_escalate(local):
        return local

    config = CloudConfig.from_env()
    if not config.enabled:
        local["cloud_escalation"] = {
            "attempted": False,
            "reason": "cloud_not_configured",
        }
        return local

    profile = profile_for_mode(sandbox_mode)
    if not profile.network_access:
        local["cloud_escalation"] = {
            "attempted": False,
            "reason": "sandbox_network_disabled",
        }
        return local

    if steering_queue is not None and bool(
        getattr(steering_queue, "cancelled", False)
    ):
        local["cloud_escalation"] = {
            "attempted": False,
            "reason": "cancelled",
        }
        return local

    cloud_session = OpenAICompatibleSession(config)
    cloud_engine = AgentEngine(model_key=engine.model_key)
    handoff = _escalation_packet(local)
    combined_context = "\n\n".join(
        value
        for value in (additional_context, handoff)
        if value and value.strip()
    )

    if progress is not None:
        progress(
            f"[Router] Escalating to configured cloud model "
            f"{config.provider}/{config.model}."
        )

    cloud = cloud_engine.execute(
        task,
        repo_path,
        max_steps=max_steps,
        routing_mode="quality",
        session=cloud_session,
        permission_controller=permission_controller,
        sandbox_mode=sandbox_mode,
        event_bus=event_bus,
        additional_context=combined_context,
        steering_queue=steering_queue,
        progress=progress,
        write_scope=write_scope,
    )
    cloud["route"] = "cloud"
    cloud["cloud_provider"] = config.provider
    cloud["cloud_model"] = config.model
    cloud["local_attempt"] = {
        "status": local.get("status"),
        "summary": local.get("summary"),
        "verification": local.get("verification"),
        "rolled_back_files": local.get("rolled_back_files") or [],
    }
    cloud["cloud_escalation"] = {
        "attempted": True,
        "reason": str(local.get("status") or "local_failure"),
    }

    _safe_record_outcome(
        task=task,
        repo_path=repo_path,
        result=cloud,
        model_id=config.model,
        backend=config.provider,
        router_mode="quality",
        input_tokens=cloud_session.input_tokens,
        output_tokens=cloud_session.output_tokens,
        latency_ms=cloud_session.latency_ms,
        cost_usd=cloud_session.cost_usd,
        cloud_costs=(
            config.input_cost_per_million,
            config.output_cost_per_million,
        ),
        context_limit=config.context_limit,
        escalated=False,
    )
    return cloud
