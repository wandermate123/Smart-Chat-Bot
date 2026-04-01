import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def _connect(path: Path) -> sqlite3.Connection:
    try:
        if path.parent.as_posix() not in ("/", "/tmp"):
            path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.warning("Using /tmp for idempotency (mkdir failed: %s)", e)
        path = Path("/tmp/wandermate-idempotency.db")
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS processed_wamid (
            wam_id TEXT PRIMARY KEY,
            created_at REAL NOT NULL
        )
        """
    )
    conn.commit()
    return conn


class IdempotencyStore:
    def __init__(self, db_path: Path) -> None:
        self._conn = _connect(db_path)

    def seen(self, wam_id: str) -> bool:
        cur = self._conn.execute(
            "SELECT 1 FROM processed_wamid WHERE wam_id = ?", (wam_id,)
        )
        return cur.fetchone() is not None

    def mark(self, wam_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO processed_wamid (wam_id, created_at) VALUES (?, ?)",
            (wam_id, time.time()),
        )
        self._conn.commit()
