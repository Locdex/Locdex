from __future__ import annotations

import ast
from pathlib import Path


def extract_symbols(path: str | Path) -> list[str]:
    p = Path(path)
    if p.suffix != ".py":
        return []
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception:
        return []
    out = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.append(node.name)
    return out
