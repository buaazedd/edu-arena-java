"""review nodes 独立单元测试：preprocess / dimension_agent / arbitrator / dispatch。"""
from __future__ import annotations

import pytest

from app.contracts.review_models import (
    ArbitrationResult,
    BattleContext,
    DimensionKey,
    DimensionScore,
    ExtractedPoints,
    RagHit,
)
from app.review.state import GraphState


# ─────────────── Preprocess Node ───────────────

class TestPreprocessNode:
    async def test_preprocess_basic(self, monkeypatch, fake_llm, sample_battle_context):
        """预处理节点应产出 extracted_a/b, skill_summary, rag_hits。"""
        from app.review.nodes import preprocess as pre_mod

        monkeypatch.setattr(pre_mod, "get_llm", lambda: fake_llm)
        monkeypatch.setattr(pre_mod, "_fetch_rag", lambda _ctx: {d.value: [] for d in DimensionKey})
        monkeypatch.setattr(pre_mod, "_run_skills", lambda _ctx: {"text_stats": {"a": {}, "b": {}}})

        state: GraphState = {"ctx": sample_battle_context, "errors": [], "trace": {}}
        result = await pre_mod.preprocess_node(state)

        assert "extracted_a" in result
        assert "extracted_b" in result
        assert isinstance(result["extracted_a"], ExtractedPoints)
        assert result["extracted_a"].side == "A"
        assert result["extracted_b"].side == "B"
        assert "skill_summary" in result
        assert "rag_hits" in result

    async def test_preprocess_llm_failure_fallback(self, monkeypatch, fake_llm, sample_battle_context):
        """LLM 抽取失败时应退化为空结构。"""
        from app.review.nodes import preprocess as pre_mod

        # 覆盖 achat_json 为抛异常
        async def failing_achat(**kwargs):
            raise Exception("LLM 网络错误")

        fake_llm.achat_json = failing_achat
        monkeypatch.setattr(pre_mod, "get_llm", lambda: fake_llm)
        monkeypatch.setattr(pre_mod, "_fetch_rag", lambda _ctx: {d.value: [] for d in DimensionKey})
        monkeypatch.setattr(pre_mod, "_run_skills", lambda _ctx: {})

        state: GraphState = {"ctx": sample_battle_context, "errors": [], "trace": {}}
        result = await pre_mod.preprocess_node(state)

        # 应仍然有 extracted_a/b（退化版本）
        assert result["extracted_a"].highlights == []
        assert result["extracted_b"].highlights == []

    def test_run_skills_with_real_skills(self, sample_battle_context):
        """使用真实 Skill 测试 _run_skills 函数。"""
        from app.review.nodes.preprocess import _run_skills

        summary = _run_skills(sample_battle_context)
        assert isinstance(summary, dict)
        # 至少应有 feedback_compare 和 text_stats
        assert "feedback_compare" in summary or "text_stats" in summary

    def test_fetch_rag_returns_all_dims(self, monkeypatch, sample_battle_context, tmp_path):
        """_fetch_rag 应为所有 6 个维度返回结果（可以是空列表）。"""
        from app.review.nodes.preprocess import _fetch_rag

        # 使用 fallback embedding 的 retriever
        from app.rag.store import ChromaStore
        from app.rag.retriever import Retriever
        import app.rag.retriever as ret_mod

        store = ChromaStore(persist_dir=str(tmp_path / "rag"))
        retriever = Retriever(store=store)
        monkeypatch.setattr(ret_mod, "_SINGLETON", retriever)

        result = _fetch_rag(sample_battle_context)
        assert set(result.keys()) == {d.value for d in DimensionKey}


# ─────────────── Dimension Agent Node ───────────────

class TestDimensionAgentNode:
    async def test_dimension_agent_basic(self, monkeypatch, fake_llm, sample_battle_context):
        """维度 Agent 应输出一个 DimensionScore。"""
        from app.review.nodes import dimension_agent as dim_mod

        monkeypatch.setattr(dim_mod, "get_llm", lambda: fake_llm)

        payload = {
            "ctx": sample_battle_context,
            "current_dim": DimensionKey.THEME,
            "skill_summary": {},
            "rag_hits_for_dim": [],
        }
        result = await dim_mod.dimension_agent_node(payload)
        assert "dimension_scores" in result
        assert len(result["dimension_scores"]) == 1
        score = result["dimension_scores"][0]
        assert isinstance(score, DimensionScore)
        assert score.dim == DimensionKey.THEME

    async def test_dimension_agent_all_dims(self, monkeypatch, fake_llm, sample_battle_context):
        """所有 6 个维度都能正常执行。"""
        from app.review.nodes import dimension_agent as dim_mod

        monkeypatch.setattr(dim_mod, "get_llm", lambda: fake_llm)

        for dim in DimensionKey:
            payload = {
                "ctx": sample_battle_context,
                "current_dim": dim,
                "skill_summary": {},
                "rag_hits_for_dim": [],
            }
            result = await dim_mod.dimension_agent_node(payload)
            assert result["dimension_scores"][0].dim == dim

    async def test_dimension_agent_llm_failure_fallback(self, monkeypatch, fake_llm, sample_battle_context):
        """LLM 失败时 Agent 应降级为 tie 分数。"""
        from app.review.nodes import dimension_agent as dim_mod

        async def failing_achat(**kwargs):
            raise Exception("timeout")

        fake_llm.achat_json = failing_achat
        monkeypatch.setattr(dim_mod, "get_llm", lambda: fake_llm)

        payload = {
            "ctx": sample_battle_context,
            "current_dim": DimensionKey.THEME,
            "skill_summary": {},
            "rag_hits_for_dim": [],
        }
        result = await dim_mod.dimension_agent_node(payload)
        score = result["dimension_scores"][0]
        assert score.winner == "tie"
        assert score.confidence == 0.2  # fallback 低置信度

    async def test_dimension_agent_with_rag_hits(self, monkeypatch, fake_llm, sample_battle_context):
        """包含 RAG 命中结果时正常工作。"""
        from app.review.nodes import dimension_agent as dim_mod

        monkeypatch.setattr(dim_mod, "get_llm", lambda: fake_llm)

        rag_hits = [
            RagHit(source="rubric", content="主旨需紧扣题意", score=0.85),
            RagHit(source="exemplar", content="优秀范例", score=0.72),
        ]
        payload = {
            "ctx": sample_battle_context,
            "current_dim": DimensionKey.THEME,
            "skill_summary": {"text_stats": {"a_chars": 100, "b_chars": 120}},
            "rag_hits_for_dim": rag_hits,
        }
        result = await dim_mod.dimension_agent_node(payload)
        assert result["dimension_scores"][0].dim == DimensionKey.THEME


# ─────────────── Dispatch Node ───────────────

class TestDispatchNode:
    def test_dispatch_produces_6_sends(self, sample_battle_context):
        """dispatch 应为每个维度产出一个 Send。"""
        from app.review.nodes.dispatch import dispatch_dimensions
        from langgraph.types import Send

        state: GraphState = {
            "ctx": sample_battle_context,
            "skill_summary": {"test": True},
            "rag_hits": {d.value: [] for d in DimensionKey},
        }
        sends = dispatch_dimensions(state)
        assert len(sends) == 6
        assert all(isinstance(s, Send) for s in sends)
        # 每个 Send 的目标节点应为 dimension_agent
        for s in sends:
            assert s.node == "dimension_agent"

    def test_dispatch_carries_correct_data(self, sample_battle_context):
        """每个 Send 应携带对应维度和上下文。"""
        from app.review.nodes.dispatch import dispatch_dimensions

        state: GraphState = {
            "ctx": sample_battle_context,
            "skill_summary": {"key": "val"},
            "rag_hits": {"theme": [RagHit(source="rubric", content="test", score=0.5)]},
        }
        sends = dispatch_dimensions(state)
        # 检查第一个 Send（theme）
        theme_send = sends[0]
        assert theme_send.arg["current_dim"] == DimensionKey.THEME
        assert theme_send.arg["ctx"] == sample_battle_context

    def test_dispatch_handles_empty_rag_hits(self, sample_battle_context):
        """rag_hits 为空时不报错。"""
        from app.review.nodes.dispatch import dispatch_dimensions

        state: GraphState = {
            "ctx": sample_battle_context,
            "skill_summary": {},
            "rag_hits": {},
        }
        sends = dispatch_dimensions(state)
        assert len(sends) == 6
        for s in sends:
            assert s.arg.get("rag_hits_for_dim") == []


# ─────────────── Arbitrator Node ───────────────

class TestArbitratorNode:
    async def test_arbitrator_heuristic(self, all_dimension_scores):
        """OVERALL 置信度 >= 0.6 时走启发式，不调 LLM。"""
        from app.review.nodes.arbitrator import arbitrator_node

        state = {"dimension_scores": all_dimension_scores}
        result = await arbitrator_node(state)
        assert "arbitration" in result
        arb = result["arbitration"]
        assert isinstance(arb, ArbitrationResult)
        assert arb.final_winner == "A"  # OVERALL.winner == A
        assert "启发式" in arb.rationale

    async def test_arbitrator_low_confidence_calls_llm(self, monkeypatch, fake_llm):
        """OVERALL 置信度 < 0.6 时应调用 LLM 仲裁。"""
        from app.review.nodes import arbitrator as arb_mod
        monkeypatch.setattr(arb_mod, "get_llm", lambda: fake_llm)

        scores = [
            DimensionScore(dim=d, score_a=3, score_b=3, winner="tie", reason="ok", confidence=0.4)
            for d in DimensionKey
        ]
        # OVERALL 设为低置信度
        scores[-1] = DimensionScore(
            dim=DimensionKey.OVERALL, score_a=3, score_b=3,
            winner="A", reason="slightly A", confidence=0.4
        )
        state = {"dimension_scores": scores}
        result = await arb_mod.arbitrator_node(state)
        arb = result["arbitration"]
        # LLM mock 返回 A，与 OVERALL 一致
        assert arb.final_winner == "A"

    async def test_arbitrator_llm_disagree_forces_overall(self, monkeypatch, fake_llm):
        """LLM 仲裁与 OVERALL 不一致时，应强制回退到 OVERALL.winner。"""
        from app.review.nodes import arbitrator as arb_mod

        async def disagree_achat(*, system, user, **kwargs):
            return {
                "final_winner": "B",  # 故意与 OVERALL 不一致
                "overall_confidence": 0.9,
                "rationale": "B wins",
                "adjusted_dimensions": [],
            }

        fake_llm.achat_json = disagree_achat
        monkeypatch.setattr(arb_mod, "get_llm", lambda: fake_llm)

        scores = [
            DimensionScore(dim=d, score_a=3, score_b=3, winner="tie", reason="ok", confidence=0.4)
            for d in DimensionKey
        ]
        scores[-1] = DimensionScore(
            dim=DimensionKey.OVERALL, score_a=4, score_b=3,
            winner="A", reason="A better", confidence=0.5
        )
        state = {"dimension_scores": scores}
        result = await arb_mod.arbitrator_node(state)
        # 应被强制回退为 A（OVERALL.winner）
        assert result["arbitration"].final_winner == "A"

    async def test_arbitrator_llm_failure_fallback(self, monkeypatch, fake_llm):
        """LLM 仲裁失败时应走启发式。"""
        from app.review.nodes import arbitrator as arb_mod

        async def fail_achat(**kwargs):
            raise Exception("timeout")

        fake_llm.achat_json = fail_achat
        monkeypatch.setattr(arb_mod, "get_llm", lambda: fake_llm)

        scores = [
            DimensionScore(dim=d, score_a=4, score_b=3, winner="A", reason="ok", confidence=0.4)
            for d in DimensionKey
        ]
        state = {"dimension_scores": scores}
        result = await arb_mod.arbitrator_node(state)
        arb = result["arbitration"]
        assert arb.final_winner == "A"
        assert "失败" in arb.rationale

    async def test_arbitrator_missing_scores(self, fake_llm, monkeypatch):
        """不足 6 个维度评分时不崩溃。"""
        from app.review.nodes import arbitrator as arb_mod
        monkeypatch.setattr(arb_mod, "get_llm", lambda: fake_llm)

        scores = [
            DimensionScore(dim=DimensionKey.THEME, score_a=4, score_b=3, winner="A", reason="ok", confidence=0.8),
            DimensionScore(dim=DimensionKey.OVERALL, score_a=4, score_b=3, winner="A", reason="ok", confidence=0.8),
        ]
        state = {"dimension_scores": scores}
        result = await arb_mod.arbitrator_node(state)
        assert result["arbitration"].final_winner == "A"
