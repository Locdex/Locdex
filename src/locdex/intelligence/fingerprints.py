from __future__ import annotations

import hashlib
from pathlib import Path


def file_fingerprint(path: str | Path) -> str:
    p = Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest()
