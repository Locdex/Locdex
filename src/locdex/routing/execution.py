from __future__ import annotations

from typing import Any

from ..agent import AgentEngine
from ..runtime.llama_cpp import RuntimeExecutionError
from .evidence import collect_cloud_evidence
from ..providers.openai_compatible import CloudConfig, make_cloud_session
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
    sandbox_mode: str | SandboxMode = SandboxMode.WORKSPACE_NETWORK,
    event_bus=None,
    additional_context: str | None = None,
    steering_queue=None,
    progress=None,
    write_scope: list[str] | None = None,
    local_session=None,
) -> dict[str, Any]:
    try:
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
            session=local_session,
        )
    except RuntimeExecutionError as exc:
        # The hardened AgentEngine rolls back its own edits on exceptions.
        # An isolated native timeout must become a result so cloud routing can
        # recover rather than the interactive CLI abandoning the task.
        cancelled = bool(
            steering_queue is not None
            and getattr(steering_queue, "cancelled", False)
        )
        timeout = "timed out" in str(exc).lower()
        restored = list(getattr(engine, "_last_failure_rollback", []) or [])
        local = {
            "status": "cancelled" if cancelled else "error",
            "model": engine.model_key,
            "summary": (
                "Local inference cancelled by the user."
                if cancelled
                else str(exc)[:500]
            ),
            "steps": 0,
            "files_modified": [],
            "rolled_back_files": restored,
            "rollback_performed": bool(restored),
            "verification": {},
            "verification_attempts": 0,
            "failure_class": (
                "cancelled" if cancelled else "inference_timeout" if timeout else "runtime_error"
            ),
        }
        if progress is not None:
            progress(
                "[Router] Local inference cancelled."
                if cancelled
                else "[Router] Local inference timed out; checking cloud fallback."
                if timeout
                else "[Router] Local runtime failed; checking cloud fallback."
            )

    local["route"] = "local"
    local["escalation_reason"] = local.get("failure_class")

    _safe_record_outcome(
        task=task,
        repo_path=repo_path,
        result=local,
        model_id=engine.model_key,
        backend="local",
        router_mode=routing_mode,
        escalated=_should_escalate(local),
    )

    if local.get("status") == "cancelled" or (
        steering_queue is not None
        and bool(getattr(steering_queue, "cancelled", False))
    ):
        local["cloud_escalation"] = {"attempted": False, "reason": "cancelled"}
        return local

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

    if local_session is not None:
        closer = getattr(local_session, "close", None)
        if callable(closer):
            closer()  # free local model memory before cloud escalation
    # Collect bounded context on the local computer before any paid network
    # request. The cloud model receives a targeted evidence pack rather than
    # a raw repository inventory. Cloud still uses normal tool calls to reread
    # exact source when necessary.
    if progress is not None:
        progress("[Router] Collecting relevant repository evidence locally before cloud request.")
    handoff = _escalation_packet(local)
    try:
        evidence = collect_cloud_evidence(
            repo_path,
            task,
            context_limit=config.context_limit,
            local_failure=handoff,
            prior_session=additional_context or "",
        )
    except Exception as exc:
        local["cloud_escalation"] = {
            "attempted": False,
            "reason": "evidence_collection_failed",
            "failure_type": type(exc).__name__,
        }
        if progress is not None:
            progress("[Router] Cloud preparation stopped: local evidence collection failed.")
        return local
    if not evidence.text.strip() or not evidence.sections:
        local["cloud_escalation"] = {
            "attempted": False,
            "reason": "insufficient_local_evidence",
        }
        return local
    combined_context = evidence.text
    local["cloud_evidence"] = {
        "estimated_tokens": evidence.tokens,
        "sections": list(evidence.sections),
        "redactions": evidence.redactions,
    }
    cloud_session = make_cloud_session(config)
    cloud_engine = AgentEngine(model_key=engine.model_key)

    if progress is not None:
        progress(
            f"[Router] Escalating to configured cloud model "
            f"{config.provider}/{config.model}."
        )

    try:
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
    except Exception as exc:
        # Hardened cloud execution rolls back its own edits on exceptions.
        # Never surface HTTP authorization details or cloud API credentials.
        local["cloud_escalation"] = {
            "attempted": True,
            "reason": "cloud_execution_failed",
            "failure_type": type(exc).__name__[:60],
        }
        if progress is not None:
            progress("[Router] Cloud fallback failed; returning local failure.")
        return local
    if cloud.get("status") == "completed":
        # Interactive checkpoint/undo must use the journal that actually
        # produced the edits, not the rolled-back local attempt's journal.
        journal = getattr(cloud_engine, "change_journal", None)
        if journal is not None:
            engine.change_journal = journal
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
        "reason": str(local.get("failure_class") or local.get("status") or "local_failure"),
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
