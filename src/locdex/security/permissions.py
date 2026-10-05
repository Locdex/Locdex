from __future__ import annotations

import difflib
import shlex
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .policy import RiskClass


class PermissionMode(str, Enum):
    PLAN = "plan"
    ASK = "ask"
    AUTO_EDIT = "auto-edit"
    TRUSTED = "trusted"
    UNRESTRICTED = "unrestricted"


class ApprovalChoice(str, Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"
    DENY = "deny"


@dataclass(frozen=True)
class PermissionRequest:
    tool: str
    risk: RiskClass
    args: dict[str, Any]
    preview: str
    cache_key: str
    purpose: str = ""
    access: tuple[str, ...] = ()


@dataclass(frozen=True)
class PermissionDecision:
    allowed: bool
    reason: str
    choice: ApprovalChoice | None = None


ApprovalCallback = Callable[[PermissionRequest], ApprovalChoice]


def _safe_workspace_path(repo_path: str, relative: str) -> Path | None:
    root = Path(repo_path).resolve()
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


MAX_PERMISSION_PREVIEW_LINES = 40
MAX_PERMISSION_PREVIEW_CHARS = 4000


def _bounded_text(value: str) -> str:
    lines = value.splitlines()
    truncated = len(lines) > MAX_PERMISSION_PREVIEW_LINES
    rendered = "\n".join(lines[:MAX_PERMISSION_PREVIEW_LINES])
    if len(rendered) > MAX_PERMISSION_PREVIEW_CHARS:
        rendered = rendered[:MAX_PERMISSION_PREVIEW_CHARS]
        truncated = True
    if truncated:
        rendered += "\n... details truncated ..."
    return rendered


def _bounded_diff(
    before: str,
    after: str,
    *,
    path: str,
) -> str:
    lines = list(
        difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
    )
    return _bounded_text("\n".join(lines) or "(no textual diff)")


def _command_text(args: dict[str, Any]) -> str:
    argv = args.get("argv") or []
    if not isinstance(argv, list):
        return "workspace command"
    return shlex.join(str(item) for item in argv)


def build_tool_preview(
    repo_path: str,
    tool: str,
    args: dict[str, Any],
) -> str:
    del repo_path
    path_text = str(args.get("path", "")).replace("\\", "/")

    if tool == "write_file" and path_text:
        content = str(args.get("content", ""))
        excerpt = _bounded_text(content)
        return (
            f"Write {path_text} ({len(content.encode('utf-8'))} bytes)."
            + (f"\n\n{excerpt}" if excerpt else "")
        )

    if tool == "replace_in_file" and path_text:
        old = str(args.get("old", ""))
        new = str(args.get("new", ""))
        return _bounded_diff(old, new, path=path_text)

    if tool == "replace_symbol" and path_text:
        symbol = str(args.get("name", ""))
        new_source = _bounded_text(str(args.get("new_source", "")))
        return (
            f"Replace Python symbol {symbol!r} in {path_text}."
            + (f"\n\n{new_source}" if new_source else "")
        )

    if tool == "insert_after_symbol" and path_text:
        anchor = str(args.get("anchor", ""))
        new_source = _bounded_text(str(args.get("new_source", "")))
        return (
            f"Insert after Python symbol {anchor!r} in {path_text}."
            + (f"\n\n{new_source}" if new_source else "")
        )

    if tool == "delete_path" and path_text:
        return f"Delete workspace path: {path_text}"

    if tool == "run_command":
        return f"Run command:\n  {_bounded_text(_command_text(args))}"

    if tool == "run_tests":
        return "Run the detected project test suite."

    if tool.startswith("git_"):
        details = ", ".join(
            f"{key}={value!r}"
            for key, value in args.items()
            if value not in (None, "", [], {})
        )
        return _bounded_text(
            f"Git action: {tool}"
            + (f"\n{details}" if details else "")
        )

    return _bounded_text(f"Tool: {tool}\nArguments: {args}")


def _shorten(value: str, limit: int = 96) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(1, limit - 1)] + "…"


def format_permission_request(request: PermissionRequest) -> str:
    path = str(request.args.get("path", "")).replace("\\", "/").strip()

    if request.risk is RiskClass.READ:
        target = path or "the workspace"
        return f"Allow Locdex to read {target}?"

    if request.risk is RiskClass.WRITE:
        if request.tool == "delete_path":
            return f"Allow Locdex to delete {path or 'a workspace path'}?"
        return f"Allow Locdex to edit {path or 'workspace files'}?"

    if request.risk is RiskClass.EXECUTE:
        if request.tool == "run_tests":
            return "Allow Locdex to run project tests?"
        if request.tool == "run_command":
            return f"Allow Locdex to run: {_shorten(_command_text(request.args))}?"
        return f"Allow Locdex to run {request.tool}?"

    if request.risk is RiskClass.GIT_WRITE:
        remote = str(request.args.get("remote", "origin")).strip() or "origin"
        if request.tool == "git_commit":
            return "Allow Locdex to create a Git commit?"
        if request.tool == "git_push":
            return f"Allow Locdex to push to {remote}?"
        if request.tool == "git_pull":
            return f"Allow Locdex to pull from {remote}?"
        if request.tool == "git_add":
            return "Allow Locdex to stage Git changes?"
        return f"Allow Locdex to perform {request.tool}?"

    if request.risk is RiskClass.NETWORK:
        server = str(request.args.get("server", "")).strip()
        tool = str(request.args.get("tool", "")).strip()
        target = "/".join(value for value in (server, tool) if value)
        if target:
            return f"Allow Locdex to use external tool {target}?"
        return "Allow Locdex network access for this action?"

    return f"Allow Locdex to use {request.tool}?"


def format_permission_details(request: PermissionRequest) -> str:
    rows = [
        f"Tool: {request.tool}",
        f"Risk: {request.risk.value}",
    ]
    if request.purpose:
        rows.append(f"Reason: {request.purpose}")
    if request.access:
        rows.append("Access: " + ", ".join(request.access))
    if request.preview:
        rows.extend(["", "Details:", request.preview])
    return "\n".join(rows)

def permission_cache_key(
    tool: str,
    risk: RiskClass,
    args: dict[str, Any],
) -> str:
    if risk is RiskClass.WRITE:
        return "risk:write"
    if tool == "run_tests":
        return "tool:run_tests"
    if tool == "run_command":
        argv = args.get("argv") or []
        executable = (
            str(argv[0]).lower()
            if isinstance(argv, list) and argv
            else ""
        )
        return f"run_command:{executable}"
    if risk is RiskClass.GIT_WRITE:
        return f"tool:{tool}"
    if risk is RiskClass.NETWORK:
        return f"tool:{tool}"
    return f"tool:{tool}"


def _request_purpose(
    tool: str,
    risk: RiskClass,
    args: dict[str, Any],
) -> str:
    explicit = str(args.get("reason", "")).strip()
    if explicit:
        return explicit[:240]

    if tool == "run_tests":
        return "Verify the current workspace changes."
    if tool == "run_command":
        argv = args.get("argv") or []
        command = (
            str(argv[0])
            if isinstance(argv, list) and argv
            else "command"
        )
        return f"Run {command} inside the workspace."
    if tool == "git_commit":
        return "Create the Git commit explicitly requested by the user."
    if tool in {"git_pull", "git_push"}:
        return "Perform the requested remote Git operation."
    if risk is RiskClass.WRITE:
        path = str(args.get("path", "")).strip()
        return (
            f"Modify {path}."
            if path
            else "Modify files in the workspace."
        )
    if risk is RiskClass.NETWORK:
        return "Use a network-backed tool requested by the active task."
    if risk is RiskClass.GIT_WRITE:
        return "Mutate Git state for the active task."
    return f"Use {tool} for the active task."


def _request_access(
    tool: str,
    risk: RiskClass,
    args: dict[str, Any],
) -> tuple[str, ...]:
    access: list[str] = ["workspace"]
    path = str(args.get("path", "")).replace("\\", "/").strip()

    if risk is RiskClass.WRITE:
        access.append(
            f"write:{path}" if path else "write:workspace"
        )
    if risk is RiskClass.EXECUTE:
        access.append("execute:local-process")
    if risk is RiskClass.GIT_WRITE:
        access.append("git:mutate")
    if risk is RiskClass.NETWORK:
        access.append("network")
    if tool in {"git_pull", "git_push"}:
        access.append("remote-git")

    return tuple(dict.fromkeys(access))



class PermissionController:
    def __init__(
        self,
        mode: str | PermissionMode = PermissionMode.ASK,
        *,
        approval_callback: ApprovalCallback | None = None,
    ):
        self.mode = PermissionMode(mode)
        self.approval_callback = approval_callback
        self._session_allow: set[str] = set()

    def _base_action(self, risk: RiskClass) -> str:
        if risk is RiskClass.DANGEROUS:
            return "deny"

        if self.mode is PermissionMode.PLAN:
            return "allow" if risk is RiskClass.READ else "deny"

        if self.mode is PermissionMode.ASK:
            return "allow" if risk is RiskClass.READ else "ask"

        if self.mode is PermissionMode.AUTO_EDIT:
            if risk in {RiskClass.READ, RiskClass.WRITE}:
                return "allow"
            return "ask"

        if self.mode is PermissionMode.TRUSTED:
            if risk in {
                RiskClass.READ,
                RiskClass.WRITE,
                RiskClass.EXECUTE,
            }:
                return "allow"
            return "ask"

        if self.mode is PermissionMode.UNRESTRICTED:
            return "allow"

        return "deny"

    def authorize(
        self,
        *,
        repo_path: str,
        tool: str,
        risk: RiskClass,
        args: dict[str, Any],
    ) -> PermissionDecision:
        action = self._base_action(risk)
        if action == "allow":
            return PermissionDecision(
                True,
                f"Allowed by {self.mode.value} permission mode.",
            )
        if action == "deny":
            return PermissionDecision(
                False,
                f"Denied by {self.mode.value} permission mode.",
            )

        key = permission_cache_key(tool, risk, args)
        if key in self._session_allow:
            return PermissionDecision(
                True,
                "Allowed by a previous session approval.",
                ApprovalChoice.ALLOW_SESSION,
            )

        request = PermissionRequest(
            tool=tool,
            risk=risk,
            args=dict(args),
            preview=build_tool_preview(repo_path, tool, args),
            cache_key=key,
            purpose=_request_purpose(tool, risk, args),
            access=_request_access(tool, risk, args),
        )

        if self.approval_callback is None:
            return PermissionDecision(
                False,
                "Permission requires interactive approval, "
                "but no approval callback is available.",
            )

        choice = self.approval_callback(request)
        if choice is ApprovalChoice.ALLOW_SESSION:
            self._session_allow.add(key)
            return PermissionDecision(
                True,
                "Allowed for this session.",
                choice,
            )
        if choice is ApprovalChoice.ALLOW_ONCE:
            return PermissionDecision(True, "Allowed once.", choice)
        return PermissionDecision(
            False,
            "Denied by user.",
            ApprovalChoice.DENY,
        )
