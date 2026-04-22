"""LangGraph 工作流的共享 State。

采用 TypedDict + operator.add 归约：6 个维度 Agent 并行写入 `dimension_scores`，
LangGraph 会按 `Annotated[..., add]` 自动合并列表。
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict

from app.contracts.review_models import (
    ArbitrationResult,
    BattleContext,
    DimensionScore,
    ExtractedPoints,
    RagHit,
)


class GraphState(TypedDict, total=False):
    # ---- 输入 ----
    ctx: BattleContext

    # ---- 预处理产物 ----
    extracted_a: ExtractedPoints
    extracted_b: ExtractedPoints
    skill_summary: Dict[str, Any]  # feedback_compare / grammar / duplicate 汇总
    rag_hits: Dict[str, List[RagHit]]  # 按维度键（如 "theme"）组织

    # ---- 并行维度 Agent 的输出（由 fan-out 合并） ----
    dimension_scores: Annotated[List[DimensionScore], operator.add]

    # ---- 仲裁 ----
    arbitration: ArbitrationResult

    # ---- 运行时 ----
    errors: Annotated[List[str], operator.add]
    trace: Dict[str, Any]


__all__ = ["GraphState"]
