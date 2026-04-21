from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Optional

import pymysql
from pymysql.cursors import DictCursor

from app.runner_config import runner_settings


@dataclass
class TaskRecord:
    id: int
    task_key: str
    sample_id: str
    source_file: str
    essay_title: str
    essay_content: str
    grade_level: str
    requirements: str
    image_paths_json: str
    battle_id: int | None
    status: str
    retry_count: int
    last_error: str | None


class TaskStoreMySQL:
    @contextmanager
    def _conn(self):
        conn = pymysql.connect(
            host=runner_settings.db_host,
            port=runner_settings.db_port,
            user=runner_settings.db_user,
            password=runner_settings.db_password,
            database=runner_settings.db_name,
            charset="utf8mb4",
            autocommit=True,
            cursorclass=DictCursor,
        )
        try:
            yield conn
        finally:
            conn.close()

    def upsert_pending(
        self,
        task_key: str,
        sample_id: str,
        source_file: str,
        essay_title: str,
        essay_content: str,
        grade_level: str,
        requirements: str,
        image_paths_json: str,
    ) -> None:
        sql = """
        INSERT INTO agent_review_task
          (task_key, sample_id, source_file, essay_title, essay_content, grade_level, requirements, image_paths_json, status)
        VALUES
          (%s, %s, %s, %s, %s, %s, %s, %s, 'PENDING')
        ON DUPLICATE KEY UPDATE
          source_file = VALUES(source_file),
          essay_title = VALUES(essay_title),
          essay_content = VALUES(essay_content),
          grade_level = VALUES(grade_level),
          requirements = VALUES(requirements),
          image_paths_json = VALUES(image_paths_json)
        """
        essay_title = (essay_title or "")[:9999]
        source_file = (source_file or "")[:255]
        grade_level = (grade_level or "")[:20]
        requirements = (requirements or "")[:1000]

        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(
                sql,
                (task_key, sample_id, source_file, essay_title, essay_content, grade_level, requirements, image_paths_json),
            )

    def fetch_runnable(self, limit: int) -> list[TaskRecord]:
        sql = """
        SELECT id, task_key, sample_id, source_file, essay_title, essay_content, grade_level, requirements, image_paths_json, battle_id, status, retry_count, last_error
        FROM agent_review_task
        WHERE status IN ('PENDING','FAILED') AND retry_count < %s
        ORDER BY id ASC
        LIMIT %s
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (runner_settings.max_retry, limit))
            rows = cur.fetchall()
        return [TaskRecord(**row) for row in rows]

    def mark_created(self, task_key: str, battle_id: int) -> None:
        self._update(task_key, "CREATED", battle_id=battle_id, last_error=None)

    def mark_generated(self, task_key: str, battle_id: int) -> None:
        self._update(task_key, "GENERATED", battle_id=battle_id, last_error=None)

    def mark_voted(self, task_key: str, payload: dict[str, Any]) -> None:
        agent_winner = None
        if isinstance(payload, dict):
            agent_winner = payload.get("agent_winner")
            if agent_winner is None:
                review_payload = payload.get("review_payload")
                if isinstance(review_payload, dict):
                    agent_winner = review_payload.get("overall_winner")
            if agent_winner is None:
                vote_resp = payload.get("vote_response")
                if isinstance(vote_resp, dict):
                    agent_winner = vote_resp.get("overall_winner")

        sql = """
        UPDATE agent_review_task
        SET status='VOTED', agent_winner=%s, review_payload=%s, last_error=NULL, updated_at=NOW()
        WHERE task_key=%s
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (agent_winner, json.dumps(payload, ensure_ascii=False, default=str), task_key))

    def mark_failed(self, task_key: str, error: str) -> None:
        sql = """
        UPDATE agent_review_task
        SET status='FAILED', retry_count=retry_count+1, last_error=%s, updated_at=NOW()
        WHERE task_key=%s
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (error[:2000], task_key))

    def _update(self, task_key: str, status: str, battle_id: Optional[int], last_error: Optional[str]) -> None:
        sql = """
        UPDATE agent_review_task
        SET status=%s, battle_id=%s, last_error=%s, updated_at=NOW()
        WHERE task_key=%s
        """
        with self._conn() as conn, conn.cursor() as cur:
            cur.execute(sql, (status, battle_id, last_error, task_key))
