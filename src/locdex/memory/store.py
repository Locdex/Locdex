from __future__ import annotations

import sqlite3
from pathlib import Path


class MemoryStore:
    def __init__(self, path: str | Path):
        self.conn = sqlite3.connect(path)
        self.conn.execute("CREATE TABLE IF NOT EXISTS outcomes (task TEXT, summary TEXT, success INTEGER)")
        self.conn.commit()

    def save(self, task: str, summary: str, success: bool) -> None:
        self.conn.execute("INSERT INTO outcomes VALUES (?, ?, ?)", (task, summary, int(success)))
        self.conn.commit()
