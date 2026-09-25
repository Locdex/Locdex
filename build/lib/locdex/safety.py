from __future__ import annotations

import ast
import os

BLOCKED_BUILTINS = {"eval", "exec", "__import__"}
PROTECTED_PARTS = {
    ".git",
    ".github",
    "venv",
    ".venv",
    "env",
    ".env",
    "__pycache__",
    ".locdex_budget.json",
    ".locdex_telemetry.json",
}

def _literal_true(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is True

def check_ast_security(code: str) -> list[str]:
    """Low-false-positive static safety review; execution safety is enforced by the sandbox."""
    flags: list[str] = []
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return flags

    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Name):
            name = node.func.id
            target = aliases.get(name, name)
            if name in BLOCKED_BUILTINS:
                flags.append(f"[Security Violation] Dynamic execution call blocked: {name}().")
            if target in {"os.system", "os.popen"}:
                flags.append(f"[Security Violation] Shell execution call blocked: {target}().")

        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            base = node.func.value.id if isinstance(node.func.value, ast.Name) else None
            full_name = f"{aliases.get(base, base)}.{attr}" if base else attr
            if full_name in {"os.system", "os.popen"}:
                flags.append(f"[Security Violation] Shell execution call blocked: {full_name}().")
            if full_name in {
                "subprocess.run",
                "subprocess.call",
                "subprocess.Popen",
                "subprocess.check_call",
                "subprocess.check_output",
            }:
                for keyword in node.keywords:
                    if keyword.arg == "shell" and _literal_true(keyword.value):
                        flags.append(
                            f"[Security Violation] {full_name}(..., shell=True) is blocked. Use argv form instead."
                        )

    return sorted(set(flags))


def is_safe_path(base_dir: str, target_path: str) -> bool:
    try:
        if not target_path or os.path.basename(target_path).startswith("-"):
            return False
        abs_base = os.path.abspath(base_dir)
        abs_target = os.path.abspath(os.path.join(abs_base, target_path))
        return os.path.commonpath([abs_base, abs_target]) == abs_base
    except (ValueError, OSError):
        return False


def is_protected_path(target_path: str) -> bool:
    if not isinstance(target_path, str):
        return True
    normalized = target_path.replace("\\", "/")
    parts = {part for part in normalized.split("/") if part}
    return bool(parts.intersection(PROTECTED_PARTS))
