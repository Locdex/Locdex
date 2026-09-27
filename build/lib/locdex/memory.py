from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter
from pathlib import Path

from platformdirs import user_data_dir


def _tokens(text: str) -> Counter[str]:
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower())
    return Counter(words)


def _cosine_like(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = sum(min(a[token], b[token]) for token in a.keys() & b.keys())
    denom = (sum(a.values()) * sum(b.values())) ** 0.5
    return float(overlap / denom) if denom else 0.0


def _default_memory_path() -> Path:
    data_dir = Path(user_data_dir("Locdex", "Locdex"))
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "agent_memory.db"


def init_db(path: str | None = None):
    if path == ":memory:":
        db_path = ":memory:"
    else:
        resolved = Path(path) if path is not None else _default_memory_path()
        resolved.parent.mkdir(parents=True, exist_ok=True)
        db_path = str(resolved)

    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS memory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task TEXT,
            outcome TEXT,
            success INTEGER,
            embedding BLOB,
            timestamp REAL,
            access_count INTEGER DEFAULT 0
        )
        """
    )
    conn.commit()
    return conn


def save_memory(conn, task: str, outcome: str, success: bool):
    conn.execute(
        "INSERT INTO memory (task, outcome, success, embedding, timestamp) VALUES (?,?,?,?,?)",
        (task, outcome, int(success), None, time.time()),
    )
    conn.commit()


def recall_similar(conn, task: str, k: int = 3) -> list[str]:
    rows = conn.execute(
        "SELECT id, task, outcome, success, timestamp, access_count FROM memory"
    ).fetchall()
    if not rows:
        return []

    query_tokens = _tokens(task)
    now = time.time()
    scored = []
    for row in rows:
        row_tokens = _tokens(str(row[1] or ""))
        similarity = _cosine_like(query_tokens, row_tokens)
        recency_weight = 1 / (1 + (now - float(row[4] or now)) / 86400 / 30)
        success_bonus = 0.05 if row[3] else 0.0
        score = (similarity * 0.8) + (recency_weight * 0.15) + success_bonus
        scored.append((score, row))

    scored.sort(key=lambda item: -item[0])
    top = scored[: max(0, k)]
    for _, row in top:
        conn.execute("UPDATE memory SET access_count = access_count + 1 WHERE id = ?", (row[0],))
    conn.commit()
    return [str(row[2]) for _, row in top if row[2]]
