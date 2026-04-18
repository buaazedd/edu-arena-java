from __future__ import annotations

import hashlib
import logging
import math
import os
from typing import Dict, List

import requests
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from openai import OpenAI

from app.config import settings
from app.models import RagSearchHit


logger = logging.getLogger(__name__)

INDEX_TO_COLLECTION = {
    "rubric": "rubric_index",
    "exemplar": "exemplar_index",
    "gold_case": "gold_case_index",
    "error_pattern": "error_pattern_index",
}


class LiteHashEmbeddings(Embeddings):
    """
    轻量兜底 embedding：用于开发联调，不保证语义质量。
    当本地模型和API都不可用时，保证服务可启动与接口可测。
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _encode(self, text: str) -> List[float]:
        vec = [0.0] * self.dim
        if not text:
            return vec
        for token in text.split():
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            sign = 1.0 if (h % 2 == 0) else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._encode(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._encode(text)


class ApiCompatibleEmbeddings(Embeddings):
    """
    直接调用 OpenAI 兼容 embedding 接口，绕过 LangChain 对某些 provider 的兼容性问题。
    """

    def __init__(self, model: str, api_key: str, base_url: str) -> None:
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        clean_texts = [text if text else " " for text in texts]
        if not clean_texts:
            return []
        response = self.client.embeddings.create(model=self.model, input=clean_texts)
        return [item.embedding for item in response.data]

    def embed_query(self, text: str) -> List[float]:
        response = self.client.embeddings.create(model=self.model, input=text or " ")
        return response.data[0].embedding


class RetrievalService:
    def __init__(self) -> None:
        os.makedirs(settings.vector_db_path, exist_ok=True)
        self.emb = self._build_embedding()
        self._stores: Dict[str, Chroma] = {}

    def _build_api_embeddings(self) -> Embeddings:
        return ApiCompatibleEmbeddings(
            model=settings.embedding_api_model,
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_api_base_url,
        )

    def _build_embedding(self):
        provider = settings.embedding_provider.lower()

        if provider == "api":
            logger.info("Embedding provider=api, model=%s", settings.embedding_api_model)
            if not settings.embedding_api_key:
                if settings.embedding_lite_fallback_enabled:
                    logger.warning("EMBEDDING_API_KEY missing, use lite embedding fallback")
                    return LiteHashEmbeddings()
                raise RuntimeError("EMBEDDING_API_KEY is required when EMBEDDING_PROVIDER=api")
            return self._build_api_embeddings()

        # default local (lazy import，避免 API 模式下硬依赖本地 embedding 包)
        try:
            from langchain_huggingface import HuggingFaceEmbeddings

            logger.info("Embedding provider=local, model=%s", settings.embedding_model)
            return HuggingFaceEmbeddings(model_name=settings.embedding_model)
        except Exception as ex:
            if settings.embedding_api_fallback_enabled and settings.embedding_api_key:
                logger.warning(
                    "Local embedding init failed, fallback to api embedding. error=%s", ex
                )
                return self._build_api_embeddings()

            if settings.embedding_lite_fallback_enabled:
                logger.warning(
                    "Local/API embedding unavailable, fallback to lite hash embeddings. error=%s",
                    ex,
                )
                return LiteHashEmbeddings()

            raise RuntimeError(
                "Embedding init failed. Configure local model path, or API key, or enable lite fallback."
            ) from ex

    def _store(self, index: str) -> Chroma:
        collection = INDEX_TO_COLLECTION[index]
        if collection not in self._stores:
            self._stores[collection] = Chroma(
                collection_name=collection,
                embedding_function=self.emb,
                persist_directory=settings.vector_db_path,
            )
        return self._stores[collection]

    def _rerank(self, query: str, hits: List[RagSearchHit], top_k: int) -> List[RagSearchHit]:
        if not settings.rerank_enabled or not hits:
            return hits[:top_k]

        if not settings.rerank_api_key:
            logger.warning("RERANK_ENABLED=true but RERANK_API_KEY empty; skip rerank")
            return hits[:top_k]

        documents = [h.text for h in hits]
        payload = {
            "model": settings.rerank_model,
            "query": query,
            "top_n": min(top_k, len(documents)),
            "documents": documents,
            "return_documents": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.rerank_api_key}",
        }

        try:
            resp = requests.post(
                settings.rerank_endpoint,
                headers=headers,
                json=payload,
                timeout=settings.rerank_timeout_seconds,
            )
            resp.raise_for_status()
            body = resp.json()

            ranked = body.get("results") or body.get("data") or []
            if not ranked:
                return hits[:top_k]

            reordered: List[RagSearchHit] = []
            for item in ranked:
                idx = item.get("index")
                if idx is None or idx < 0 or idx >= len(hits):
                    continue
                hit = hits[idx]
                score = item.get("relevance_score")
                if score is not None:
                    hit.score = float(score)
                reordered.append(hit)

            return reordered[:top_k] if reordered else hits[:top_k]
        except Exception as ex:
            logger.warning("rerank failed, fallback to vector order. error=%s", ex)
            return hits[:top_k]

    def upsert_documents(self, index: str, docs: List[dict]) -> int:
        store = self._store(index)
        documents = []
        ids = []
        for d in docs:
            metadata = d.get("metadata", {}) or {}
            metadata.setdefault("id", d["id"])
            documents.append(Document(page_content=d["text"], metadata=metadata, id=d["id"]))
            ids.append(d["id"])
        store.add_documents(documents=documents, ids=ids)
        return len(ids)

    def search(self, index: str, query: str, top_k: int, where: Dict | None = None) -> List[RagSearchHit]:
        store = self._store(index)
        candidate_k = max(top_k, top_k * settings.rerank_candidate_multiplier)
        results = store.similarity_search_with_relevance_scores(
            query=query,
            k=candidate_k,
            filter=where or None,
        )

        hits: List[RagSearchHit] = []
        for doc, score in results:
            hits.append(
                RagSearchHit(
                    id=str(doc.metadata.get("id", "")),
                    score=float(score),
                    text=doc.page_content,
                    metadata=doc.metadata,
                )
            )

        return self._rerank(query=query, hits=hits, top_k=top_k)

    def get_rubric_context(self, dimensions: List[str], version: str) -> List[dict]:
        contexts: List[dict] = []
        for d in dimensions:
            hits = self.search(
                "rubric",
                query=f"{d} 评分标准 {version}",
                top_k=settings.rag_top_k_rubric,
                where={"dimension": d},
            )
            contexts.append({"dimension": d, "hits": [h.model_dump() for h in hits]})
        return contexts

    def get_dimension_context(self, dimension: str, query_text: str) -> Dict:
        exemplars = self.search(
            "exemplar",
            query=f"{dimension} {query_text}",
            top_k=settings.rag_top_k_exemplar,
            where={"dimension": dimension},
        )
        gold_cases = self.search(
            "gold_case",
            query=f"{dimension} 相似对战判例 {query_text}",
            top_k=settings.rag_top_k_gold_case,
            where={"dimension": dimension},
        )
        risks = self.search(
            "error_pattern",
            query=f"{dimension} 常见问题 风险模式",
            top_k=settings.rag_top_k_risk,
            where={"dimension": dimension},
        )
        return {
            "exemplars": [h.model_dump() for h in exemplars],
            "gold_cases": [h.model_dump() for h in gold_cases],
            "risk_patterns": [h.model_dump() for h in risks],
        }
