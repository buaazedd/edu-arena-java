"""ReviewService 外观类：封装评审链路与决策器，对外暴露 `arun(ReviewRequest) -> ReviewResponse`。

支持两种评审模式（由 settings.review_mode 控制）：
- single：DeepSeek 单 agent + 固定 5 步 CoT，**1 次 LLM 调用**，默认模式
- multi：旧 LangGraph 多 agent 工作流，9~10 次 LLM 调用，作为 fallback 保留

职责：
1. 把 ReviewRequest 转换为内部 BattleContext
2. 按 review_mode 选择 single / multi 链路得到 dimensions + arbitration
3. 复用 VoteMapper 生成 VotePayload
4. 汇总 latency_ms 与 trace 作为 ReviewResponse 返回
"""
from __future__ import annotations

import asyncio
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

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
from app.settings import get_settings

from .decision import VoteMapper
from .single_agent import run_single_review
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


def _build_report_from_parts(
    battle_id: int,
    dimensions_in: List[DimensionScore],
    arbitration: Optional[ArbitrationResult],
    errors: Optional[List[str]] = None,
) -> ReviewReport:
    dimensions = _merge_dimensions(dimensions_in, arbitration)

    if len(dimensions) < 6:
        missing = [k.value for k in DimensionKey if k not in {d.dim for d in dimensions}]
        logger.warning(f"[service] 评审维度缺失: {missing}（将以 tie 兜底由 VoteMapper 处理）")

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

    return ReviewReport(
        battle_id=battle_id,
        dimensions=dimensions,
        final_winner=final_winner,  # type: ignore[arg-type]
        overall_confidence=overall_conf,
        review_version="v1",
        errors=list(errors or []),
    )


def _build_report_from_state(battle_id: int, final_state: Dict[str, Any]) -> ReviewReport:
    """从旧 LangGraph 终态中抽取。"""
    scores: List[DimensionScore] = list(final_state.get("dimension_scores") or [])
    arbitration: Optional[ArbitrationResult] = final_state.get("arbitration")
    errors: List[str] = list(final_state.get("errors") or [])
    return _build_report_from_parts(battle_id, scores, arbitration, errors)


class ReviewService:
    """评审服务外观。"""

    def __init__(self) -> None:
        self._mode = (get_settings().review_mode or "single").lower()
        if self._mode not in ("single", "multi"):
            logger.warning(f"[service] 未知 REVIEW_MODE={self._mode!r}，回退为 single")
            self._mode = "single"
        # multi 模式才加载 LangGraph，避免 single 模式下不必要的依赖与启动开销
        self._graph = None
        if self._mode == "multi":
            from .graph import get_graph  # 延迟导入

            self._graph = get_graph()
        self._vote_mapper = VoteMapper()
        logger.info(f"[service] ReviewService 初始化完成 mode={self._mode}")

    async def arun(self, req: ReviewRequest) -> ReviewResponse:
        """执行一次评审并返回 HTTP 响应体。"""
        t0 = time.perf_counter()
        battle_id = req.battle_id
        logger.info(
            f"[service] 开始评审 battle_id={battle_id} mode={self._mode} "
            f"title={req.essay_title!r} len_a={len(req.response_a)} len_b={len(req.response_b)}"
        )

        ctx = _to_battle_ctx(req)

        try:
            if self._mode == "single":
                report, trace = await self._run_single(ctx)
            else:
                report, trace = await self._run_multi(ctx)
        except asyncio.CancelledError:
            raise
        except ReviewServiceError:
            raise
        except Exception as e:
            logger.exception(f"[service] 评审执行失败 battle_id={battle_id}")
            raise ReviewGraphError(f"评审执行失败: {e}") from e

        try:
            vote_payload = self._vote_mapper.to_vote_payload(report)
        except Exception as e:
            logger.exception(f"[service] 组装投票失败 battle_id={battle_id}")
            raise ReviewServiceError(f"组装评审报告失败: {e}") from e

        latency_ms = int((time.perf_counter() - t0) * 1000)
        trace["latency_ms"] = latency_ms

        logger.info(
            f"[service] 评审完成 battle_id={battle_id} mode={self._mode} "
            f"winner={report.final_winner} conf={report.overall_confidence} cost={latency_ms}ms"
        )

        return ReviewResponse(
            report=report,
            vote_payload=vote_payload,
            latency_ms=latency_ms,
            model_trace=trace,
        )

    # --------- 链路实现 ---------

    async def _run_single(self, ctx: BattleContext) -> Tuple[ReviewReport, Dict[str, Any]]:
        dimensions, arbitration, trace = await run_single_review(ctx)
        report = _build_report_from_parts(ctx.battle_id, dimensions, arbitration)
        return report, trace

    async def _run_multi(self, ctx: BattleContext) -> Tuple[ReviewReport, Dict[str, Any]]:
        assert self._graph is not None, "multi 模式 graph 未初始化"
        initial: GraphState = {"ctx": ctx, "errors": [], "trace": {}}  # type: ignore[typeddict-item]
        final_state: Dict[str, Any] = await self._graph.ainvoke(initial)  # type: ignore[assignment]
        report = _build_report_from_state(ctx.battle_id, final_state)
        trace: Dict[str, Any] = dict(final_state.get("trace") or {})
        trace.setdefault("mode", "multi")
        return report, trace


@lru_cache(maxsize=1)
def get_service() -> ReviewService:
    """进程内单例 ReviewService。"""
    return ReviewService()


__all__ = ["ReviewService", "get_service"]

