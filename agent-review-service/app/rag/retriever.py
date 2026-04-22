"""Retriever 门面：按维度/查询跨三类集合召回，附带去重与缓存。"""
from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from typing import Dict, List, Optional

from app.common.logger import logger
from app.contracts.review_models import DimensionKey, RagHit

from .store import ChromaStore, get_store


class _LRU:
    """简易线程安全 LRU。"""

    def __init__(self, capacity: int = 256):
        self._cap = capacity
        self._d: OrderedDict[str, List[RagHit]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[List[RagHit]]:
        with self._lock:
            if key in self._d:
                self._d.move_to_end(key)
                return list(self._d[key])
            return None

    def put(self, key: str, value: List[RagHit]) -> None:
        with self._lock:
            self._d[key] = list(value)
            self._d.move_to_end(key)
            while len(self._d) > self._cap:
                self._d.popitem(last=False)


def _cache_key(dim: DimensionKey, query: str, top_k: int) -> str:
    h = hashlib.md5(query.encode("utf-8")).hexdigest()[:16]
    return f"{dim.value}:{top_k}:{h}"


# 各维度优先召回的集合顺序
_DIM_SOURCES: Dict[DimensionKey, List[str]] = {
    DimensionKey.THEME: ["rubric", "exemplar", "gold_case"],
    DimensionKey.IMAGINATION: ["rubric", "exemplar"],
    DimensionKey.LOGIC: ["rubric", "exemplar", "gold_case"],
    DimensionKey.LANGUAGE: ["rubric", "exemplar"],
    DimensionKey.WRITING: ["rubric"],
    DimensionKey.OVERALL: ["rubric", "gold_case", "exemplar"],
}


class Retriever:
    """维度感知的多集合召回器。"""

    def __init__(self, store: Optional[ChromaStore] = None, cache_capacity: int = 256):
        self._store = store or get_store()
        self._cache = _LRU(cache_capacity)

    def retrieve(
        self,
        dim: DimensionKey,
        query: str,
        top_k: int = 3,
    ) -> List[RagHit]:
        """按维度检索多集合，合并去重后截断到 top_k。"""
        if not query.strip():
            return []
        key = _cache_key(dim, query, top_k)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        sources = _DIM_SOURCES.get(dim, list(_DIM_SOURCES[DimensionKey.OVERALL]))
        hits: List[RagHit] = []
        for src in sources:
            try:
                hits.extend(self._store.query(src, query, top_k=top_k))
            except Exception as e:  # 向量库故障不影响主流程
                logger.warning(f"[rag] query '{src}' failed: {e}")

        # 去重（按 content hash），保留分数较高者
        dedup: Dict[str, RagHit] = {}
        for h in hits:
            k = hashlib.md5(h.content.encode("utf-8")).hexdigest()
            if k not in dedup or dedup[k].score < h.score:
                dedup[k] = h
        merged = sorted(dedup.values(), key=lambda x: x.score, reverse=True)[: top_k * 2]
        self._cache.put(key, merged)
        return merged


_SINGLETON: Optional[Retriever] = None


def get_retriever() -> Retriever:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = Retriever()
    return _SINGLETON
