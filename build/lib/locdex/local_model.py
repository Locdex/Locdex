from __future__ import annotations

from .agent import run_agent


def run_local_with_confidence(task: str, system: str = "", context: dict | None = None, **kwargs) -> dict:
    merged = dict(context or {})
    if system:
        existing = str(merged.get("system_prompt", ""))
        merged["system_prompt"] = f"{system}\n\n{existing}".strip()
    return run_agent(task, repo_path=str(merged.get("repo_path", ".")), context=merged)
