"""把六维度并行分派到 dimension_agent 节点。"""
from __future__ import annotations

from typing import List

from langgraph.types import Send

from app.contracts.review_models import DimensionKey

from ..state import GraphState


def dispatch_dimensions(state: GraphState) -> List[Send]:
    """条件边函数：根据 state 产出 6 个 Send 对象，并行调用 dimension_agent。"""
    ctx = state["ctx"]
    skill_summary = state.get("skill_summary") or {}
    rag_hits = state.get("rag_hits") or {}

    sends: List[Send] = []
    for dim in DimensionKey:
        sends.append(
            Send(
                "dimension_agent",
                {
                    "ctx": ctx,
                    "current_dim": dim,
                    "skill_summary": skill_summary,
                    "rag_hits_for_dim": rag_hits.get(dim.value, []),
                },
            )
        )
    return sends
