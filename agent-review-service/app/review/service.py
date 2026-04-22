"""ReviewService 外观类：封装 LangGraph 工作流 + 决策器，对外暴露 `arun(ReviewRequest) -> ReviewResponse`。

职责：
1. 把 ReviewRequest 转换为内部 BattleContext
2. 构造初始 GraphState，调用编译好的 LangGraph
3. 从终态中抽取 dimension_scores / arbitration，组装 ReviewReport
4. 调 VoteMapper 生成 VotePayload
5. 汇总 latency_ms 与 trace 作为 ReviewResponse 返回
"""
from __future__ import annotations

import asyncio
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional

from app.common.exceptions import ReviewGraphError, ReviewServiceError
from app.common.logger import logger
from app.contracts.review_dto import ReviewRequest, ReviewResponse
from app.contracts.review_models import (
    ArbitrationResult,
    BattleContext,
    DimensionKey,
    DimensionScore,
    ReviewReport,
)

from .decision import VoteMapper
from .graph import get_graph
from .state import GraphState


def _to_battle_ctx(req: ReviewRequest) -> BattleContext:
    return BattleContext(
        battle_id=req.battle_id,
        essay_title=req.essay_title,
        essay_content=req.essay_content,
        grade_level=req.grade_level or "初中",
        requirements=req.requirements,
        response_a=req.response_a,
        response_b=req.response_b,
        essay_images=req.essay_images,
        metadata=req.metadata,
    )


def _merge_dimensions(
    raw: List[DimensionScore],
    arbitration: Optional[ArbitrationResult],
) -> List[DimensionScore]:
    """若仲裁者提供了 adjusted_dimensions，则覆盖同维度的原打分；按枚举顺序排序。"""
    by_dim: Dict[DimensionKey, DimensionScore] = {s.dim: s for s in raw}
    if arbitration and arbitration.adjusted_dimensions:
        for adj in arbitration.adjusted_dimensions:
            by_dim[adj.dim] = adj
    # 固定输出顺序：枚举定义顺序
    ordered: List[DimensionScore] = []
    for dim in DimensionKey:
        if dim in by_dim:
            ordered.append(by_dim[dim])
    return ordered


def _build_report(
    battle_id: int,
    final_state: Dict[str, Any],
) -> ReviewReport:
    scores: List[DimensionScore] = list(final_state.get("dimension_scores") or [])
    arbitration: Optional[ArbitrationResult] = final_state.get("arbitration")
    dimensions = _merge_dimensions(scores, arbitration)

    if len(dimensions) < 6:
        # 给出详细错误信息便于排查；这里不抛异常，允许部分缺失但降级为 tie
        missing = [k.value for k in DimensionKey if k not in {d.dim for d in dimensions}]
        logger.warning(f"[service] 评审维度缺失: {missing}（将以 tie 兜底由 VoteMapper 处理）")

    # final_winner：优先取仲裁结论，其次取 OVERALL，最后 tie
    final_winner = "tie"
    overall_conf = 0.5
    if arbitration:
        final_winner = arbitration.final_winner
        overall_conf = arbitration.overall_confidence
    else:
        for d in dimensions:
            if d.dim == DimensionKey.OVERALL:
                final_winner = d.winner
                overall_conf = d.confidence
                break

    errors: List[str] = list(final_state.get("errors") or [])

    return ReviewReport(
        battle_id=battle_id,
        dimensions=dimensions,
        final_winner=final_winner,  # type: ignore[arg-type]
        overall_confidence=overall_conf,
        review_version="v1",
        errors=errors,
    )


class ReviewService:
    """评审服务外观。"""

    def __init__(self) -> None:
        self._graph = get_graph()
        self._vote_mapper = VoteMapper()

    async def arun(self, req: ReviewRequest) -> ReviewResponse:
        """执行一次评审工作流并返回 HTTP 响应体。"""
        t0 = time.perf_counter()
        battle_id = req.battle_id
        logger.info(
            f"[service] 开始评审 battle_id={battle_id} title={req.essay_title!r} "
            f"len_a={len(req.response_a)} len_b={len(req.response_b)}"
        )

        ctx = _to_battle_ctx(req)
        initial: GraphState = {"ctx": ctx, "errors": [], "trace": {}}  # type: ignore[typeddict-item]

        try:
            final_state: Dict[str, Any] = await self._graph.ainvoke(initial)  # type: ignore[assignment]
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"[service] LangGraph 执行失败 battle_id={battle_id}")
            raise ReviewGraphError(f"评审工作流执行失败: {e}") from e

        try:
            report = _build_report(battle_id, final_state)
            vote_payload = self._vote_mapper.to_vote_payload(report)
        except Exception as e:
            logger.exception(f"[service] 组装报告/投票失败 battle_id={battle_id}")
            raise ReviewServiceError(f"组装评审报告失败: {e}") from e

        latency_ms = int((time.perf_counter() - t0) * 1000)
        trace = final_state.get("trace") or {}
        trace["latency_ms"] = latency_ms

        logger.info(
            f"[service] 评审完成 battle_id={battle_id} winner={report.final_winner} "
            f"conf={report.overall_confidence} cost={latency_ms}ms"
        )

        return ReviewResponse(
            report=report,
            vote_payload=vote_payload,
            latency_ms=latency_ms,
            model_trace=trace,
        )


@lru_cache(maxsize=1)
def get_service() -> ReviewService:
    """进程内单例 ReviewService。"""
    return ReviewService()


__all__ = ["ReviewService", "get_service"]
