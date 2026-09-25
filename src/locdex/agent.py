from __future__ import annotations

import json
from typing import Any

from .agent_tools import TOOL_DESCRIPTIONS, ToolError, execute_tool
from .config import LocalModelConfig, load_local_model_config
from .local_runtime import get_runtime

MUTATING_GIT_TOOLS = {"git_add", "git_commit", "git_pull", "git_push"}

def _git_tool_allowed(task: str, tool_name: str) -> bool:
    text = task.lower()
    if "ship it" in text or text.strip() == "ship":
        return tool_name in {"git_add", "git_commit", "git_push"}
    keywords = {
        "git_add": ("git add", "stage ", "stage these", "stage the", "add these changes", "add changes"),
        "git_commit": ("commit",),
        "git_pull": ("git pull", "pull latest", "pull from", "sync from remote", "sync with remote"),
        "git_push": ("git push", "push", "publish branch"),
    }
    return any(phrase in text for phrase in keywords.get(tool_name, ()))

AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["tool", "final", "escalate"]},
        "tool": {"type": "string"},
        "args": {"type": "object"},
        "summary": {"type": "string"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "reason": {"type": "string"},
    },
    "required": ["action"],
}


def _system_prompt(extra_context: str) -> str:
    tool_text = "\n".join(f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items())
    return f"""You are Locdex, an autonomous coding agent working directly in the user's current workspace.

You should behave like a modern terminal coding agent: inspect the repository, edit files in place, run commands/tests, inspect diffs, and continue until the user's task is complete. File edits made with tools are REAL and immediate. Do not merely describe code changes when you can make them.

Available tools:
{tool_text}

Operating rules:
1. Inspect relevant files before editing. Never claim you inspected something you did not read/search.
2. For code tasks, use write_file or replace_in_file to make the requested changes directly in the workspace.
3. After editing, run the most relevant tests/checks you can reasonably detect. Use git_diff/status to inspect your work when useful.
4. Do NOT call git_add, git_commit, git_pull, or git_push unless the user's current request explicitly asks for that Git operation (e.g. 'commit this', 'pull latest', 'push it', 'add these files'). Editing code alone is not permission to commit or push.
5. Never access paths outside the workspace. Do not try to read .git internals, virtualenvs, caches, credentials, or secrets.
6. Prefer argv-style run_command calls. Do not invoke privilege escalation or machine power/admin commands.
7. Keep edits scoped to the request. Do not rewrite unrelated files.
8. If the task truly exceeds the local model after inspection, return action='escalate' with a concise reason. Do not escalate just because the task is large.
9. When finished, return action='final' with a concise summary of what you changed, tests/checks run, and any relevant caveat. Do not include giant code dumps in final.

WORKSPACE CONTEXT:
{extra_context}
"""


def run_agent(
    task: str,
    repo_path: str = ".",
    context: dict | None = None,
    config: LocalModelConfig | None = None,
) -> dict:
    config = config or load_local_model_config()
    runtime = get_runtime(config)
    extra_context = (context or {}).get("system_prompt", "")

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _system_prompt(extra_context)},
        {"role": "user", "content": task},
    ]
    tool_calls: list[dict[str, Any]] = []

    for step in range(1, config.max_agent_steps + 1):
        decision = runtime.json_completion(messages, AGENT_RESPONSE_SCHEMA)
        action = decision.get("action")

        if action == "final":
            return {
                "status": "completed",
                "confidence": float(decision.get("confidence", 0.85)),
                "summary": str(decision.get("summary", "Task completed.")),
                "steps": step,
                "tool_calls": tool_calls,
            }

        if action == "escalate":
            return {
                "status": "escalate",
                "confidence": float(decision.get("confidence", 0.0)),
                "summary": str(decision.get("reason") or decision.get("summary") or "Local agent requested escalation."),
                "steps": step,
                "tool_calls": tool_calls,
            }

        if action != "tool":
            messages.append({"role": "user", "content": "Protocol error: choose action 'tool', 'final', or 'escalate'."})
            continue

        tool_name = str(decision.get("tool", ""))
        tool_args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
        try:
            if tool_name in MUTATING_GIT_TOOLS and not _git_tool_allowed(task, tool_name):
                raise ToolError(
                    f"{tool_name} requires an explicit Git instruction from the user in the current request."
                )
            result = execute_tool(repo_path, tool_name, tool_args)
        except ToolError as exc:
            result = {"error": str(exc)}
        except Exception as exc:  # noqa: BLE001
            result = {"error": f"Tool execution failed: {exc}"}

        tool_calls.append({"tool": tool_name, "args": tool_args, "result": result})
        messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        messages.append({
            "role": "user",
            "content": f"TOOL RESULT for {tool_name}:\n{json.dumps(result, ensure_ascii=False)[:24000]}",
        })

    return {
        "status": "incomplete",
        "confidence": 0.0,
        "summary": "Agent step limit reached before it could finish.",
        "steps": config.max_agent_steps,
        "tool_calls": tool_calls,
    }
