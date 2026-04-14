"""Fallback conversation stage when DATABASE_URL is not set (e.g. local dev)."""

import sqlite3
import time
from pathlib import Path


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS wa_stage (
            wa_id TEXT PRIMARY KEY,
            stage TEXT NOT NULL,
            updated_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


class StageStore:
    def __init__(self, db_path: Path) -> None:
        self._conn = _connect(db_path)

    def get(self, wa_id: str) -> str:
        cur = self._conn.execute(
            "SELECT stage FROM wa_stage WHERE wa_id = ?", (wa_id,)
        )
        row = cur.fetchone()
        return row[0] if row else "greeting"

    def set(self, wa_id: str, stage: str) -> None:
        self._conn.execute(
            """
            INSERT INTO wa_stage (wa_id, stage, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(wa_id) DO UPDATE SET
                stage = excluded.stage,
                updated_at = excluded.updated_at
            """,
            (wa_id, stage, time.time()),
        )
        self._conn.commit()
