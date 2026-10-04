from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .executor import ToolError


_PROTECTED_PARTS = {
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
    ".env",
}


def _safe_python_path(repo_path: str, relative: str) -> Path:
    root = Path(repo_path).resolve()
    candidate = (root / relative).resolve()
    try:
        parts = candidate.relative_to(root).parts
    except ValueError as exc:
        raise ToolError("Path traversal outside the workspace is blocked.") from exc
    if any(part in _PROTECTED_PARTS for part in parts):
        raise ToolError("Direct access to protected/internal workspace paths is blocked.")
    if not candidate.is_file():
        raise ToolError(f"File does not exist: {relative}")
    if candidate.suffix.lower() not in {".py", ".pyi"}:
        raise ToolError("Python symbol mutation tools require a .py or .pyi file.")
    return candidate


def _module(path: Path) -> tuple[str, ast.Module]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise ToolError("File is not UTF-8 text.") from exc
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ToolError(
            f"Cannot perform symbol edit because current Python source is invalid: {exc.msg}"
        ) from exc
    return source, tree


def _node_start(node: ast.AST) -> int:
    starts = [int(getattr(node, "lineno", 1) or 1)]
    decorators = getattr(node, "decorator_list", None) or []
    starts.extend(int(getattr(item, "lineno", starts[0]) or starts[0]) for item in decorators)
    return min(starts)


def _find_top_level(tree: ast.Module, name: str) -> ast.AST:
    matches = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        and getattr(node, "name", None) == name
    ]
    if not matches:
        raise ToolError(f"Top-level Python symbol was not found: {name}")
    if len(matches) > 1:
        raise ToolError(f"Multiple top-level Python symbols share this name: {name}")
    return matches[0]


def _normalize_block(source: str) -> str:
    block = str(source).strip("\n")
    if not block.strip():
        raise ToolError("Symbol source cannot be empty.")
    return block


def _validate_updated(path: Path, content: str) -> None:
    try:
        ast.parse(content)
    except SyntaxError as exc:
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        raise ToolError(
            f"Refusing invalid Python symbol edit: {exc.msg} ({location})"
        ) from exc


def replace_symbol(
    repo_path: str,
    path: str,
    name: str,
    new_source: str,
) -> dict[str, Any]:
    target = _safe_python_path(repo_path, path)
    source, tree = _module(target)
    node = _find_top_level(tree, name)

    lines = source.splitlines(keepends=True)
    start = _node_start(node)
    end = int(getattr(node, "end_lineno", getattr(node, "lineno", start)) or start)
    replacement = _normalize_block(new_source) + "\n"

    updated = "".join(lines[: start - 1]) + replacement + "".join(lines[end:])
    _validate_updated(target, updated)
    target.write_text(updated, encoding="utf-8")

    return {
        "ok": True,
        "path": str(target.relative_to(Path(repo_path).resolve())).replace("\\", "/"),
        "symbol": name,
        "operation": "replace_symbol",
        "start_line": start,
        "end_line": end,
    }


def insert_after_symbol(
    repo_path: str,
    path: str,
    anchor: str,
    new_source: str,
) -> dict[str, Any]:
    target = _safe_python_path(repo_path, path)
    source, tree = _module(target)
    node = _find_top_level(tree, anchor)

    lines = source.splitlines(keepends=True)
    end = int(getattr(node, "end_lineno", getattr(node, "lineno", 1)) or 1)
    block = _normalize_block(new_source)

    prefix = "".join(lines[:end])
    suffix = "".join(lines[end:])
    separator = "" if prefix.endswith("\n\n") else "\n"
    insertion = separator + block + "\n"
    if suffix and not suffix.startswith("\n"):
        insertion += "\n"

    updated = prefix + insertion + suffix
    _validate_updated(target, updated)
    target.write_text(updated, encoding="utf-8")

    return {
        "ok": True,
        "path": str(target.relative_to(Path(repo_path).resolve())).replace("\\", "/"),
        "anchor": anchor,
        "operation": "insert_after_symbol",
        "inserted_after_line": end,
    }
