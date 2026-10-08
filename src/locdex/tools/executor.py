from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from ..sandbox import sandbox_environment, wrap_command
from ..security import native_authorize
from .registry import TOOLS

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".preflight-tmp",
    ".pytest-tmp",
}
PROTECTED_PARTS = IGNORED_DIRS | {".env"}
TEXT_EXTENSIONS = {
    ".py",
    ".pyi",
    ".toml",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".ini",
    ".cfg",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".sql",
    ".css",
    ".scss",
    ".html",
    ".vue",
    ".svelte",
    ".xml",
    ".gradle",
    ".properties",
}
SPECIAL_TEXT_FILES = {"Dockerfile", "Makefile"}
MAX_READ_BYTES = 2_000_000
MAX_TOOL_OUTPUT = 20_000
MAX_COMMAND_SECONDS = 180
BLOCKED_EXECUTABLES = {
    "sudo",
    "su",
    "doas",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "git",
    "gh",
    "cmd",
    "cmd.exe",
    "powershell",
    "powershell.exe",
    "pwsh",
    "bash",
    "sh",
    "zsh",
    "fish",
    "wsl",
    "curl",
    "wget",
    "ssh",
    "scp",
    "ftp",
    "nc",
    "ncat",
}
SECRET_ENV_MARKERS = ("TOKEN", "SECRET", "PASSWORD", "API_KEY", "PRIVATE_KEY", "CREDENTIAL")


class ToolError(ValueError):
    pass


def _root(repo_path: str) -> Path:
    root = Path(repo_path).resolve()
    if not root.is_dir():
        raise ToolError(f"Workspace does not exist: {root}")
    return root


def _safe_resolve(repo_path: str, relative: str, *, allow_missing: bool = True) -> Path:
    root = _root(repo_path)
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ToolError("Path traversal outside the workspace is blocked.") from exc

    relative_parts = candidate.relative_to(root).parts
    if any(part in PROTECTED_PARTS for part in relative_parts):
        raise ToolError("Direct access to protected/internal workspace paths is blocked.")
    if not allow_missing and not candidate.exists():
        raise ToolError(f"Path does not exist: {relative}")
    return candidate


def _relative(repo_path: str, path: Path) -> str:
    return str(path.relative_to(_root(repo_path))).replace("\\", "/")


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS or path.name in SPECIAL_TEXT_FILES


def _sanitized_env(sandbox_mode: str | None = None) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in SECRET_ENV_MARKERS)
    }
    env["LOCDEX_AGENT"] = "1"
    if sandbox_mode:
        env.update(sandbox_environment(sandbox_mode))
    return env


def _bounded_timeout(value: int) -> int:
    return max(1, min(int(value), MAX_COMMAND_SECONDS))


def _git(
    repo_path: str,
    *args: str,
    timeout: int = 120,
    sandbox_mode: str | None = None,
) -> subprocess.CompletedProcess[str]:
    argv = ["git", *args]
    wrapped_argv = argv
    if sandbox_mode:
        try:
            wrapped_argv, _ = wrap_command(
                repo_path,
                str(_root(repo_path)),
                argv,
                sandbox_mode,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    try:
        return subprocess.run(
            wrapped_argv,
            cwd=_root(repo_path),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_bounded_timeout(timeout),
            check=False,
            env=_sanitized_env(sandbox_mode),
        )
    except FileNotFoundError as exc:
        raise ToolError("git or the selected sandbox backend is not installed or not on PATH.") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"git {' '.join(args)} timed out.") from exc


def list_files(repo_path: str, path: str = ".", limit: int = 200) -> dict[str, Any]:
    base = _safe_resolve(repo_path, path, allow_missing=False)
    root = _root(repo_path)
    results: list[str] = []
    cap = max(1, min(int(limit), 500))

    if base.is_file():
        return {"files": [_relative(repo_path, base)], "truncated": False}

    for current_root, dirs, files in os.walk(base):
        dirs[:] = sorted(
            directory
            for directory in dirs
            if directory not in IGNORED_DIRS and not directory.startswith(".")
        )
        for name in sorted(files):
            candidate = Path(current_root) / name
            if not _is_text_file(candidate):
                continue
            results.append(str(candidate.relative_to(root)).replace("\\", "/"))
            if len(results) >= cap:
                return {"files": results, "truncated": True}
    return {"files": results, "truncated": False}


def read_file(
    repo_path: str,
    path: str,
    start_line: int = 1,
    end_line: int = 300,
) -> dict[str, Any]:
    candidate = _safe_resolve(repo_path, path, allow_missing=False)
    if not candidate.is_file():
        raise ToolError(f"File does not exist: {path}")
    if candidate.stat().st_size > MAX_READ_BYTES:
        raise ToolError("File is too large for the agent read tool.")

    start = max(1, int(start_line))
    end = max(start, min(int(end_line), start + 399))
    try:
        lines = candidate.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise ToolError("File is not UTF-8 text.") from exc

    selected = lines[start - 1 : end]
    numbered = "\n".join(
        f"{line_number}: {line}"
        for line_number, line in enumerate(selected, start=start)
    )
    return {
        "path": _relative(repo_path, candidate),
        "start_line": start,
        "end_line": min(end, len(lines)),
        "total_lines": len(lines),
        "content": numbered,
    }


def search_code(
    repo_path: str,
    query: str,
    path: str = ".",
    limit: int = 50,
) -> dict[str, Any]:
    if not query or len(query) > 300:
        raise ToolError("Search query must be between 1 and 300 characters.")

    base = _safe_resolve(repo_path, path, allow_missing=False)
    root = _root(repo_path)
    needle = query.lower()
    matches: list[dict[str, Any]] = []
    cap = max(1, min(int(limit), 100))

    files: list[Path] = [base] if base.is_file() else []
    if base.is_dir():
        for current_root, dirs, names in os.walk(base):
            dirs[:] = [
                directory
                for directory in dirs
                if directory not in IGNORED_DIRS and not directory.startswith(".")
            ]
            for name in names:
                candidate = Path(current_root) / name
                if _is_text_file(candidate):
                    files.append(candidate)

    for candidate in files:
        try:
            if candidate.stat().st_size > MAX_READ_BYTES:
                continue
            for line_number, line in enumerate(
                candidate.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if needle in line.lower():
                    matches.append(
                        {
                            "path": str(candidate.relative_to(root)).replace("\\", "/"),
                            "line": line_number,
                            "text": line[:500],
                        }
                    )
                    if len(matches) >= cap:
                        return {"matches": matches, "truncated": True}
        except (OSError, UnicodeDecodeError):
            continue

    return {"matches": matches, "truncated": False}


def write_file(repo_path: str, path: str, content: str) -> dict[str, Any]:
    if not isinstance(content, str):
        raise ToolError("write_file content must be text.")
    target = _safe_resolve(repo_path, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    target.write_text(content, encoding="utf-8")
    return {
        "ok": True,
        "path": _relative(repo_path, target),
        "created": not existed,
        "bytes": len(content.encode("utf-8")),
    }


def replace_in_file(
    repo_path: str,
    path: str,
    old: str,
    new: str,
    count: int = 1,
) -> dict[str, Any]:
    target = _safe_resolve(repo_path, path, allow_missing=False)
    if not target.is_file():
        raise ToolError(f"File does not exist: {path}")
    if not old:
        raise ToolError("replace_in_file requires a non-empty old string.")

    text = target.read_text(encoding="utf-8")
    occurrences = text.count(old)
    if occurrences == 0:
        raise ToolError("Exact text to replace was not found.")

    requested = max(1, min(int(count), occurrences))
    target.write_text(text.replace(old, new, requested), encoding="utf-8")
    return {
        "ok": True,
        "path": _relative(repo_path, target),
        "replacements": requested,
        "remaining_matches": occurrences - requested,
    }


def delete_path(repo_path: str, path: str) -> dict[str, Any]:
    target = _safe_resolve(repo_path, path, allow_missing=False)
    if target.is_dir():
        if any(target.iterdir()):
            raise ToolError("Refusing to recursively delete a non-empty directory.")
        target.rmdir()
    else:
        target.unlink()
    return {"ok": True, "path": path}


def run_command(
    repo_path: str,
    argv: list[str],
    cwd: str = ".",
    timeout: int = 120,
    *,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(item, str) and item for item in argv)
    ):
        raise ToolError("run_command requires argv as a non-empty list of strings.")

    executable = Path(argv[0]).name.lower()
    if executable in BLOCKED_EXECUTABLES:
        if executable in {"git", "gh"}:
            raise ToolError("Use Locdex dedicated Git tools instead of run_command.")
        raise ToolError(f"Command is blocked in agent mode: {executable}")

    if executable in {"python", "python.exe", "python3"} and len(argv) >= 3:
        if argv[1:3] == ["-m", "pip"]:
            raise ToolError("Package installation is blocked in the generic agent command tool.")

    working = _safe_resolve(repo_path, cwd, allow_missing=False)
    if not working.is_dir():
        raise ToolError("Command cwd must be a directory inside the workspace.")

    wrapped_argv = list(argv)
    sandbox_backend = "none"
    if sandbox_mode:
        try:
            wrapped_argv, sandbox_backend = wrap_command(
                repo_path,
                str(working),
                list(argv),
                sandbox_mode,
            )
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    try:
        process = subprocess.run(
            wrapped_argv,
            cwd=working,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=_bounded_timeout(timeout),
            check=False,
            env=_sanitized_env(sandbox_mode),
        )
    except FileNotFoundError as exc:
        raise ToolError(f"Executable not found: {wrapped_argv[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"Command timed out after {timeout}s: {shlex.join(argv)}") from exc

    combined = (
        (process.stdout or "")
        + ("\n" + process.stderr if process.stderr else "")
    )[-MAX_TOOL_OUTPUT:]
    return {
        "ok": process.returncode == 0,
        "returncode": process.returncode,
        "output": combined,
        "command": shlex.join(argv),
        "sandbox_backend": sandbox_backend,
        "sandbox_mode": sandbox_mode,
    }


def _has_python_tests(repo_path: str) -> bool:
    root = _root(repo_path)
    for current_root, dirs, files in os.walk(root):
        dirs[:] = [
            directory
            for directory in dirs
            if directory not in IGNORED_DIRS and not directory.startswith(".")
        ]
        for name in files:
            lower = name.lower()
            if lower.endswith(".py") and (
                lower.startswith("test_") or lower.endswith("_test.py")
            ):
                return True
    return False


def run_tests(repo_path: str, *, sandbox_mode: str | None = None) -> dict[str, Any]:
    root = _root(repo_path)
    python_markers = (
        root / "pytest.ini",
        root / "pyproject.toml",
        root / "setup.cfg",
        root / "tox.ini",
    )
    if any(marker.exists() for marker in python_markers) or _has_python_tests(repo_path):
        return run_command(
            repo_path,
            [sys.executable, "-m", "pytest", "-q"],
            timeout=MAX_COMMAND_SECONDS,
            sandbox_mode=sandbox_mode,
        )

    candidates = [
        (["npm", "test", "--", "--runInBand"], root / "package.json"),
        (["go", "test", "./..."], root / "go.mod"),
        (["cargo", "test"], root / "Cargo.toml"),
    ]
    for argv, marker in candidates:
        if marker.exists():
            return run_command(
                repo_path,
                argv,
                timeout=MAX_COMMAND_SECONDS,
                sandbox_mode=sandbox_mode,
            )

    return {
        "ok": False,
        "returncode": None,
        "output": "No supported test runner was detected automatically.",
    }


def git_status(repo_path: str, *, sandbox_mode: str | None = None) -> dict[str, Any]:
    process = _git(
        repo_path,
        "status",
        "--short",
        "--branch",
        sandbox_mode=sandbox_mode,
    )
    return {
        "ok": process.returncode == 0,
        "output": (process.stdout + process.stderr)[-MAX_TOOL_OUTPUT:],
    }


def git_diff(
    repo_path: str,
    staged: bool = False,
    path: str | None = None,
    *,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    args = ["diff"]
    if staged:
        args.append("--cached")
    if path:
        safe_path = _relative(repo_path, _safe_resolve(repo_path, path))
        args.extend(["--", safe_path])
    process = _git(repo_path, *args, sandbox_mode=sandbox_mode)
    return {
        "ok": process.returncode == 0,
        "output": (process.stdout + process.stderr)[-MAX_TOOL_OUTPUT:],
    }


def git_add(
    repo_path: str,
    paths: list[str] | None = None,
    all_changes: bool = False,
    *,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    if all_changes:
        process = _git(repo_path, "add", "-A", sandbox_mode=sandbox_mode)
    else:
        if not paths:
            raise ToolError("git_add requires paths or all_changes=true.")
        safe = [
            _relative(repo_path, _safe_resolve(repo_path, item))
            for item in paths
        ]
        process = _git(repo_path, "add", "--", *safe, sandbox_mode=sandbox_mode)
    return {"ok": process.returncode == 0, "output": (process.stdout + process.stderr)[-MAX_TOOL_OUTPUT:]}


def git_commit(
    repo_path: str,
    message: str,
    *,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    if not message.strip():
        raise ToolError("Commit message cannot be empty.")
    process = _git(
        repo_path,
        "commit",
        "-m",
        message.strip(),
        sandbox_mode=sandbox_mode,
    )
    return {"ok": process.returncode == 0, "output": (process.stdout + process.stderr)[-MAX_TOOL_OUTPUT:]}


def git_pull(
    repo_path: str,
    remote: str = "origin",
    branch: str | None = None,
    rebase: bool = False,
    *,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    args = ["pull"]
    if rebase:
        args.append("--rebase")
    args.append(remote)
    if branch:
        args.append(branch)
    process = _git(
        repo_path,
        *args,
        timeout=MAX_COMMAND_SECONDS,
        sandbox_mode=sandbox_mode,
    )
    return {"ok": process.returncode == 0, "output": (process.stdout + process.stderr)[-MAX_TOOL_OUTPUT:]}


def git_push(
    repo_path: str,
    remote: str = "origin",
    branch: str | None = None,
    set_upstream: bool = False,
    *,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    args = ["push"]
    if set_upstream:
        args.extend(["-u", remote])
        if branch:
            args.append(branch)
    else:
        args.append(remote)
        if branch:
            args.append(branch)
    process = _git(
        repo_path,
        *args,
        timeout=MAX_COMMAND_SECONDS,
        sandbox_mode=sandbox_mode,
    )
    return {"ok": process.returncode == 0, "output": (process.stdout + process.stderr)[-MAX_TOOL_OUTPUT:]}


def execute_tool(
    repo_path: str,
    name: str,
    args: dict[str, Any] | None = None,
    *,
    explicit_user_intent: bool = False,
    sandbox_mode: str | None = None,
) -> dict[str, Any]:
    args = args or {}
    definition = TOOLS.get(name)
    if definition is None:
        raise ToolError(f"Unknown tool: {name}")

    decision = native_authorize(
        definition.risk,
        explicit_user_intent=explicit_user_intent,
    )
    if not decision.allowed:
        raise ToolError(decision.reason)

    if name == "list_files":
        return list_files(repo_path, str(args.get("path", ".")), int(args.get("limit", 200)))
    if name == "read_file":
        if "path" not in args:
            raise ToolError("read_file requires path")
        return read_file(
            repo_path,
            str(args["path"]),
            int(args.get("start_line", 1)),
            int(args.get("end_line", 300)),
        )
    if name == "search_code":
        if "query" not in args:
            raise ToolError("search_code requires query")
        return search_code(
            repo_path,
            str(args["query"]),
            str(args.get("path", ".")),
            int(args.get("limit", 50)),
        )
    if name == "write_file":
        if "path" not in args or "content" not in args:
            raise ToolError("write_file requires path and content")
        return write_file(repo_path, str(args["path"]), str(args["content"]))
    if name == "replace_in_file":
        for required in ("path", "old", "new"):
            if required not in args:
                raise ToolError(f"replace_in_file requires {required}")
        return replace_in_file(
            repo_path,
            str(args["path"]),
            str(args["old"]),
            str(args["new"]),
            int(args.get("count", 1)),
        )
    if name == "replace_symbol":
        for required in ("path", "name", "new_source"):
            if required not in args:
                raise ToolError(f"replace_symbol requires {required}")
        from .python_symbols import replace_symbol

        return replace_symbol(
            repo_path,
            str(args["path"]),
            str(args["name"]),
            str(args["new_source"]),
        )
    if name == "insert_after_symbol":
        for required in ("path", "anchor", "new_source"):
            if required not in args:
                raise ToolError(f"insert_after_symbol requires {required}")
        from .python_symbols import insert_after_symbol

        return insert_after_symbol(
            repo_path,
            str(args["path"]),
            str(args["anchor"]),
            str(args["new_source"]),
        )
    if name == "delete_path":
        if "path" not in args:
            raise ToolError("delete_path requires path")
        return delete_path(repo_path, str(args["path"]))
    if name == "run_command":
        return run_command(
            repo_path,
            args.get("argv") or [],
            str(args.get("cwd", ".")),
            int(args.get("timeout", 120)),
            sandbox_mode=sandbox_mode,
        )
    if name == "run_tests":
        return run_tests(repo_path, sandbox_mode=sandbox_mode)
    if name == "mcp_list_tools":
        server = str(args.get("server", "")).strip()
        if not server:
            raise ToolError("mcp_list_tools requires server")
        from ..extensions.mcp import MCPConfigError, MCPUnavailableError, list_mcp_tools
        try:
            return list_mcp_tools(
                repo_path,
                server,
                sandbox_mode=sandbox_mode or "workspace-network",
            )
        except (MCPConfigError, MCPUnavailableError) as exc:
            raise ToolError(str(exc)) from exc
    if name == "mcp_call":
        server = str(args.get("server", "")).strip()
        tool = str(args.get("tool", "")).strip()
        arguments = args.get("arguments") or {}
        if not server or not tool:
            raise ToolError("mcp_call requires server and tool")
        if not isinstance(arguments, dict):
            raise ToolError("mcp_call arguments must be an object")
        from ..extensions.mcp import MCPConfigError, MCPUnavailableError, call_mcp_tool
        try:
            return call_mcp_tool(
                repo_path,
                server,
                tool,
                arguments,
                sandbox_mode=sandbox_mode or "workspace-network",
            )
        except (MCPConfigError, MCPUnavailableError) as exc:
            raise ToolError(str(exc)) from exc
    if name == "git_status":
        return git_status(repo_path, sandbox_mode=sandbox_mode)
    if name == "git_diff":
        return git_diff(
            repo_path,
            bool(args.get("staged", False)),
            str(args["path"]) if args.get("path") else None,
            sandbox_mode=sandbox_mode,
        )
    if name == "git_add":
        paths = args.get("paths")
        if paths is not None and (
            not isinstance(paths, list) or not all(isinstance(item, str) for item in paths)
        ):
            raise ToolError("git_add paths must be a list of strings")
        return git_add(
            repo_path,
            paths,
            bool(args.get("all_changes", False)),
            sandbox_mode=sandbox_mode,
        )
    if name == "git_commit":
        return git_commit(
            repo_path,
            str(args.get("message", "")),
            sandbox_mode=sandbox_mode,
        )
    if name == "git_pull":
        return git_pull(
            repo_path,
            str(args.get("remote", "origin")),
            str(args["branch"]) if args.get("branch") else None,
            bool(args.get("rebase", False)),
            sandbox_mode=sandbox_mode,
        )
    if name == "git_push":
        return git_push(
            repo_path,
            str(args.get("remote", "origin")),
            str(args["branch"]) if args.get("branch") else None,
            bool(args.get("set_upstream", False)),
            sandbox_mode=sandbox_mode,
        )

    raise ToolError(f"Tool is registered but not implemented: {name}")
