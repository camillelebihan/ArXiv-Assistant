"""SQLite store of papers already sent, so nothing is posted twice."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class SeenStore:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(path)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS seen ("
            "arxiv_id TEXT PRIMARY KEY, "
            "sent_at TEXT DEFAULT CURRENT_TIMESTAMP)"
        )
        self._conn.commit()

    def is_seen(self, arxiv_id: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM seen WHERE arxiv_id = ?", (arxiv_id,)
        ).fetchone()
        return row is not None

    def mark_seen(self, arxiv_ids: list[str]) -> None:
        self._conn.executemany(
            "INSERT OR IGNORE INTO seen (arxiv_id) VALUES (?)",
            [(i,) for i in arxiv_ids],
        )
        self._conn.commit()
