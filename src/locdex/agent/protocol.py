from __future__ import annotations

from typing import Any

from ..tools import TOOLS

WORKSPACE_MUTATING_TOOLS = {"write_file", "replace_in_file", "delete_path"}
READ_TOOLS = {"list_files", "read_file", "search_code", "git_status", "git_diff"}
VALIDATION_TOOLS = {"run_tests", "run_command"}
GIT_MUTATING_TOOLS = {"git_add", "git_commit", "git_pull", "git_push"}

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

AGENT_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["tool", "final", "escalate"],
        },
        "tool": {
            "type": "string",
            "enum": sorted(TOOLS),
        },
        "args": {"type": "object"},
        "summary": {"type": "string"},
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
        },
        "reason": {"type": "string"},
    },
    "required": ["action"],
}


def task_requires_workspace_change(task: str) -> bool:
    lowered = task.lower()
    return any(keyword in lowered for keyword in _CHANGE_KEYWORDS)


def git_tool_allowed(task: str, tool_name: str) -> bool:
    text = task.lower()
    if "ship it" in text or text.strip() == "ship":
        return tool_name in {"git_add", "git_commit", "git_push"}

    phrases = {
        "git_add": (
            "git add",
            "stage changes",
            "stage the changes",
            "stage these",
            "commit",
        ),
        "git_commit": ("commit",),
        "git_pull": (
            "git pull",
            "pull latest",
            "pull from",
            "sync from remote",
        ),
        "git_push": (
            "git push",
            "push changes",
            "push commits",
            "publish branch",
        ),
    }
    return any(phrase in text for phrase in phrases.get(tool_name, ()))


def tool_descriptions() -> str:
    return "\n".join(
        f"- {name}: {definition.description}"
        for name, definition in TOOLS.items()
    )


def system_prompt(repo_context: str, model_key: str) -> str:
    smoke_note = ""
    if model_key == "smoke":
        smoke_note = (
            "\nSMOKE MODEL MODE: Keep each step narrow. Read one relevant file, make the smallest "
            "exact edit, validate it, and finish. Avoid broad architectural rewrites.\n"
        )

    return f"""You are Locdex, a local-first coding agent operating directly in the user's repository.
{smoke_note}
Available tools:
{tool_descriptions()}

Rules:
1. Inspect relevant code before changing it.
2. File writes and replacements are real and immediate.
3. Prefer replace_in_file for small existing-file edits and write_file for new files or full rewrites.
4. Keep changes tightly scoped to the user's request.
5. Never access paths outside the workspace or protected internal paths.
6. run_command accepts argv only. Do not attempt shell wrappers, Git through run_command, privilege escalation, networking, or package installation.
7. Git mutations require explicit current-user intent. Do not stage, commit, pull, or push unless the request explicitly asks for it.
8. After a code change, validate with run_tests or a targeted safe command before claiming success.
9. Do not claim an edit/test happened unless a tool result proves it.
10. If the task genuinely cannot be completed locally after inspection and a concrete attempt, use action "escalate".
11. When complete, use action "final" with a concise summary.

Return exactly one schema-valid JSON object per turn.

Repository context:
{repo_context}
"""
