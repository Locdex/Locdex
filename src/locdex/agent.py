from __future__ import annotations

import json
from typing import Any

from .agent_tools import TOOL_DESCRIPTIONS, ToolError, execute_tool
from .config import LocalModelConfig, load_local_model_config
from .local_runtime import get_runtime
from .planner import record_usage

MUTATING_GIT_TOOLS = {"git_add", "git_commit", "git_pull", "git_push"}
WORKSPACE_MUTATING_TOOLS = {"write_file", "replace_in_file", "delete_path"}

_CHANGE_KEYWORDS = (
    "fix",
    "correct",
    "change",
    "edit",
    "modify",
    "update",
    "implement",
    "add",
    "remove",
    "delete",
    "create",
    "write",
    "refactor",
    "rename",
)

_VALIDATION_KEYWORDS = (
    "test",
    "tests",
    "pytest",
    "unittest",
    "check",
    "checks",
    "lint",
    "verify",
    "validation",
)

_TEST_COMMAND_MARKERS = {
    "pytest",
    "unittest",
    "test",
    "tests",
    "jest",
    "vitest",
    "mocha",
    "cargo",
    "go",
}


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


def _task_requires_workspace_change(task: str) -> bool:
    text = task.lower()
    return any(keyword in text for keyword in _CHANGE_KEYWORDS)


def _task_requests_validation(task: str) -> bool:
    text = task.lower()
    return any(keyword in text for keyword in _VALIDATION_KEYWORDS)


def _successful_workspace_mutation(tool_calls: list[dict[str, Any]]) -> bool:
    for call in tool_calls:
        if call.get("tool") not in WORKSPACE_MUTATING_TOOLS:
            continue
        result = call.get("result")
        if isinstance(result, dict) and result.get("ok") is True:
            return True
    return False


def _looks_like_validation_call(call: dict[str, Any]) -> bool:
    tool = str(call.get("tool", ""))
    if tool == "run_tests":
        return True
    if tool != "run_command":
        return False

    args = call.get("args")
    if not isinstance(args, dict):
        return False
    argv = args.get("argv")
    if not isinstance(argv, list):
        return False

    normalized = {str(part).lower() for part in argv}
    return bool(normalized & _TEST_COMMAND_MARKERS)


def _validation_state(tool_calls: list[dict[str, Any]]) -> tuple[bool, bool, bool]:
    """Return (attempted, passed, unavailable)."""
    attempted = False
    passed = False
    unavailable = False

    for call in tool_calls:
        if not _looks_like_validation_call(call):
            continue

        attempted = True
        result = call.get("result")
        if not isinstance(result, dict):
            continue

        if result.get("ok") is True:
            passed = True
            continue

        if result.get("returncode") is None and "No supported test runner" in str(result.get("output", "")):
            unavailable = True

    return attempted, passed, unavailable


def _append_premature_final_feedback(
    messages: list[dict[str, str]],
    decision: dict[str, Any],
    reason: str,
) -> None:
    messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
    messages.append(
        {
            "role": "user",
            "content": (
                "You attempted to finish, but Locdex cannot mark this task complete yet. "
                f"{reason} Continue using the available tools. Do not claim work was performed "
                "unless the corresponding tool result proves it."
            ),
        }
    )


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
10. A final answer is accepted only when tool evidence supports it. For edit/fix tasks, a successful workspace mutation must have occurred. If the user explicitly requested tests/checks, Locdex must observe the requested validation before accepting completion.

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

    requires_change = _task_requires_workspace_change(task)
    requests_validation = _task_requests_validation(task)

    for step in range(1, config.max_agent_steps + 1):
        decision = runtime.json_completion(messages, AGENT_RESPONSE_SCHEMA)
        record_usage("local")
        action = decision.get("action")

        if action == "final":
            mutated = _successful_workspace_mutation(tool_calls)
            validation_attempted, validation_passed, validation_unavailable = _validation_state(tool_calls)

            if requires_change and not mutated:
                _append_premature_final_feedback(
                    messages,
                    decision,
                    "The request requires a workspace change, but no successful write/edit/delete tool has run.",
                )
                continue

            if requests_validation and not validation_attempted:
                _append_premature_final_feedback(
                    messages,
                    decision,
                    "The user explicitly requested tests/checks, but no validation command has been attempted.",
                )
                continue

            if requests_validation and validation_attempted and not (validation_passed or validation_unavailable):
                _append_premature_final_feedback(
                    messages,
                    decision,
                    "The requested validation has not passed. Inspect the failure, make any needed correction, and run it again.",
                )
                continue

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
        messages.append(
            {
                "role": "user",
                "content": f"TOOL RESULT for {tool_name}:\n{json.dumps(result, ensure_ascii=False)[:24000]}",
            }
        )

    return {
        "status": "incomplete",
        "confidence": 0.0,
        "summary": "Agent step limit reached before it could finish.",
        "steps": config.max_agent_steps,
        "tool_calls": tool_calls,
    }
