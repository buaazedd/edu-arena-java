"""LangGraph 工作流装配。

拓扑:
    START
      │
      ▼
   preprocess     ← LLM 要点抽取 + Skill 指标 + RAG 检索
      │
      ▼  (conditional edge: dispatch_dimensions 返回 6×Send)
      ├── dimension_agent(theme)       ┐
      ├── dimension_agent(imagination) │
      ├── dimension_agent(logic)       │  并行执行，
      ├── dimension_agent(language)    │  结果经 Annotated[List,add] 合并
      ├── dimension_agent(writing)     │
      └── dimension_agent(overall)     ┘
                 │
                 ▼
           arbitrator  ← 综合 6 维，强约束 final == OVERALL.winner
                 │
                 ▼
                END
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.common.logger import logger

from .nodes.arbitrator import arbitrator_node
from .nodes.dimension_agent import dimension_agent_node
from .nodes.dispatch import dispatch_dimensions
from .nodes.preprocess import preprocess_node
from .state import GraphState


def build_graph() -> Any:
    """构造并编译 LangGraph 工作流。

    返回已编译的 graph 对象，可 `await graph.ainvoke(initial_state)` 执行。
    """
    g = StateGraph(GraphState)

    # 注册节点
    g.add_node("preprocess", preprocess_node)
    g.add_node("dimension_agent", dimension_agent_node)
    g.add_node("arbitrator", arbitrator_node)

    # 拓扑边
    g.add_edge(START, "preprocess")
    # 条件边：preprocess 完成后 fan-out 到 6 个 dimension_agent
    g.add_conditional_edges(
        "preprocess",
        dispatch_dimensions,
        # path_map 可省略；显式列出目标节点利于 IDE 跳转
        ["dimension_agent"],
    )
    # 6 个 dimension_agent 产出后 fan-in 到 arbitrator
    g.add_edge("dimension_agent", "arbitrator")
    g.add_edge("arbitrator", END)

    compiled = g.compile()
    logger.info("[graph] LangGraph 评审工作流编译完成")
    return compiled


@lru_cache(maxsize=1)
def get_graph() -> Any:
    """进程内单例 graph（编译结果线程安全可复用）。"""
    return build_graph()


__all__ = ["build_graph", "get_graph"]
