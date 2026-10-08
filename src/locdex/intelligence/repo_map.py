from __future__ import annotations

from pathlib import Path

from .fingerprints import file_fingerprint
from .symbols import extract_symbols


def build_repo_map(root: str) -> list[dict]:
    base = Path(root).resolve()
    rows = []
    for p in sorted(base.rglob("*")):
        if not p.is_file() or any(part in {".git", ".venv", "venv", "node_modules", "__pycache__"} for part in p.parts):
            continue
        try:
            rel = str(p.relative_to(base)).replace("\\", "/")
            rows.append({"path": rel, "symbols": extract_symbols(p), "fingerprint": file_fingerprint(p)})
        except Exception:
            continue
    return rows
