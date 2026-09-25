from __future__ import annotations

from .agent_tools import write_file
from .cloud_fallback import run_cloud
from .local_model import run_local_with_confidence
from .validator import validate_candidate_set


def _apply_cloud_files(repo_path: str, files: list[dict]) -> int:
    applied = 0
    for item in files:
        path = str(item.get("filepath", "")).strip()
        code = item.get("code")
        if path and isinstance(code, str):
            write_file(repo_path, path, code)
            applied += 1
    return applied

def route_task(task: str, task_type: str, context: dict, thresholds: dict) -> dict:
    """Run the local workspace agent first; use configured cloud fallback only on explicit local escalation/failure."""
    repo_path = str(context.get("repo_path", "."))
    print("[Router] Running local agent...")
    try:
        result = run_local_with_confidence(task, context=context)
    except Exception as exc:  # noqa: BLE001
        result = {"status": "escalate", "confidence": 0.0, "summary": f"Local runtime failed: {exc}"}

    if result.get("status") == "completed":
        return {"source": "local", "result": result, "escalation_reason": None}

    print(f"[Router] Local agent did not complete: {result.get('summary', 'unknown reason')}")
    local_reason = "local_requested_escalation" if result.get("status") == "escalate" else "local_incomplete"
    if str(result.get("summary", "")).startswith("Local runtime failed:"):
        local_reason = "local_runtime_failure"
    print("[Router] Trying cloud fallback if configured...")
    cloud_result = run_cloud(task, context)
    files = cloud_result.get("files") or []
    if files:
        validation = validate_candidate_set(repo_path, files)
        if not validation.get("all_pass"):
            return {
                "source": "none",
                "provider": cloud_result.get("provider"),
                "model": cloud_result.get("model"),
                "escalation_reason": "cloud_validation_failure",
                "result": {
                    "status": "incomplete",
                    "confidence": 0.0,
                    "summary": f"Cloud fallback candidate failed validation: {validation.get('message', '')}",
                },
            }
        applied = _apply_cloud_files(repo_path, files)
        return {
            "source": "cloud",
            "provider": cloud_result.get("provider"),
            "model": cloud_result.get("model"),
            "escalation_reason": local_reason,
            "result": {
                "status": "completed",
                "confidence": float(cloud_result.get("confidence", 0.8)),
                "summary": f"Cloud fallback applied {applied} file(s) directly to the workspace.",
                "steps": 1,
                "tool_calls": [],
            },
        }

    return {
        "source": "none",
        "result": result,
        "escalation_reason": "cloud_unavailable" if local_reason else "other",
    }
