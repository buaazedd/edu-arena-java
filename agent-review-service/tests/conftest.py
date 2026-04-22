"""Pytest 全局夹具：确保测试环境可独立运行，不触发真实 LLM/网络。"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

# 让测试可以 `from app...` / `from batch...`
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


# ─────────────── pytest-asyncio 全局模式 ───────────────
def pytest_configure(config):
    """设置 asyncio 模式为 auto，省去每个测试都标 @pytest.mark.asyncio。"""
    config.addinivalue_line("markers", "asyncio: mark test as async")


# ─────────────── 环境隔离 ───────────────
@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    """为每个测试注入安全的环境变量，避免触发真实 LLM/网络/文件系统。"""
    monkeypatch.setenv("AI_API_KEY", "test-key")
    monkeypatch.setenv("AI_BASE_URL", "http://localhost:0/v1")
    monkeypatch.setenv("AI_REVIEW_MODEL", "test-model")
    monkeypatch.setenv("AI_ARBITRATOR_MODEL", "test-model")
    monkeypatch.setenv("AI_TIMEOUT", "5")
    monkeypatch.setenv("AI_MAX_RETRIES", "1")
    monkeypatch.setenv("ARENA_BASE_URL", "http://localhost:0")
    monkeypatch.setenv("ARENA_USERNAME", "test")
    monkeypatch.setenv("ARENA_PASSWORD", "test")
    monkeypatch.setenv("CHROMA_DIR", str(tmp_path / "chroma"))
    monkeypatch.setenv("BATCH_STORE_PATH", str(tmp_path / "batch.sqlite"))
    monkeypatch.setenv("LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "fallback")
    monkeypatch.setenv("REVIEW_URL", "http://localhost:0")

    # 清掉各模块的 lru_cache / 单例，保证每次测试拿到干净状态
    from app.settings import get_settings
    get_settings.cache_clear()

    yield

    # teardown: 清掉可能被测试创建的单例
    get_settings.cache_clear()
    _reset_singletons()


def _reset_singletons():
    """重置全局单例，避免测试间污染。"""
    import app.review.llm as llm_mod
    import app.rag.store as store_mod
    import app.rag.retriever as retriever_mod
    import app.rag.embedding as embed_mod

    llm_mod._SINGLETON = None
    store_mod._STORE = None
    retriever_mod._SINGLETON = None
    embed_mod._PROVIDER_CACHE = None

    # graph / service 的 lru_cache
    try:
        from app.review.graph import get_graph
        get_graph.cache_clear()
    except Exception:
        pass
    try:
        from app.review.service import get_service
        get_service.cache_clear()
    except Exception:
        pass


# ─────────────── 共享 Mock Factory ───────────────

class FakeLLMClient:
    """确定性 LLM mock：根据 system prompt 关键字返回不同的 JSON 结果。"""

    def __init__(self, overrides: Optional[Dict[str, dict]] = None):
        self._overrides = overrides or {}

    async def achat_json(
        self, *, system: str, user: str, model=None, temperature=0.0, images_base64=None
    ) -> dict:
        # 允许测试注入特定返回值
        for key, val in self._overrides.items():
            if key in system or key in user:
                return val

        # 预处理节点
        if "要点" in system or "抽取" in system:
            return {
                "highlights": ["亮点1"],
                "issues": ["问题1"],
                "suggestions": ["建议1"],
                "summary": "Mock 摘要",
                "word_count": 100,
            }
        # 仲裁节点
        if "仲裁" in system or "arbitrator" in system.lower():
            return {
                "final_winner": "A",
                "overall_confidence": 0.75,
                "rationale": "mock 仲裁",
                "adjusted_dimensions": [],
            }
        # 维度 Agent（默认）
        return {
            "score_a": 4.0,
            "score_b": 3.0,
            "winner": "A",
            "reason": "mock 理由",
            "evidence": ["mock 证据"],
            "confidence": 0.8,
        }

    def chat_json(self, **kwargs) -> dict:
        import asyncio
        return asyncio.run(self.achat_json(**kwargs))


@pytest.fixture
def fake_llm():
    """返回一个 FakeLLMClient 实例。"""
    return FakeLLMClient()


@pytest.fixture
def fake_llm_factory():
    """返回 FakeLLMClient 工厂，允许自定义返回值。"""
    return FakeLLMClient


@pytest.fixture
def sample_battle_context():
    """标准 BattleContext fixture。"""
    from app.contracts.review_models import BattleContext
    return BattleContext(
        battle_id=42,
        essay_title="记一次秋游",
        essay_content="秋天来了，树叶飘落，我们去公园玩。",
        grade_level="初中",
        requirements="请从主旨、想象力等维度评价",
        response_a="批改A：文章主题明确，语言流畅，想象力丰富。" * 20,
        response_b="批改B：文章结构清晰，但语言表达有待提高。" * 20,
    )


@pytest.fixture
def sample_review_request():
    """标准 ReviewRequest fixture。"""
    from app.contracts.review_dto import ReviewRequest
    return ReviewRequest(
        battle_id=42,
        essay_title="记一次秋游",
        response_a="批改A：文章主题明确，语言流畅，想象力丰富。" * 20,
        response_b="批改B：文章结构清晰，但语言表达有待提高。" * 20,
        essay_content="秋天来了，树叶飘落，我们去公园玩。",
        grade_level="初中",
        requirements="请从主旨、想象力等维度评价",
    )


@pytest.fixture
def all_dimension_scores():
    """覆盖 6 维度的标准 DimensionScore 列表（A 赢）。"""
    from app.contracts.review_models import DimensionKey, DimensionScore
    return [
        DimensionScore(dim=DimensionKey.THEME, score_a=4, score_b=3, winner="A", reason="A主旨更佳", confidence=0.8),
        DimensionScore(dim=DimensionKey.IMAGINATION, score_a=3.5, score_b=4, winner="B", reason="B更有创意", confidence=0.7),
        DimensionScore(dim=DimensionKey.LOGIC, score_a=4, score_b=4, winner="tie", reason="逻辑相当", confidence=0.9),
        DimensionScore(dim=DimensionKey.LANGUAGE, score_a=4, score_b=3, winner="A", reason="A语言更好", confidence=0.85),
        DimensionScore(dim=DimensionKey.WRITING, score_a=3, score_b=3, winner="tie", reason="书写相当", confidence=0.9),
        DimensionScore(dim=DimensionKey.OVERALL, score_a=4, score_b=3, winner="A", reason="A整体更优", confidence=0.8),
    ]
