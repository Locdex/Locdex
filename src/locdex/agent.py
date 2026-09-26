from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any

from .agent_tools import TOOL_DESCRIPTIONS, ToolError, execute_tool
from .config import LocalModelConfig, load_local_model_config
from .local_runtime import get_runtime
from .planner import record_usage

MUTATING_GIT_TOOLS = {"git_add", "git_commit", "git_pull", "git_push"}
WORKSPACE_MUTATING_TOOLS = {"write_file", "replace_in_file", "delete_path"}
SUBSTANTIVE_INSPECTION_TOOLS = {"read_file", "search_code"}

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

# For very small repositories, deterministic context gathering is cheaper and
# more reliable than asking a tiny local model to discover the project itself.
SMALL_REPO_MAX_FILES = 8
SMALL_REPO_MAX_TOTAL_BYTES = 64 * 1024


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


def _has_substantive_inspection(tool_calls: list[dict[str, Any]]) -> bool:
    for call in tool_calls:
        if call.get("tool") not in SUBSTANTIVE_INSPECTION_TOOLS:
            continue
        result = call.get("result")
        if isinstance(result, dict) and "error" not in result:
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


def _last_successful_mutation_index(tool_calls: list[dict[str, Any]]) -> int | None:
    last_index: int | None = None
    for index, call in enumerate(tool_calls):
        if call.get("tool") not in WORKSPACE_MUTATING_TOOLS:
            continue
        result = call.get("result")
        if isinstance(result, dict) and result.get("ok") is True:
            last_index = index
    return last_index


def _progress_message(tool_name: str, args: dict[str, Any]) -> str:
    if tool_name == "list_files":
        return "[Agent] Inspecting workspace files..."
    if tool_name == "read_file":
        return f"[Agent] Reading {args.get('path', 'file')}..."
    if tool_name == "search_code":
        query = str(args.get("query", ""))
        return f"[Agent] Searching code for {query!r}..."
    if tool_name == "write_file":
        return f"[Agent] Writing {args.get('path', 'file')}..."
    if tool_name == "replace_in_file":
        return f"[Agent] Editing {args.get('path', 'file')}..."
    if tool_name == "delete_path":
        return f"[Agent] Deleting {args.get('path', 'path')}..."
    if tool_name == "run_tests":
        return "[Agent] Running tests..."
    if tool_name == "run_command":
        argv = args.get("argv")
        if isinstance(argv, list):
            command = shlex.join(str(part) for part in argv)
            return f"[Agent] Running: {command}"
        return "[Agent] Running command..."
    if tool_name == "git_status":
        return "[Agent] Checking Git status..."
    if tool_name == "git_diff":
        return "[Agent] Inspecting Git diff..."
    if tool_name == "git_add":
        return "[Agent] Staging requested changes..."
    if tool_name == "git_commit":
        return "[Agent] Creating requested commit..."
    if tool_name == "git_pull":
        return "[Agent] Pulling requested changes..."
    if tool_name == "git_push":
        return "[Agent] Pushing requested commits..."
    return f"[Agent] Running tool: {tool_name}..."


def _print_tool_result(tool_name: str, result: dict[str, Any]) -> None:
    if "error" in result:
        print(f"[Agent] ✗ {tool_name} failed: {result['error']}")
        return

    if tool_name in {"write_file", "replace_in_file", "delete_path"} and result.get("ok") is True:
        path = result.get("path")
        print(f"[Agent] ✓ Updated {path or 'workspace'}.")
        return

    if tool_name in {"run_tests", "run_command"}:
        if result.get("ok") is True:
            print("[Agent] ✓ Command passed.")
        else:
            code = result.get("returncode")
            suffix = f" (exit {code})" if code is not None else ""
            print(f"[Agent] ✗ Command failed{suffix}; result added to context.")
        return

    if result.get("ok") is True:
        print(f"[Agent] ✓ {tool_name} completed.")


def _run_tool(
    repo_path: str,
    task: str,
    tool_name: str,
    tool_args: dict[str, Any],
) -> dict[str, Any]:
    print(_progress_message(tool_name, tool_args))
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

    _print_tool_result(tool_name, result)
    return result


def _append_tool_result(
    messages: list[dict[str, str]],
    tool_name: str,
    result: dict[str, Any],
) -> None:
    messages.append(
        {
            "role": "user",
            "content": f"TOOL RESULT for {tool_name}:\n{json.dumps(result, ensure_ascii=False)[:24000]}",
        }
    )


def _small_repo_paths(repo_path: str, files: list[str]) -> list[str]:
    if not files or len(files) > SMALL_REPO_MAX_FILES:
        return []

    root = Path(repo_path).resolve()
    total = 0
    accepted: list[str] = []

    for relative in files:
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            return []
        if not candidate.is_file():
            continue
        try:
            size = candidate.stat().st_size
        except OSError:
            return []
        total += size
        if total > SMALL_REPO_MAX_TOTAL_BYTES:
            return []
        accepted.append(relative)

    return accepted


def _bootstrap_context(
    task: str,
    repo_path: str,
    messages: list[dict[str, str]],
    bootstrap_calls: list[dict[str, Any]],
    requests_validation: bool,
) -> bool:
    """Gather deterministic evidence before spending model generations.

    Returns True when the whole small repository was pre-read.
    """
    print("[Agent] Preparing workspace evidence...")

    list_args: dict[str, Any] = {"path": ".", "limit": 200}
    list_result = _run_tool(repo_path, task, "list_files", list_args)
    bootstrap_calls.append({"tool": "list_files", "args": list_args, "result": list_result})
    _append_tool_result(messages, "list_files", list_result)

    files = list_result.get("files") if isinstance(list_result, dict) else None
    small_paths = _small_repo_paths(repo_path, files if isinstance(files, list) else [])

    if small_paths:
        print(f"[Agent] Small workspace detected ({len(small_paths)} files); pre-reading project...")
        for path in small_paths:
            read_args: dict[str, Any] = {"path": path, "start_line": 1, "end_line": 400}
            read_result = _run_tool(repo_path, task, "read_file", read_args)
            bootstrap_calls.append({"tool": "read_file", "args": read_args, "result": read_result})
            _append_tool_result(messages, "read_file", read_result)

    if requests_validation:
        test_args: dict[str, Any] = {}
        test_result = _run_tool(repo_path, task, "run_tests", test_args)
        bootstrap_calls.append({"tool": "run_tests", "args": test_args, "result": test_result})
        _append_tool_result(messages, "run_tests", test_result)

    return bool(small_paths)


def _append_premature_final_feedback(
    messages: list[dict[str, str]],
    decision: dict[str, Any],
    reason: str,
) -> None:
    print(f"[Agent] Completion deferred: {reason}")
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


def _append_escalation_feedback(
    messages: list[dict[str, str]],
    decision: dict[str, Any],
    small_repo: bool,
) -> None:
    if small_repo:
        reason = (
            "This is a small workspace whose files and test evidence are already in context. "
            "Attempt the minimal concrete fix locally before escalating."
        )
    else:
        reason = (
            "Do not escalate yet. Read or search relevant source code first, then attempt the "
            "smallest plausible local fix."
        )

    print(f"[Agent] Escalation deferred: {reason}")
    messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
    messages.append({"role": "user", "content": reason})


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


def _system_prompt(extra_context: str, model_key: str) -> str:
    tool_text = "\n".join(f"- {name}: {desc}" for name, desc in TOOL_DESCRIPTIONS.items())
    smoke_hint = ""
    if model_key == "smoke":
        smoke_hint = (
            "\nSMOKE MODEL MODE: Prefer direct, minimal tool actions over broad planning. "
            "If the workspace is tiny and its files/test output are supplied, solve the concrete "
            "local problem rather than describing the repository as complex.\n"
        )

    return f"""You are Locdex, an autonomous coding agent working directly in the user's current workspace.

You should behave like a modern terminal coding agent: inspect the repository, edit files in place, run commands/tests, inspect diffs, and continue until the user's task is complete. File edits made with tools are REAL and immediate. Do not merely describe code changes when you can make them.
{smoke_hint}
Available tools:
{tool_text}

Operating rules:
1. Inspect relevant files before editing. Never claim you inspected something you did not read/search.
2. For code tasks, use write_file or replace_in_file to make the requested changes directly in the workspace.
3. After editing, run the most relevant tests/checks you can reasonably detect. Use git_diff/status to inspect your work when useful.
4. Do NOT call git_add, git_commit, git_pull, or git_push unless the user's current request explicitly asks for that Git operation.
5. Never access paths outside the workspace. Do not try to read .git internals, virtualenvs, caches, credentials, or secrets.
6. Prefer argv-style run_command calls. Do not invoke privilege escalation or machine power/admin commands.
7. Keep edits scoped to the request. Do not rewrite unrelated files.
8. Never escalate before using the available workspace evidence and attempting a concrete local solution.
9. If the task truly exceeds the local model after inspection and an attempted solution, return action='escalate' with a concise reason.
10. When finished, return action='final' with a concise summary of what you changed, tests/checks run, and any relevant caveat.
11. A final answer is accepted only when tool evidence supports it. For edit/fix tasks, a successful workspace mutation must have occurred. If the user explicitly requested tests/checks, Locdex must observe the requested validation before accepting completion.

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
        {"role": "system", "content": _system_prompt(extra_context, getattr(config, "model_key", ""))},
        {"role": "user", "content": task},
    ]
    tool_calls: list[dict[str, Any]] = []
    bootstrap_calls: list[dict[str, Any]] = []

    requires_change = _task_requires_workspace_change(task)
    requests_validation = _task_requests_validation(task)
    small_repo = _bootstrap_context(task, repo_path, messages, bootstrap_calls, requests_validation)

    # One early escalation is treated as a weak-model planning failure rather than
    # proof that the task truly requires cloud fallback.
    escalation_deferrals_remaining = 1 if requires_change else 0

    for step in range(1, config.max_agent_steps + 1):
        print(f"[Agent] Step {step}/{config.max_agent_steps}: planning next action...")
        decision = runtime.json_completion(messages, AGENT_RESPONSE_SCHEMA)
        record_usage("local")
        action = decision.get("action")

        if action == "final":
            mutated = _successful_workspace_mutation(tool_calls)

            if requires_change and mutated:
                last_mutation = _last_successful_mutation_index(tool_calls)
                post_mutation_calls = tool_calls[(last_mutation + 1):] if last_mutation is not None else []
                validation_attempted, validation_passed, validation_unavailable = _validation_state(
                    post_mutation_calls
                )
            else:
                validation_attempted, validation_passed, validation_unavailable = _validation_state(
                    bootstrap_calls + tool_calls
                )

            if requires_change and not mutated:
                _append_premature_final_feedback(
                    messages,
                    decision,
                    "the request requires a workspace change, but no successful write/edit/delete tool has run.",
                )
                continue

            if requests_validation and not validation_attempted:
                _append_premature_final_feedback(
                    messages,
                    decision,
                    "the user explicitly requested tests/checks, but no validation command has been attempted.",
                )
                continue

            if requests_validation and validation_attempted and not (validation_passed or validation_unavailable):
                _append_premature_final_feedback(
                    messages,
                    decision,
                    "the requested validation has not passed yet.",
                )
                continue

            print("[Agent] ✓ Task evidence satisfied.")
            return {
                "status": "completed",
                "confidence": float(decision.get("confidence", 0.85)),
                "summary": str(decision.get("summary", "Task completed.")),
                "steps": step,
                "tool_calls": tool_calls,
            }

        if action == "escalate":
            should_defer = escalation_deferrals_remaining > 0
            if not _has_substantive_inspection(bootstrap_calls + tool_calls) and requires_change:
                should_defer = True

            if should_defer:
                escalation_deferrals_remaining = max(0, escalation_deferrals_remaining - 1)
                _append_escalation_feedback(messages, decision, small_repo)
                continue

            reason = str(decision.get("reason") or decision.get("summary") or "Local agent requested escalation.")
            print(f"[Agent] Local escalation requested: {reason}")
            return {
                "status": "escalate",
                "confidence": float(decision.get("confidence", 0.0)),
                "summary": reason,
                "steps": step,
                "tool_calls": tool_calls,
            }

        if action != "tool":
            print("[Agent] Model returned an invalid protocol action; retrying...")
            messages.append(
                {"role": "user", "content": "Protocol error: choose action 'tool', 'final', or 'escalate'."}
            )
            continue

        tool_name = str(decision.get("tool", ""))
        tool_args = decision.get("args") if isinstance(decision.get("args"), dict) else {}
        result = _run_tool(repo_path, task, tool_name, tool_args)

        tool_calls.append({"tool": tool_name, "args": tool_args, "result": result})
        messages.append({"role": "assistant", "content": json.dumps(decision, ensure_ascii=False)})
        _append_tool_result(messages, tool_name, result)

    print(f"[Agent] Step budget exhausted after {config.max_agent_steps} local generations.")
    return {
        "status": "incomplete",
        "confidence": 0.0,
        "summary": "Agent step limit reached before it could finish.",
        "steps": config.max_agent_steps,
        "tool_calls": tool_calls,
    }
