from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv


load_dotenv()


def _env_bool(key: str, default: str = "false") -> bool:
    return os.getenv(key, default).strip().lower() in {"1", "true", "yes", "on"}


def _env_csv(key: str, default: str) -> List[str]:
    raw = os.getenv(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    service_name: str = "edu-arena-agent-review"
    review_version: str = "graph_v1.4.0"
    default_confidence_threshold: float = 0.65

    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "https://api.aihubmix.com/v1")
    llm_model: str = os.getenv("LLM_MODEL", "gpt-4o-mini")
    judge_panel_models: List[str] = field(
        default_factory=lambda: _env_csv(
            "JUDGE_PANEL_MODELS",
            "o3,gemini-2.5-pro,claude-opus-4-1-20250805",
        )
    )
    judge_panel_size: int = int(os.getenv("JUDGE_PANEL_SIZE", "3"))
    aggregate_model: str = os.getenv("AGGREGATE_MODEL", "")

    # RAG / Vector DB
    vector_db_path: str = os.getenv("VECTOR_DB_PATH", os.path.abspath("./data/chroma"))

    # Embedding backend
    # local: 使用本地路径/本地模型名（推荐离线）
    # api:   使用 OpenAI 兼容 embedding API（推荐 AIHubMix 的 gemini-embedding-001）
    embedding_provider: str = os.getenv("EMBEDDING_PROVIDER", "local")

    # local provider
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-zh-v1.5")

    # api provider
    aihubmix_api_key: str = os.getenv("AIHUBMIX_API_KEY", "")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", os.getenv("AIHUBMIX_API_KEY", ""))
    embedding_api_base_url: str = os.getenv("EMBEDDING_API_BASE_URL", "https://aihubmix.com/v1")
    embedding_api_model: str = os.getenv("EMBEDDING_API_MODEL", "gemini-embedding-001")

    # 当 local 初始化失败时是否自动降级到 api
    embedding_api_fallback_enabled: bool = _env_bool("EMBEDDING_API_FALLBACK_ENABLED", "true")

    # 当 local + api 都不可用时是否降级到本地轻量哈希 embedding（仅开发联调）
    embedding_lite_fallback_enabled: bool = _env_bool("EMBEDDING_LITE_FALLBACK_ENABLED", "true")

    # reranker（AIHubMix /v1/rerank）
    rerank_enabled: bool = _env_bool("RERANK_ENABLED", "true")
    rerank_model: str = os.getenv("RERANK_MODEL", "qwen3-reranker-4b")
    rerank_endpoint: str = os.getenv("RERANK_ENDPOINT", "https://aihubmix.com/v1/rerank")
    rerank_api_key: str = os.getenv("RERANK_API_KEY", os.getenv("AIHUBMIX_API_KEY", ""))
    rerank_candidate_multiplier: int = int(os.getenv("RERANK_CANDIDATE_MULTIPLIER", "4"))
    rerank_timeout_seconds: int = int(os.getenv("RERANK_TIMEOUT_SECONDS", "20"))

    rag_top_k_rubric: int = int(os.getenv("RAG_TOP_K_RUBRIC", "3"))
    rag_top_k_exemplar: int = int(os.getenv("RAG_TOP_K_EXEMPLAR", "2"))
    rag_top_k_gold_case: int = int(os.getenv("RAG_TOP_K_GOLD_CASE", "2"))
    rag_top_k_risk: int = int(os.getenv("RAG_TOP_K_RISK", "2"))


settings = Settings()
