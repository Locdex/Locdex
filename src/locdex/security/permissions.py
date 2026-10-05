from __future__ import annotations

import ast
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


def _bounded_diff(
    before: str,
    after: str,
    *,
    path: str,
    max_lines: int = 120,
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
    if not lines:
        return "(no textual diff)"
    if len(lines) > max_lines:
        lines = lines[:max_lines] + ["... diff truncated ..."]
    return "\n".join(lines)


def _symbol_source(path: Path, name: str) -> str | None:
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None
    lines = source.splitlines()
    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
        ):
            continue
        if getattr(node, "name", None) != name:
            continue
        start = int(getattr(node, "lineno", 1) or 1)
        decorators = getattr(node, "decorator_list", None) or []
        if decorators:
            start = min(
                start,
                *(
                    int(getattr(item, "lineno", start) or start)
                    for item in decorators
                ),
            )
        end = int(getattr(node, "end_lineno", start) or start)
        return "\n".join(lines[start - 1 : end])
    return None


def build_tool_preview(
    repo_path: str,
    tool: str,
    args: dict[str, Any],
) -> str:
    path_text = str(args.get("path", "")).replace("\\", "/")

    if tool == "write_file" and path_text:
        target = _safe_workspace_path(repo_path, path_text)
        before = ""
        if target is not None and target.is_file():
            try:
                before = target.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                before = "<existing non-UTF-8 file>"
        after = str(args.get("content", ""))
        return _bounded_diff(before, after, path=path_text)

    if tool == "replace_in_file" and path_text:
        target = _safe_workspace_path(repo_path, path_text)
        if target is not None and target.is_file():
            try:
                before = target.read_text(encoding="utf-8")
                old = str(args.get("old", ""))
                new = str(args.get("new", ""))
                count = max(1, int(args.get("count", 1)))
                after = before.replace(old, new, count)
                return _bounded_diff(before, after, path=path_text)
            except (OSError, UnicodeDecodeError, ValueError):
                pass
        return f"Edit {path_text} with an exact text replacement."

    if tool == "replace_symbol" and path_text:
        target = _safe_workspace_path(repo_path, path_text)
        symbol = str(args.get("name", ""))
        after = str(args.get("new_source", ""))
        before = (
            _symbol_source(target, symbol)
            if target is not None and target.is_file()
            else None
        )
        if before is not None:
            return _bounded_diff(
                before + "\n",
                after.strip("\n") + "\n",
                path=f"{path_text}::{symbol}",
            )
        return (
            f"Replace Python symbol {symbol!r} in {path_text} with:\n"
            f"{after[:4000]}"
        )

    if tool == "insert_after_symbol" and path_text:
        anchor = str(args.get("anchor", ""))
        new_source = str(args.get("new_source", ""))
        return (
            f"Insert after Python symbol {anchor!r} in {path_text}:\n"
            + "\n".join(
                f"+ {line}" for line in new_source.splitlines()
            )[:4000]
        )

    if tool == "delete_path" and path_text:
        return f"Delete workspace path: {path_text}"

    if tool == "run_command":
        argv = args.get("argv") or []
        if isinstance(argv, list):
            return "Run command:\n  " + shlex.join(
                str(item) for item in argv
            )
        return "Run a workspace command."

    if tool == "run_tests":
        return "Run the detected project test suite."

    if tool.startswith("git_"):
        details = ", ".join(
            f"{key}={value!r}"
            for key, value in args.items()
            if value not in (None, "", [], {})
        )
        return (
            f"Git action: {tool}"
            + (f"\n{details}" if details else "")
        )

    return f"Tool: {tool}\nArguments: {args}"


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


def format_permission_request(request: PermissionRequest) -> str:
    rows = [
        f"Locdex wants to use: {request.tool}",
        f"Risk: {request.risk.value}",
    ]
    if request.purpose:
        rows.extend(["", "Reason:", f"  {request.purpose}"])
    if request.access:
        rows.extend(["", "Access:"])
        rows.extend(f"  • {item}" for item in request.access)
    rows.extend(["", "Preview:", request.preview])
    return "\n".join(rows)


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
