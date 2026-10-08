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


def _single_symbol_block(source: str) -> tuple[str, str]:
    block = _normalize_block(source)
    try:
        tree = ast.parse(block)
    except SyntaxError as exc:
        location = f"line {exc.lineno}" if exc.lineno else "unknown line"
        raise ToolError(
            f"Refusing invalid Python symbol edit: {exc.msg} ({location})"
        ) from exc

    if len(tree.body) != 1 or not isinstance(
        tree.body[0],
        (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
    ):
        raise ToolError(
            "Symbol mutation source must contain exactly one top-level function or class."
        )
    return str(tree.body[0].name), block


def _top_level_symbol_names(tree: ast.Module) -> set[str]:
    return {
        str(node.name)
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }


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
    replacement_name, replacement_block = _single_symbol_block(new_source)
    if replacement_name != name:
        raise ToolError(
            f"replace_symbol must preserve symbol name {name!r}; "
            f"replacement defines {replacement_name!r}."
        )
    replacement = replacement_block + "\n"

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
    inserted_name, block = _single_symbol_block(new_source)
    existing_symbols = _top_level_symbol_names(tree)
    if inserted_name in existing_symbols:
        raise ToolError(
            f"Refusing duplicate top-level Python symbol: {inserted_name}"
        )

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
