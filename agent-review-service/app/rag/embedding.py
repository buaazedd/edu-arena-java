"""Embedding 抽象与具体实现。

支持：
- OpenAIEmbedding（默认，复用 AiHubMix）
- LocalBgeEmbedding（占位；需额外安装 sentence-transformers；默认不启用）

通过 settings.embedding_provider 切换。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Sequence

from openai import OpenAI

from app.common.logger import logger
from app.settings import get_settings


class EmbeddingProvider(ABC):
    """Embedding 抽象接口。"""

    @abstractmethod
    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        """把文本列表编码为向量列表。"""

    def embed_one(self, text: str) -> List[float]:
        return self.embed([text])[0]


class OpenAIEmbedding(EmbeddingProvider):
    """OpenAI 兼容接口的 Embedding。"""

    def __init__(self, *, api_key: str, base_url: str, model: str):
        # NOTE: OpenAI v1 的 embedding endpoint 为 /v1/embeddings；
        # 基地址 base_url 中不应重复包含 /chat/completions 之类路径。
        # AiHubMix 基地址应为 https://api.aihubmix.com/v1
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self._model = model

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        if not texts:
            return []
        resp = self._client.embeddings.create(model=self._model, input=list(texts))
        return [d.embedding for d in resp.data]


class _FallbackEmbedding(EmbeddingProvider):
    """退化实现：不做真实 embedding，仅按文本 hash 产生固定长度伪向量。

    **仅用于离线/无网开发与 smoke 测试**，不应在生产使用。
    """

    DIM = 32

    def embed(self, texts: Sequence[str]) -> List[List[float]]:
        import hashlib

        vectors: List[List[float]] = []
        for t in texts:
            h = hashlib.sha256(t.encode("utf-8")).digest()
            vec = [(b - 128) / 128.0 for b in h[: self.DIM]]
            vectors.append(vec)
        return vectors


_PROVIDER_CACHE: EmbeddingProvider | None = None


def get_embedding_provider() -> EmbeddingProvider:
    """根据配置返回 embedding 提供方（全局单例）。"""
    global _PROVIDER_CACHE
    if _PROVIDER_CACHE is not None:
        return _PROVIDER_CACHE

    s = get_settings()
    provider = s.embedding_provider.lower()
    if provider == "openai" and s.ai_api_key:
        _PROVIDER_CACHE = OpenAIEmbedding(
            api_key=s.ai_api_key,
            base_url=s.ai_base_url,
            model=s.embedding_model,
        )
        logger.info(f"Embedding: OpenAI model={s.embedding_model}")
    else:
        logger.warning(
            f"Embedding 回退到 fallback 模式 (provider={provider}, has_key={bool(s.ai_api_key)}). "
            "请在生产配置真实 embedding。"
        )
        _PROVIDER_CACHE = _FallbackEmbedding()
    return _PROVIDER_CACHE
