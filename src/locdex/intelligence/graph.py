from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

_IGNORED_PARTS = {
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
_TASK_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")


def _python_files(root: Path) -> list[Path]:
    return [
        path
        for path in sorted(root.rglob("*.py"))
        if path.is_file() and not any(part in _IGNORED_PARTS for part in path.parts)
    ]


def _relative(root: Path, path: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def _module_name(root: Path, path: Path) -> str:
    rel = path.relative_to(root).with_suffix("")
    parts = list(rel.parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _parse(path: Path) -> ast.Module | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, SyntaxError):
        return None


def _definitions(tree: ast.Module) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            result.append(
                {
                    "name": node.name,
                    "kind": "class" if isinstance(node, ast.ClassDef) else "function",
                    "line": int(getattr(node, "lineno", 0) or 0),
                }
            )
    return result


def _references(tree: ast.Module) -> dict[str, list[int]]:
    refs: dict[str, set[int]] = defaultdict(set)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            refs[node.id].add(int(getattr(node, "lineno", 0) or 0))
        elif isinstance(node, ast.Attribute):
            refs[node.attr].add(int(getattr(node, "lineno", 0) or 0))
    return {name: sorted(lines) for name, lines in refs.items()}


def _raw_imports(tree: ast.Module) -> list[tuple[str, int]]:
    imports: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            imports.append((node.module or "", int(node.level or 0)))
    return imports


def _resolve_relative_module(current: str, module: str, level: int) -> str:
    if level <= 0:
        return module
    package = current.split(".")[:-1]
    keep = max(0, len(package) - (level - 1))
    prefix = package[:keep]
    if module:
        prefix.extend(module.split("."))
    return ".".join(prefix)


def build_repository_graph(root: str) -> dict[str, Any]:
    base = Path(root).resolve()
    module_to_path: dict[str, str] = {}
    parsed: dict[str, tuple[ast.Module, str]] = {}

    for path in _python_files(base):
        rel = _relative(base, path)
        module = _module_name(base, path)
        module_to_path[module] = rel
        tree = _parse(path)
        if tree is not None:
            parsed[rel] = (tree, module)

    files: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    reverse: dict[str, set[str]] = defaultdict(set)

    for rel, (tree, current_module) in parsed.items():
        imports: list[dict[str, str]] = []
        for raw_module, level in _raw_imports(tree):
            resolved_module = _resolve_relative_module(current_module, raw_module, level)
            target = module_to_path.get(resolved_module)
            if target is None and resolved_module:
                prefix = resolved_module
                while "." in prefix and target is None:
                    prefix = prefix.rsplit(".", 1)[0]
                    target = module_to_path.get(prefix)
            imports.append(
                {
                    "module": resolved_module or raw_module,
                    "path": target or "",
                }
            )
            if target and target != rel:
                edge_type = "tests" if _is_test_file(rel) else "imports"
                edges.append({"from": rel, "to": target, "type": edge_type})
                reverse[target].add(rel)

        files.append(
            {
                "path": rel,
                "module": current_module,
                "is_test": _is_test_file(rel),
                "definitions": _definitions(tree),
                "references": _references(tree),
                "imports": imports,
            }
        )

    files.sort(key=lambda row: row["path"])
    edges.sort(key=lambda row: (row["from"], row["to"], row["type"]))
    return {
        "files": files,
        "edges": edges,
        "dependents": {
            path: sorted(values)
            for path, values in sorted(reverse.items())
        },
    }


def _is_test_file(path: str) -> bool:
    name = Path(path).name.lower()
    parts = {part.lower() for part in Path(path).parts}
    return (
        name.startswith("test_")
        or name.endswith("_test.py")
        or "tests" in parts
        or "test" in parts
    )


def find_symbol(root: str, name: str) -> list[dict[str, Any]]:
    wanted = name.strip()
    if not wanted:
        return []
    graph = build_repository_graph(root)
    matches: list[dict[str, Any]] = []
    for file_row in graph["files"]:
        for definition in file_row["definitions"]:
            if definition["name"] == wanted:
                matches.append(
                    {
                        "path": file_row["path"],
                        "module": file_row["module"],
                        **definition,
                    }
                )
    return matches


def find_references(root: str, name: str) -> list[dict[str, Any]]:
    wanted = name.strip()
    if not wanted:
        return []
    graph = build_repository_graph(root)
    matches: list[dict[str, Any]] = []
    for file_row in graph["files"]:
        lines = file_row["references"].get(wanted, [])
        if lines:
            matches.append(
                {
                    "path": file_row["path"],
                    "module": file_row["module"],
                    "lines": lines[:50],
                    "is_test": file_row["is_test"],
                }
            )
    return matches


def related_files(root: str, task: str, limit: int = 8) -> list[dict[str, Any]]:
    graph = build_repository_graph(root)
    tokens = {token.lower() for token in _TASK_TOKEN.findall(task)}
    rows_by_path = {row["path"]: row for row in graph["files"]}
    score: dict[str, int] = defaultdict(int)
    reasons: dict[str, set[str]] = defaultdict(set)

    for row in graph["files"]:
        path = row["path"]
        lower_path = path.lower()
        stem_tokens = {token.lower() for token in _TASK_TOKEN.findall(lower_path)}
        overlap = tokens & stem_tokens
        if overlap:
            score[path] += 8 * len(overlap)
            reasons[path].add("path/task match")

        definition_names = {item["name"].lower() for item in row["definitions"]}
        symbol_overlap = tokens & definition_names
        if symbol_overlap:
            score[path] += 12 * len(symbol_overlap)
            reasons[path].add("symbol/task match")

        reference_names = set(row["references"])
        reference_overlap = tokens & {item.lower() for item in reference_names}
        if reference_overlap:
            score[path] += 4 * len(reference_overlap)
            reasons[path].add("reference/task match")

        if row["is_test"] and any(word in tokens for word in {"test", "tests", "fail", "failing", "fix"}):
            score[path] += 3
            reasons[path].add("test file")

    edge_pairs = [(edge["from"], edge["to"], edge["type"]) for edge in graph["edges"]]
    seeds = {path for path, value in score.items() if value > 0}
    for source, target, edge_type in edge_pairs:
        if source in seeds:
            score[target] += 5
            reasons[target].add(f"related by {edge_type}")
        if target in seeds:
            score[source] += 4
            reasons[source].add("dependent/test relationship")

    ranked = sorted(
        (
            {
                "path": path,
                "score": value,
                "reasons": sorted(reasons[path]),
                "symbols": [item["name"] for item in rows_by_path[path]["definitions"][:12]],
                "is_test": bool(rows_by_path[path]["is_test"]),
            }
            for path, value in score.items()
            if value > 0
        ),
        key=lambda row: (-row["score"], row["path"]),
    )
    return ranked[: max(1, min(int(limit), 30))]


def graph_summary(root: str, task: str, limit: int = 12) -> str:
    graph = build_repository_graph(root)
    related = related_files(root, task, limit=limit)
    related_paths = {row["path"] for row in related}
    edges = [
        edge
        for edge in graph["edges"]
        if edge["from"] in related_paths or edge["to"] in related_paths
    ]

    lines = ["Relevant repository relationships:"]
    for row in related:
        symbol_text = ", ".join(row["symbols"]) or "-"
        reason_text = ", ".join(row["reasons"])
        lines.append(
            f"- {row['path']} | score={row['score']} | symbols={symbol_text} | {reason_text}"
        )

    if edges:
        lines.append("Edges:")
        for edge in edges[:40]:
            lines.append(f"- {edge['from']} --{edge['type']}--> {edge['to']}")
    return "\n".join(lines)
