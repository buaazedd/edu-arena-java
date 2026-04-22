"""ChromaDB 本地持久化封装（按集合隔离 rubric/exemplar/gold_case）。"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import List, Optional, Sequence

from app.common.logger import logger
from app.contracts.review_models import RagHit
from app.settings import get_settings

from .embedding import EmbeddingProvider, get_embedding_provider

# 懒加载 chromadb，避免冷启动时长
_chromadb = None


def _lazy_chroma():
    global _chromadb
    if _chromadb is None:
        import chromadb  # type: ignore

        _chromadb = chromadb
    return _chromadb


COLLECTIONS = ("rubric", "exemplar", "gold_case")


def _doc_id(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:24]


class ChromaStore:
    """ChromaDB 门面：按 collection 管理三类知识。"""

    def __init__(self, persist_dir: Optional[str] = None, embedding: Optional[EmbeddingProvider] = None):
        s = get_settings()
        self._persist_dir = Path(persist_dir or s.chroma_dir).expanduser().resolve()
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._embedding = embedding or get_embedding_provider()
        chromadb = _lazy_chroma()
        self._client = chromadb.PersistentClient(path=str(self._persist_dir))
        logger.info(f"ChromaStore persist_dir={self._persist_dir}")

    def _get_or_create(self, name: str):
        return self._client.get_or_create_collection(name=name, metadata={"hnsw:space": "cosine"})

    # -------- 写 --------

    def add_documents(
        self,
        collection: str,
        documents: Sequence[str],
        metadatas: Optional[Sequence[dict]] = None,
    ) -> int:
        if collection not in COLLECTIONS:
            raise ValueError(f"unknown collection: {collection}")
        if not documents:
            return 0
        col = self._get_or_create(collection)
        ids = [_doc_id(d) for d in documents]
        vectors = self._embedding.embed(list(documents))
        # ChromaDB 不接受空 dict metadata，需要转为 None 或带默认键
        resolved_metas = []
        for m in (metadatas or [None] * len(documents)):
            d = dict(m) if m else {}
            if not d:
                d = {"_placeholder": "true"}  # chromadb 拒绝空 dict
            resolved_metas.append(d)
        col.upsert(
            ids=ids,
            documents=list(documents),
            embeddings=vectors,
            metadatas=resolved_metas,
        )
        logger.info(f"[rag] upsert {len(documents)} docs into '{collection}'")
        return len(documents)

    # -------- 读 --------

    def query(self, collection: str, query_text: str, top_k: int = 3) -> List[RagHit]:
        if collection not in COLLECTIONS:
            raise ValueError(f"unknown collection: {collection}")
        col = self._get_or_create(collection)
        qvec = self._embedding.embed_one(query_text)
        # chroma 的 query 返回 dict of lists
        res = col.query(query_embeddings=[qvec], n_results=top_k)
        docs = (res.get("documents") or [[]])[0]
        metas = (res.get("metadatas") or [[]])[0]
        dists = (res.get("distances") or [[]])[0]
        hits: List[RagHit] = []
        for doc, meta, dist in zip(docs, metas, dists):
            # cosine distance -> similarity
            score = max(0.0, 1.0 - float(dist or 0))
            hits.append(
                RagHit(
                    source=collection,  # type: ignore[arg-type]
                    content=doc,
                    score=score,
                    metadata=dict(meta or {}),
                )
            )
        return hits

    def count(self, collection: str) -> int:
        return self._get_or_create(collection).count()

    def reset(self, collection: Optional[str] = None) -> None:
        """删除集合（谨慎使用）。"""
        if collection is None:
            for name in COLLECTIONS:
                self._client.delete_collection(name)
            logger.warning("[rag] 已重置所有集合")
        else:
            self._client.delete_collection(collection)
            logger.warning(f"[rag] 已重置集合 {collection}")


_STORE: Optional[ChromaStore] = None


def get_store() -> ChromaStore:
    global _STORE
    if _STORE is None:
        _STORE = ChromaStore()
    return _STORE
