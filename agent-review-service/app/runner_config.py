from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class RunnerSettings:
    arena_base_url: str = os.getenv("ARENA_BASE_URL", "http://8.219.130.23")
    arena_username: str = os.getenv("ARENA_USERNAME", "agent_reviewer")
    arena_password: str = os.getenv("ARENA_PASSWORD", "123456")

    writing_dir: str = os.getenv("WRITING_DIR", os.path.abspath("../writing"))
    writing_file: str = os.getenv("WRITING_FILE", "label_cn.txt")
    writing_json_file: str | None = os.getenv("WRITING_JSON_FILE") or None

    prompt_version: str = os.getenv("PROMPT_VERSION", "agent_v1")
    batch_limit: int = int(os.getenv("BATCH_LIMIT", "50"))
    max_retry: int = int(os.getenv("MAX_RETRY", "3"))
    request_timeout_seconds: int = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))

    # MySQL（与 application.yml 同库）
    db_host: str = os.getenv("DB_HOST", "180.76.229.245")
    db_port: int = int(os.getenv("DB_PORT", "3306"))
    db_name: str = os.getenv("DB_NAME", "edu_arena")
    db_user: str = os.getenv("DB_USER", "root")
    db_password: str = os.getenv("DB_PASSWORD", "zyd123")


runner_settings = RunnerSettings()
