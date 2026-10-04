from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Any

from ..context.budget import estimate_tokens
from .graph import build_repository_graph, find_references, related_files

_TASK_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _safe_file(root: str, relative_path: str) -> Path | None:
    base = Path(root).resolve()
    candidate = (base / relative_path).resolve()
    try:
        candidate.relative_to(base)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return []


def _top_level_nodes(path: Path):
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, UnicodeDecodeError, SyntaxError):
        return []
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]


def get_symbol_source(
    root: str,
    name: str,
    *,
    context_lines: int = 1,
) -> list[dict[str, Any]]:
    wanted = name.strip()
    if not wanted:
        return []

    graph = build_repository_graph(root)
    results: list[dict[str, Any]] = []
    for row in graph["files"]:
        path = _safe_file(root, row["path"])
        if path is None:
            continue
        lines = _read_lines(path)
        if not lines:
            continue

        for node in _top_level_nodes(path):
            if getattr(node, "name", None) != wanted:
                continue
            start = max(1, int(node.lineno) - max(0, int(context_lines)))
            end_lineno = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
            end = min(len(lines), end_lineno + max(0, int(context_lines)))
            content = "\n".join(lines[start - 1 : end])
            results.append(
                {
                    "path": row["path"],
                    "module": row["module"],
                    "name": wanted,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "start_line": start,
                    "end_line": end,
                    "content": content,
                }
            )
    return results


def get_reference_context(
    root: str,
    name: str,
    *,
    context_lines: int = 2,
    limit: int = 12,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for ref in find_references(root, name):
        path = _safe_file(root, ref["path"])
        if path is None:
            continue
        lines = _read_lines(path)
        if not lines:
            continue

        for line_number in ref["lines"]:
            start = max(1, int(line_number) - max(0, int(context_lines)))
            end = min(len(lines), int(line_number) + max(0, int(context_lines)))
            results.append(
                {
                    "path": ref["path"],
                    "module": ref["module"],
                    "is_test": bool(ref["is_test"]),
                    "reference": name,
                    "line": int(line_number),
                    "start_line": start,
                    "end_line": end,
                    "content": "\n".join(lines[start - 1 : end]),
                }
            )
            if len(results) >= max(1, int(limit)):
                return results
    return results


def _task_symbols(root: str, task: str) -> list[str]:
    graph = build_repository_graph(root)
    tokens = {token.lower() for token in _TASK_TOKEN.findall(task)}
    symbols: list[str] = []
    for row in graph["files"]:
        for definition in row["definitions"]:
            name = str(definition["name"])
            if name.lower() in tokens and name not in symbols:
                symbols.append(name)
        for reference in row["references"]:
            if reference.lower() in tokens and reference not in symbols:
                symbols.append(reference)
    return symbols[:16]


def build_task_context(
    root: str,
    task: str,
    *,
    max_tokens: int = 2200,
    max_files: int = 6,
) -> dict[str, Any]:
    budget = max(256, int(max_tokens))
    ranked = related_files(root, task, limit=max_files)
    symbols = _task_symbols(root, task)

    snippets: list[dict[str, Any]] = []
    used_tokens = 0
    seen: set[tuple[str, int, int]] = set()

    def add_snippet(snippet: dict[str, Any], reason: str) -> bool:
        nonlocal used_tokens
        key = (
            str(snippet.get("path", "")),
            int(snippet.get("start_line", 0)),
            int(snippet.get("end_line", 0)),
        )
        if key in seen:
            return True
        content = str(snippet.get("content", ""))
        tokens = estimate_tokens(content)
        if used_tokens + tokens > budget:
            return False
        seen.add(key)
        snippets.append({**snippet, "reason": reason, "tokens": tokens})
        used_tokens += tokens
        return True

    # Exact task-mentioned definitions first.
    for symbol in symbols:
        for snippet in get_symbol_source(root, symbol, context_lines=1):
            if not add_snippet(snippet, f"definition:{symbol}"):
                break

    # Then usage/test context for task-mentioned symbols.
    for symbol in symbols:
        for snippet in get_reference_context(root, symbol, context_lines=2, limit=8):
            if not add_snippet(snippet, f"reference:{symbol}"):
                break

    # Finally, if a ranked file has not contributed any exact snippet, include a
    # small leading range so missing-symbol tasks still get the relevant file.
    for row in ranked:
        path = _safe_file(root, row["path"])
        if path is None:
            continue
        lines = _read_lines(path)
        if not lines:
            continue
        if any(item["path"] == row["path"] for item in snippets):
            continue
        end = min(len(lines), 80 if row["is_test"] else 60)
        snippet = {
            "path": row["path"],
            "module": Path(row["path"]).with_suffix("").as_posix().replace("/", "."),
            "start_line": 1,
            "end_line": end,
            "content": "\n".join(lines[:end]),
            "is_test": bool(row["is_test"]),
        }
        if not add_snippet(snippet, "ranked-file-fallback"):
            break

    return {
        "related_files": ranked,
        "task_symbols": symbols,
        "snippets": snippets,
        "tokens": used_tokens,
        "budget": budget,
    }


def task_context_text(
    root: str,
    task: str,
    *,
    max_tokens: int = 2200,
    max_files: int = 6,
) -> str:
    pack = build_task_context(
        root,
        task,
        max_tokens=max_tokens,
        max_files=max_files,
    )
    lines = ["Exact task source context:"]
    for snippet in pack["snippets"]:
        lines.append(
            f"\n[{snippet['path']}:{snippet['start_line']}-{snippet['end_line']}] "
            f"{snippet['reason']}"
        )
        lines.append(str(snippet["content"]))
    return "\n".join(lines)
