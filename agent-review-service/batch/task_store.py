"""任务状态存储：SQLite 实现，支持断点续跑。

表结构：
    batch_tasks(
        item_id TEXT PRIMARY KEY,
        battle_id INTEGER,
        stage TEXT NOT NULL,
        retry_count INTEGER DEFAULT 0,
        last_error TEXT,
        review_winner TEXT,
        vote_winner_side TEXT,
        latency_ms INTEGER DEFAULT 0,
        updated_at TEXT
    )
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Protocol

from app.common.logger import logger
from app.settings import get_settings

from .models import BatchJob, StageStatus


_SCHEMA = """
CREATE TABLE IF NOT EXISTS batch_tasks (
    item_id TEXT PRIMARY KEY,
    battle_id INTEGER,
    stage TEXT NOT NULL,
    retry_count INTEGER DEFAULT 0,
    last_error TEXT,
    review_winner TEXT,
    vote_winner_side TEXT,
    latency_ms INTEGER DEFAULT 0,
    updated_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_batch_tasks_stage ON batch_tasks(stage);
"""


class TaskStore(Protocol):
    def get(self, item_id: str) -> Optional[BatchJob]: ...
    def upsert(self, job: BatchJob) -> None: ...
    def list_unfinished(self) -> List[BatchJob]: ...


class SqliteTaskStore:
    """SQLite 实现，进程内线程安全。"""

    def __init__(self, path: Optional[str] = None) -> None:
        s = get_settings()
        self.path = Path(path or s.batch_store_path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        logger.info(f"[task_store] sqlite path={self.path}")

    def get(self, item_id: str) -> Optional[BatchJob]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM batch_tasks WHERE item_id = ?", (item_id,)
            )
            row = cur.fetchone()
        if row is None:
            return None
        return BatchJob(
            item_id=row["item_id"],
            battle_id=row["battle_id"],
            stage=StageStatus(row["stage"]),
            retry_count=row["retry_count"] or 0,
            last_error=row["last_error"],
            review_winner=row["review_winner"],
            vote_winner_side=row["vote_winner_side"],
            latency_ms=row["latency_ms"] or 0,
            updated_at=row["updated_at"],
        )

    def upsert(self, job: BatchJob) -> None:
        job.updated_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO batch_tasks(
                    item_id, battle_id, stage, retry_count, last_error,
                    review_winner, vote_winner_side, latency_ms, updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(item_id) DO UPDATE SET
                    battle_id=excluded.battle_id,
                    stage=excluded.stage,
                    retry_count=excluded.retry_count,
                    last_error=excluded.last_error,
                    review_winner=excluded.review_winner,
                    vote_winner_side=excluded.vote_winner_side,
                    latency_ms=excluded.latency_ms,
                    updated_at=excluded.updated_at
                """,
                (
                    job.item_id,
                    job.battle_id,
                    job.stage.value,
                    job.retry_count,
                    job.last_error,
                    job.review_winner,
                    job.vote_winner_side,
                    job.latency_ms,
                    job.updated_at,
                ),
            )

    def list_unfinished(self) -> List[BatchJob]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT item_id FROM batch_tasks WHERE stage NOT IN (?, ?)",
                (StageStatus.DONE.value, StageStatus.FAILED.value),
            )
            ids = [r["item_id"] for r in cur.fetchall()]
        return [j for j in (self.get(i) for i in ids) if j]

    def summary(self) -> dict:
        with self._lock:
            cur = self._conn.execute(
                "SELECT stage, COUNT(*) as n FROM batch_tasks GROUP BY stage"
            )
            rows = cur.fetchall()
        return {r["stage"]: r["n"] for r in rows}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


__all__ = ["TaskStore", "SqliteTaskStore"]
