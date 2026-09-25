from __future__ import annotations

import re
import sqlite3
import time
from collections import Counter


def _tokens(text: str) -> Counter[str]:
    """Return a lightweight local token-frequency representation.

    Locdex deliberately avoids a second embedding-model dependency here. This
    keeps the base package small and prevents semantic memory from silently
    downloading another model on first use.
    """
    words = re.findall(r"[A-Za-z_][A-Za-z0-9_]{1,}", text.lower())
    return Counter(words)


def _cosine_like(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    overlap = sum(min(a[token], b[token]) for token in a.keys() & b.keys())
    denom = (sum(a.values()) * sum(b.values())) ** 0.5
    return float(overlap / denom) if denom else 0.0


def init_db(path: str = "agent_memory.db"):
    conn = sqlite3.connect(path)
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
    # `embedding` remains in the schema for backward compatibility with older
    # databases, but v0.1 does not require an embedding model.
    conn.execute(
        "INSERT INTO memory (task, outcome, success, embedding, timestamp) VALUES (?,?,?,?,?)",
        (task, outcome, int(success), None, time.time()),
    )
    conn.commit()


def recall_similar(conn, task: str, k: int = 3) -> list[str]:
    rows = conn.execute(
        "SELECT id, task, outcome, timestamp, access_count FROM memory"
    ).fetchall()
    if not rows:
        return []

    query_tokens = _tokens(task)
    now = time.time()
    scored = []
    for row in rows:
        row_tokens = _tokens(str(row[1] or ""))
        similarity = _cosine_like(query_tokens, row_tokens)
        recency_weight = 1 / (1 + (now - float(row[3] or now)) / 86400 / 30)
        success_bonus = 0.05 if row[2] else 0.0
        score = (similarity * 0.8) + (recency_weight * 0.15) + success_bonus
        scored.append((score, row))

    scored.sort(key=lambda item: -item[0])
    top = scored[: max(0, k)]
    for _, row in top:
        conn.execute("UPDATE memory SET access_count = access_count + 1 WHERE id = ?", (row[0],))
    conn.commit()
    return [str(row[2]) for _, row in top if row[2]]
