"""统一配置：读取 .env 环境变量。"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置（.env 驱动）。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ===== LLM =====
    ai_api_key: str = Field(default="", description="AiHubMix / OpenAI 兼容 API Key")
    ai_base_url: str = Field(default="https://api.aihubmix.com/v1")
    ai_review_model: str = Field(default="gpt-4o-mini", description="维度 Agent 使用模型")
    ai_arbitrator_model: str = Field(default="gpt-4o", description="仲裁 Agent 使用模型")
    ai_timeout: int = Field(default=60, ge=5, le=600)
    ai_max_retries: int = Field(default=3, ge=0, le=10)

    # ===== 对战平台 =====
    arena_base_url: str = Field(default="http://localhost:5001")
    arena_username: str = Field(default="admin")
    arena_password: str = Field(default="admin123")

    # ===== 本服务 =====
    review_host: str = Field(default="0.0.0.0")
    review_port: int = Field(default=8100, ge=1, le=65535)
    review_url: str = Field(default="http://localhost:8100")

    # ===== RAG =====
    chroma_dir: str = Field(default="./data/chroma")
    embedding_provider: str = Field(default="openai")  # openai | local_bge
    embedding_model: str = Field(default="text-embedding-3-small")

    # ===== 批量任务 =====
    batch_store_path: str = Field(default="./data/batch_tasks.sqlite")
    batch_concurrency: int = Field(default=3, ge=1, le=50)

    # ===== 日志 =====
    log_level: str = Field(default="INFO")
    log_dir: str = Field(default="./logs")

    # ===== 决策器阈值 =====
    dim_score_tie_threshold: float = Field(default=0.5, description="子维度A/B分差小于此值判 tie")

    @property
    def chroma_path(self) -> Path:
        return Path(self.chroma_dir).expanduser().resolve()

    @property
    def log_path(self) -> Path:
        return Path(self.log_dir).expanduser().resolve()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """全局唯一的 Settings 实例（通过 lru_cache 缓存）。"""
    return Settings()
