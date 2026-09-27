from __future__ import annotations

from locdex.memory import init_db, recall_similar, save_memory


def test_memory_requires_no_embedding_model(tmp_path):
    conn = init_db(str(tmp_path / "memory.db"))
    save_memory(conn, "fix authentication token bug", "updated auth token validation", True)
    save_memory(conn, "add invoice export", "added CSV export", True)

    recalled = recall_similar(conn, "authentication validation bug", k=1)
    assert recalled == ["updated auth token validation"]
