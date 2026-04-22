"""LangGraph 工作流冒烟测试：用 monkeypatch 把 LLM 替换成确定性 mock。

测试覆盖：
- graph 可编译
- preprocess → 6×dimension_agent → arbitrator 全链路执行无异常
- 产出含 6 维 + final_winner
- 不同 winner 场景
"""
from __future__ import annotations

from app.contracts.review_models import DimensionKey


async def test_graph_smoke(monkeypatch, fake_llm, sample_review_request):
    """完整 DAG 冒烟：START → preprocess → 6×dim → arbitrator → END。"""
    from app.review import llm as llm_mod
    from app.review.nodes import arbitrator as arb_mod
    from app.review.nodes import dimension_agent as dim_mod
    from app.review.nodes import preprocess as pre_mod

    for mod in (llm_mod, arb_mod, dim_mod, pre_mod):
        if hasattr(mod, "get_llm"):
            monkeypatch.setattr(mod, "get_llm", lambda: fake_llm, raising=False)

    monkeypatch.setattr(pre_mod, "_fetch_rag", lambda _ctx: {d.value: [] for d in DimensionKey}, raising=True)
    monkeypatch.setattr(pre_mod, "_run_skills", lambda _ctx: {}, raising=True)

    from app.review import graph as g
    from app.review import service as svc_mod

    g.get_graph.cache_clear()
    svc_mod.get_service.cache_clear()

    from app.review import get_service
    service = get_service()
    resp = await service.arun(sample_review_request)
    assert resp.report.battle_id == 42
    assert resp.report.final_winner in ("A", "B", "tie")
    assert len(resp.report.dimensions) == 6
    assert resp.vote_payload.dim_overall in ("left", "right", "tie")


async def test_graph_b_wins(monkeypatch, fake_llm, sample_review_request):
    """测试 B 赢的场景。"""
    from app.review import llm as llm_mod
    from app.review.nodes import arbitrator as arb_mod
    from app.review.nodes import dimension_agent as dim_mod
    from app.review.nodes import preprocess as pre_mod

    # 覆盖 fake_llm 的 achat_json，返回 B 赢
    original_achat = fake_llm.achat_json

    async def b_wins_achat(*, system, user, **kwargs):
        if "仲裁" in system or "arbitrator" in system.lower():
            return {
                "final_winner": "B",
                "overall_confidence": 0.7,
                "rationale": "B wins",
                "adjusted_dimensions": [],
            }
        if "要点" in system or "抽取" in system:
            return await original_achat(system=system, user=user, **kwargs)
        return {
            "score_a": 3.0, "score_b": 4.0, "winner": "B",
            "reason": "B 更好", "evidence": [], "confidence": 0.8,
        }

    fake_llm.achat_json = b_wins_achat

    for mod in (llm_mod, arb_mod, dim_mod, pre_mod):
        if hasattr(mod, "get_llm"):
            monkeypatch.setattr(mod, "get_llm", lambda: fake_llm, raising=False)

    monkeypatch.setattr(pre_mod, "_fetch_rag", lambda _ctx: {d.value: [] for d in DimensionKey}, raising=True)
    monkeypatch.setattr(pre_mod, "_run_skills", lambda _ctx: {}, raising=True)

    from app.review import graph as g
    from app.review import service as svc_mod
    g.get_graph.cache_clear()
    svc_mod.get_service.cache_clear()

    from app.review import get_service
    resp = await get_service().arun(sample_review_request)
    assert resp.report.final_winner == "B"
    assert resp.vote_payload.dim_overall == "right"


async def test_graph_tie(monkeypatch, fake_llm, sample_review_request):
    """测试 tie 场景。"""
    from app.review import llm as llm_mod
    from app.review.nodes import arbitrator as arb_mod
    from app.review.nodes import dimension_agent as dim_mod
    from app.review.nodes import preprocess as pre_mod

    original_achat = fake_llm.achat_json

    async def tie_achat(*, system, user, **kwargs):
        if "仲裁" in system or "arbitrator" in system.lower():
            return {
                "final_winner": "tie",
                "overall_confidence": 0.6,
                "rationale": "tie",
                "adjusted_dimensions": [],
            }
        if "要点" in system or "抽取" in system:
            return await original_achat(system=system, user=user, **kwargs)
        return {
            "score_a": 3.5, "score_b": 3.5, "winner": "tie",
            "reason": "相当", "evidence": [], "confidence": 0.9,
        }

    fake_llm.achat_json = tie_achat

    for mod in (llm_mod, arb_mod, dim_mod, pre_mod):
        if hasattr(mod, "get_llm"):
            monkeypatch.setattr(mod, "get_llm", lambda: fake_llm, raising=False)

    monkeypatch.setattr(pre_mod, "_fetch_rag", lambda _ctx: {d.value: [] for d in DimensionKey}, raising=True)
    monkeypatch.setattr(pre_mod, "_run_skills", lambda _ctx: {}, raising=True)

    from app.review import graph as g
    from app.review import service as svc_mod
    g.get_graph.cache_clear()
    svc_mod.get_service.cache_clear()

    from app.review import get_service
    resp = await get_service().arun(sample_review_request)
    assert resp.report.final_winner == "tie"
    assert resp.vote_payload.dim_overall == "tie"
