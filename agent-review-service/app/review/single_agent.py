"""单 Agent 评审链路（固定 5 步 CoT，1 次 LLM 调用产出 6 维 + final_winner）。

使用 DeepSeek（OpenAI 兼容协议）。与旧多 agent / LangGraph 链路并存，
由 ReviewService 根据 settings.review_mode 选择是否启用。

设计原则：
- 单次 LLM 调用，最大化降低被风控概率与成本；
- 不引入 skills、不引入 RAG、不传作文图片；
- 输出严格 JSON，由本模块负责解析与校验，转为现有领域模型
  (List[DimensionScore], ArbitrationResult)，对外契约零变更。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from app.common.exceptions import LLMInvokeError, ReviewServiceError
from app.common.logger import logger
from app.contracts.review_models import (
    ArbitrationResult,
    BattleContext,
    DimensionKey,
    DimensionScore,
)
from app.settings import get_settings

from .llm import LLMClient
from .prompts import SINGLE_AGENT_SYSTEM, single_agent_user


# 维度顺序与 review_models.DimensionKey 一致；single agent 必须输出全部 6 项。
_DIM_ORDER: List[DimensionKey] = [
    DimensionKey.THEME,
    DimensionKey.IMAGINATION,
    DimensionKey.LOGIC,
    DimensionKey.LANGUAGE,
    DimensionKey.WRITING,
    DimensionKey.OVERALL,
]
_DIM_KEY_SET = {d.value for d in _DIM_ORDER}

_TIE_DELTA = 0.5  # 与 prompt 中阈值保持一致


_SINGLE_LLM: Optional[LLMClient] = None


def _get_single_llm() -> LLMClient:
    """single 模式专用的 LLMClient（连接 DeepSeek）。与旧 LLM 实例隔离。"""
    global _SINGLE_LLM
    if _SINGLE_LLM is None:
        s = get_settings()
        _SINGLE_LLM = LLMClient(
            api_key=s.ai_api_key_single,
            base_url=s.ai_base_url_single,
            default_model=s.ai_review_model_single,
        )
    return _SINGLE_LLM


def _clip(v: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f < lo:
        return lo
    if f > hi:
        return hi
    return f


def _normalize_winner(w: Any) -> str:
    if isinstance(w, str):
        ws = w.strip()
        if ws in ("A", "B", "tie"):
            return ws
        # 容错小写
        if ws.lower() == "a":
            return "A"
        if ws.lower() == "b":
            return "B"
    return "tie"


def _enforce_tie(score_a: float, score_b: float, winner: str) -> str:
    if abs(score_a - score_b) <= _TIE_DELTA:
        return "tie"
    # 若 winner 与分差方向不一致，按分差方向修正
    if score_a > score_b and winner != "A":
        return "A"
    if score_b > score_a and winner != "B":
        return "B"
    return winner


def _parse_dimension(item: Dict[str, Any]) -> Optional[DimensionScore]:
    dim_raw = item.get("dim")
    if dim_raw not in _DIM_KEY_SET:
        return None
    score_a = _clip(item.get("score_a"), 0.0, 5.0, 0.0)
    score_b = _clip(item.get("score_b"), 0.0, 5.0, 0.0)
    winner = _normalize_winner(item.get("winner"))
    winner = _enforce_tie(score_a, score_b, winner)
    reason = str(item.get("reason") or "").strip()
    if len(reason) > 500:
        reason = reason[:500]
    raw_evidence = item.get("evidence") or []
    evidence: List[str] = []
    if isinstance(raw_evidence, list):
        for ev in raw_evidence[:3]:
            if isinstance(ev, str) and ev.strip():
                evidence.append(ev.strip())
    confidence = _clip(item.get("confidence"), 0.0, 1.0, 0.5)
    return DimensionScore(
        dim=DimensionKey(dim_raw),
        score_a=score_a,
        score_b=score_b,
        winner=winner,  # type: ignore[arg-type]
        reason=reason,
        evidence=evidence,
        confidence=confidence,
    )


def _parse_response(payload: Dict[str, Any]) -> Tuple[List[DimensionScore], ArbitrationResult]:
    """把 single agent 的 JSON 输出解析为 (dimensions, arbitration)。"""
    dims_raw = payload.get("dimensions") or []
    if not isinstance(dims_raw, list):
        raise ReviewServiceError("single agent 返回 dimensions 不是数组")

    by_dim: Dict[DimensionKey, DimensionScore] = {}
    for item in dims_raw:
        if not isinstance(item, dict):
            continue
        ds = _parse_dimension(item)
        if ds is not None:
            by_dim[ds.dim] = ds

    # 缺失维度兜底：以 0 分 tie 占位（VoteMapper 可处理）
    dimensions: List[DimensionScore] = []
    missing: List[str] = []
    for k in _DIM_ORDER:
        if k in by_dim:
            dimensions.append(by_dim[k])
        else:
            missing.append(k.value)
            dimensions.append(
                DimensionScore(
                    dim=k,
                    score_a=0.0,
                    score_b=0.0,
                    winner="tie",
                    reason="single agent 未返回该维度，自动补 tie。",
                    evidence=[],
                    confidence=0.0,
                )
            )
    if missing:
        logger.warning(f"[single_agent] 缺失维度: {missing}，已用 tie 兜底")

    overall = by_dim.get(DimensionKey.OVERALL)

    # final_winner 严格以 overall 维度为准（即使模型返回了不一致的 final_winner 也以 overall 为权威）
    if overall is not None:
        final_winner = overall.winner
        overall_conf = overall.confidence
    else:
        # overall 缺失时再退而求其次取模型给的 final_winner
        final_winner = _normalize_winner(payload.get("final_winner"))
        overall_conf = _clip(payload.get("overall_confidence"), 0.0, 1.0, 0.5)

    rationale = str(payload.get("rationale") or "").strip()
    if len(rationale) > 500:
        rationale = rationale[:500]

    arbitration = ArbitrationResult(
        final_winner=final_winner,  # type: ignore[arg-type]
        overall_confidence=overall_conf,
        rationale=rationale,
        adjusted_dimensions=[],  # single 模式无需 adjust
    )
    return dimensions, arbitration


async def run_single_review(
    ctx: BattleContext,
) -> Tuple[List[DimensionScore], ArbitrationResult, Dict[str, Any]]:
    """执行一次单 agent 评审。

    Returns:
        dimensions: 6 个维度评分，按 DimensionKey 顺序排列；
        arbitration: 仲裁结果（final_winner / overall_confidence / rationale）；
        trace: 模型调用元信息，供上层 ReviewResponse.model_trace 展示。
    """
    settings = get_settings()
    if not settings.ai_api_key_single:
        raise ReviewServiceError(
            "REVIEW_MODE=single 但 AI_API_KEY_SINGLE 未配置，请在 .env 中填写 DeepSeek API Key。"
        )

    llm = _get_single_llm()

    system = SINGLE_AGENT_SYSTEM
    user = single_agent_user(
        essay_title=ctx.essay_title,
        grade_level=ctx.grade_level or "初中",
        requirements=ctx.requirements,
        response_a=ctx.response_a,
        response_b=ctx.response_b,
    )

    logger.info(
        f"[single_agent] battle_id={ctx.battle_id} 调用 DeepSeek "
        f"model={settings.ai_review_model_single} base={settings.ai_base_url_single}"
    )

    try:
        payload = await llm.achat_json(
            system=system,
            user=user,
            model=settings.ai_review_model_single,
            temperature=0.2,
        )
    except LLMInvokeError:
        raise
    except Exception as e:
        raise ReviewServiceError(f"single agent LLM 调用失败: {e}") from e

    dimensions, arbitration = _parse_response(payload)

    trace: Dict[str, Any] = {
        "mode": "single",
        "model": settings.ai_review_model_single,
        "base_url": settings.ai_base_url_single,
        "llm_calls": 1,
        "raw_final_winner": payload.get("final_winner"),
    }
    return dimensions, arbitration, trace


__all__ = ["run_single_review"]
