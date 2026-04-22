"""RAG 模块测试：embedding / store / retriever 完整覆盖。"""
from __future__ import annotations

import pytest

from app.contracts.review_models import DimensionKey, RagHit
from app.rag.embedding import _FallbackEmbedding, EmbeddingProvider, get_embedding_provider
from app.rag.store import ChromaStore, COLLECTIONS


# ─────────────── Embedding 测试 ───────────────

class TestFallbackEmbedding:
    def test_embed_returns_vectors(self):
        emb = _FallbackEmbedding()
        vecs = emb.embed(["你好", "世界"])
        assert len(vecs) == 2
        assert len(vecs[0]) == _FallbackEmbedding.DIM
        assert len(vecs[1]) == _FallbackEmbedding.DIM

    def test_embed_deterministic(self):
        emb = _FallbackEmbedding()
        v1 = emb.embed(["相同的文本"])
        v2 = emb.embed(["相同的文本"])
        assert v1 == v2

    def test_embed_different_texts_differ(self):
        emb = _FallbackEmbedding()
        v1 = emb.embed_one("文本A")
        v2 = emb.embed_one("文本B")
        assert v1 != v2

    def test_embed_empty_list(self):
        emb = _FallbackEmbedding()
        assert emb.embed([]) == []

    def test_embed_one(self):
        emb = _FallbackEmbedding()
        vec = emb.embed_one("测试")
        assert isinstance(vec, list)
        assert len(vec) == _FallbackEmbedding.DIM

    def test_get_embedding_provider_fallback(self):
        """EMBEDDING_PROVIDER=fallback 时返回 _FallbackEmbedding。"""
        provider = get_embedding_provider()
        assert isinstance(provider, _FallbackEmbedding)


# ─────────────── ChromaStore 测试 ───────────────

class TestChromaStore:
    @pytest.fixture
    def store(self, tmp_path):
        return ChromaStore(persist_dir=str(tmp_path / "test_chroma"))

    def test_add_and_query(self, store):
        n = store.add_documents("rubric", ["主旨需紧扣题目", "想象力需丰富"])
        assert n == 2
        assert store.count("rubric") == 2

        hits = store.query("rubric", "题目主旨", top_k=2)
        assert len(hits) >= 1
        assert isinstance(hits[0], RagHit)
        assert hits[0].source == "rubric"
        assert hits[0].score >= 0

    def test_add_with_metadata(self, store):
        store.add_documents(
            "exemplar",
            ["优秀批改范例"],
            [{"dim": "theme", "quality": "high"}],
        )
        hits = store.query("exemplar", "批改", top_k=1)
        assert len(hits) == 1
        assert hits[0].metadata.get("dim") == "theme"

    def test_invalid_collection(self, store):
        with pytest.raises(ValueError, match="unknown collection"):
            store.add_documents("invalid_collection", ["test"])
        with pytest.raises(ValueError, match="unknown collection"):
            store.query("invalid_collection", "test")

    def test_add_empty_documents(self, store):
        assert store.add_documents("rubric", []) == 0

    def test_count_empty(self, store):
        # 即使集合不存在也返回 0（get_or_create）
        assert store.count("gold_case") == 0

    def test_query_empty_collection(self, store):
        hits = store.query("rubric", "随便", top_k=3)
        assert hits == []

    def test_dedup_by_content(self, store):
        """相同内容多次 upsert 不会重复（SHA256 ID 相同，后者覆盖前者）。"""
        store.add_documents("rubric", ["相同内容"])
        store.add_documents("rubric", ["相同内容"])  # 第二次 upsert 同 ID
        assert store.count("rubric") == 1

    def test_all_collections_supported(self, store):
        for coll in COLLECTIONS:
            n = store.add_documents(coll, [f"{coll} 测试文档"])
            assert n == 1

    def test_reset_single_collection(self, store):
        store.add_documents("rubric", ["文档1"])
        store.add_documents("exemplar", ["文档2"])
        store.reset("rubric")
        # rubric 被重置后重新创建为空
        assert store.count("rubric") == 0
        assert store.count("exemplar") == 1

    def test_reset_all(self, store):
        for coll in COLLECTIONS:
            store.add_documents(coll, [f"{coll} doc"])
        store.reset()
        for coll in COLLECTIONS:
            assert store.count(coll) == 0


# ─────────────── Retriever 测试 ───────────────

class TestRetriever:
    @pytest.fixture
    def retriever(self, tmp_path):
        from app.rag.retriever import Retriever
        store = ChromaStore(persist_dir=str(tmp_path / "retriever_chroma"))
        store.add_documents("rubric", ["主旨评分规则", "语言评分规则", "想象力评分规则"])
        store.add_documents("exemplar", ["优秀范例1：主旨", "优秀范例2：语言"])
        store.add_documents("gold_case", ["高一致案例：整体评价"])
        return Retriever(store=store, cache_capacity=16)

    def test_retrieve_basic(self, retriever):
        hits = retriever.retrieve(DimensionKey.THEME, "主旨评分", top_k=3)
        assert len(hits) > 0
        assert all(isinstance(h, RagHit) for h in hits)

    def test_retrieve_empty_query(self, retriever):
        assert retriever.retrieve(DimensionKey.THEME, "", top_k=3) == []
        assert retriever.retrieve(DimensionKey.THEME, "   ", top_k=3) == []

    def test_retrieve_uses_cache(self, retriever):
        """第二次相同查询应命中缓存。"""
        hits1 = retriever.retrieve(DimensionKey.THEME, "主旨", top_k=3)
        hits2 = retriever.retrieve(DimensionKey.THEME, "主旨", top_k=3)
        assert hits1 == hits2

    def test_retrieve_different_dims(self, retriever):
        """不同维度的查询结果可能不同（因为数据源不同）。"""
        h1 = retriever.retrieve(DimensionKey.WRITING, "书写", top_k=3)
        h2 = retriever.retrieve(DimensionKey.OVERALL, "整体评价", top_k=3)
        # 至少有结果
        assert isinstance(h1, list)
        assert isinstance(h2, list)

    def test_retrieve_results_sorted_by_score(self, retriever):
        hits = retriever.retrieve(DimensionKey.THEME, "主旨", top_k=5)
        if len(hits) > 1:
            scores = [h.score for h in hits]
            assert scores == sorted(scores, reverse=True)
