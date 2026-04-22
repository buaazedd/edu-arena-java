"""单维度评审 Agent（参数化：通过 state['current_dim'] 指明要评的维度）。

由 dispatch 节点通过 LangGraph Send API 并行 fan-out 到 6 个维度。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from app.common.logger import logger
from app.contracts.review_models import DIMENSION_LABELS, DimensionKey, DimensionScore, RagHit

from ..llm import get_llm
from ..prompts import DIM_AGENT_USER_TEMPLATE, dim_system_prompt


def _format_rag(hits: List[RagHit], limit: int = 3) -> str:
    if not hits:
        return "（无可用检索结果）"
    lines = []
    for i, h in enumerate(hits[:limit], 1):
        lines.append(f"[{i}][{h.source}|s={h.score:.2f}] {h.content[:280]}")
    return "\n".join(lines)


def _compact_skill_for_dim(dim: DimensionKey, skill_summary: Dict[str, Any]) -> str:
    """按维度从 skill_summary 中挑选相关子指标，避免 prompt 过长。"""
    snapshot: Dict[str, Any] = {}
    fc = skill_summary.get("feedback_compare") or {}
    if fc:
        snapshot["feedback_compare.verdict"] = fc.get("verdict")
        snapshot["feedback_compare.a_length"] = (fc.get("a") or {}).get("length")
        snapshot["feedback_compare.b_length"] = (fc.get("b") or {}).get("length")

    cov = skill_summary.get("coverage") or {}
    if cov:
        a_cov = (cov.get("a") or {}).get("coverage") or {}
        b_cov = (cov.get("b") or {}).get("coverage") or {}
        snapshot[f"coverage.{dim.value}"] = {"a": a_cov.get(dim.value), "b": b_cov.get(dim.value)}

    if dim == DimensionKey.LANGUAGE:
        g = skill_summary.get("grammar")
        if g:
            snapshot["grammar"] = g
        d = skill_summary.get("duplicate")
        if d:
            snapshot["duplicate"] = d

    if dim in (DimensionKey.OVERALL, DimensionKey.THEME):
        h = skill_summary.get("hallucination")
        if h:
            snapshot["hallucination.a_rate"] = (h.get("a") or {}).get("hallucination_rate")
            snapshot["hallucination.b_rate"] = (h.get("b") or {}).get("hallucination_rate")

    t = skill_summary.get("text_stats")
    if t:
        snapshot["text_stats"] = {
            "a_chars": (t.get("a") or {}).get("char_count"),
            "b_chars": (t.get("b") or {}).get("char_count"),
        }
    return json.dumps(snapshot, ensure_ascii=False)


def _fallback_score(ctx, dim: DimensionKey, err: str) -> DimensionScore:
    """LLM 失败时的降级评分：保守判 tie。"""
    return DimensionScore(
        dim=dim,
        score_a=3.0,
        score_b=3.0,
        winner="tie",
        reason=f"LLM 评审失败，降级为 tie。原因：{err[:200]}",
        evidence=[],
        confidence=0.2,
    )


async def dimension_agent_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    """单维度评审 Agent。

    payload 由 dispatch 生成，包含 ctx / current_dim / skill_summary / rag_hits 的切片。
    返回 {"dimension_scores": [score]}（让 Annotated[operator.add] 自动合并）。
    """
    ctx = payload["ctx"]
    dim: DimensionKey = payload["current_dim"]
    skill_summary: Dict[str, Any] = payload.get("skill_summary") or {}
    rag_hits: List[RagHit] = payload.get("rag_hits_for_dim") or []

    llm = get_llm()
    system = dim_system_prompt(dim)
    user = DIM_AGENT_USER_TEMPLATE.format(
        essay_title=ctx.essay_title,
        grade_level=ctx.grade_level or "初中",
        requirements=ctx.requirements or "（无特殊要求）",
        rag_context=_format_rag(rag_hits),
        response_a=ctx.response_a[:4000],
        response_b=ctx.response_b[:4000],
        skill_summary=_compact_skill_for_dim(dim, skill_summary),
    )

    try:
        data = await llm.achat_json(system=system, user=user, temperature=0.15)
        score = DimensionScore(
            dim=dim,
            score_a=float(data.get("score_a", 3.0)),
            score_b=float(data.get("score_b", 3.0)),
            winner=str(data.get("winner", "tie")),  # type: ignore[arg-type]
            reason=str(data.get("reason", ""))[:500],
            evidence=[str(x)[:200] for x in (data.get("evidence") or [])][:3],
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception as e:
        logger.warning(f"[dim_agent/{dim.value}] 失败: {e}")
        score = _fallback_score(ctx, dim, str(e))

    logger.info(
        f"[dim_agent/{dim.value}] a={score.score_a} b={score.score_b} "
        f"winner={score.winner} conf={score.confidence}"
    )
    return {"dimension_scores": [score]}
