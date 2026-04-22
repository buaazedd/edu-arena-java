"""预处理节点：
1) 用 LLM 从 A/B 两份批改中抽取结构化要点（亮点/问题/建议/摘要）
2) 调用多个 Skill 得到客观指标（feedback_compare / coverage / hallucination / grammar）
3) 按 6 个维度触发 RAG 检索，结果塞到 state.rag_hits
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict

from app.common.logger import logger
from app.contracts.review_models import DimensionKey, ExtractedPoints
from app.rag import get_retriever
from app.skills import registry as skill_registry
from app.skills.coverage_analyzer import CoverageInput
from app.skills.duplicate_detect import DuplicateInput
from app.skills.feedback_compare import FeedbackCompareInput
from app.skills.grammar_check import GrammarCheckInput
from app.skills.hallucination_check import HallucinationCheckInput
from app.skills.text_stats import TextStatsInput

from ..llm import get_llm
from ..prompts import PREPROCESS_SYSTEM, preprocess_user
from ..state import GraphState


async def _extract_points(side: str, text: str) -> ExtractedPoints:
    llm = get_llm()
    try:
        data = await llm.achat_json(
            system=PREPROCESS_SYSTEM,
            user=preprocess_user(side, text),
            temperature=0.1,
        )
    except Exception as e:
        logger.warning(f"[preprocess] LLM 要点抽取失败 side={side}: {e}")
        # 退化：用空结构 + 字数估算
        return ExtractedPoints(side=side, word_count=len(text))  # type: ignore[arg-type]

    try:
        return ExtractedPoints(
            side=side,  # type: ignore[arg-type]
            highlights=list(data.get("highlights") or [])[:10],
            issues=list(data.get("issues") or [])[:10],
            suggestions=list(data.get("suggestions") or [])[:10],
            summary=str(data.get("summary") or "")[:240],
            word_count=int(data.get("word_count") or 0),
        )
    except Exception as e:
        logger.warning(f"[preprocess] 解析要点失败 side={side}: {e}")
        return ExtractedPoints(side=side, word_count=len(text))  # type: ignore[arg-type]


def _run_skills(ctx) -> Dict[str, Any]:
    """调用客观分析 Skill，返回紧凑摘要。"""
    reg = skill_registry
    summary: Dict[str, Any] = {}

    try:
        out = reg.get("feedback_compare").run(
            FeedbackCompareInput(response_a=ctx.response_a, response_b=ctx.response_b)
        )
        summary["feedback_compare"] = out.model_dump()
    except Exception as e:
        logger.warning(f"[preprocess] skill feedback_compare 失败: {e}")

    try:
        cov_a = reg.get("coverage_analyzer").run(CoverageInput(response=ctx.response_a)).model_dump()
        cov_b = reg.get("coverage_analyzer").run(CoverageInput(response=ctx.response_b)).model_dump()
        summary["coverage"] = {"a": cov_a, "b": cov_b}
    except Exception as e:
        logger.warning(f"[preprocess] skill coverage 失败: {e}")

    try:
        g_a = reg.get("grammar_check").run(GrammarCheckInput(text=ctx.response_a)).model_dump()
        g_b = reg.get("grammar_check").run(GrammarCheckInput(text=ctx.response_b)).model_dump()
        summary["grammar"] = {"a_score": g_a["score"], "b_score": g_b["score"]}
    except Exception as e:
        logger.warning(f"[preprocess] skill grammar 失败: {e}")

    try:
        d_a = reg.get("duplicate_detect").run(DuplicateInput(text=ctx.response_a)).model_dump()
        d_b = reg.get("duplicate_detect").run(DuplicateInput(text=ctx.response_b)).model_dump()
        summary["duplicate"] = {"a_ratio": d_a["ratio"], "b_ratio": d_b["ratio"]}
    except Exception as e:
        logger.warning(f"[preprocess] skill duplicate 失败: {e}")

    try:
        t_a = reg.get("text_stats").run(TextStatsInput(text=ctx.response_a)).model_dump()
        t_b = reg.get("text_stats").run(TextStatsInput(text=ctx.response_b)).model_dump()
        summary["text_stats"] = {"a": t_a, "b": t_b}
    except Exception as e:
        logger.warning(f"[preprocess] skill text_stats 失败: {e}")

    # 幻觉检测（若有原文才有意义）
    essay_text = ctx.essay_content or ""
    if essay_text.strip():
        try:
            h_a = reg.get("hallucination_check").run(
                HallucinationCheckInput(feedback=ctx.response_a, essay_text=essay_text)
            ).model_dump()
            h_b = reg.get("hallucination_check").run(
                HallucinationCheckInput(feedback=ctx.response_b, essay_text=essay_text)
            ).model_dump()
            summary["hallucination"] = {"a": h_a, "b": h_b}
        except Exception as e:
            logger.warning(f"[preprocess] skill hallucination 失败: {e}")

    return summary


def _fetch_rag(ctx) -> Dict[str, list]:
    retriever = get_retriever()
    hits: Dict[str, list] = {}
    query_base = f"{ctx.essay_title}\n{(ctx.essay_content or '')[:200]}"
    for dim in DimensionKey:
        try:
            hits[dim.value] = retriever.retrieve(dim, query_base, top_k=3)
        except Exception as e:
            logger.warning(f"[preprocess] RAG 检索 {dim} 失败: {e}")
            hits[dim.value] = []
    return hits


async def preprocess_node(state: GraphState) -> Dict[str, Any]:
    ctx = state["ctx"]
    logger.info(f"[preprocess] battle_id={ctx.battle_id} 启动")

    ext_a_t = asyncio.create_task(_extract_points("A", ctx.response_a))
    ext_b_t = asyncio.create_task(_extract_points("B", ctx.response_b))
    # Skill 和 RAG 是 CPU/本地，不用异步，但让出控制权给 LLM 抽取
    skill_summary = _run_skills(ctx)
    rag_hits = _fetch_rag(ctx)
    ext_a = await ext_a_t
    ext_b = await ext_b_t

    return {
        "extracted_a": ext_a,
        "extracted_b": ext_b,
        "skill_summary": skill_summary,
        "rag_hits": rag_hits,
        "trace": {**(state.get("trace") or {}), "preprocess": "done"},
    }
