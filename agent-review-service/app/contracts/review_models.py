"""评审内部领域模型：维度定义、打分结构、评审报告。"""
from __future__ import annotations

from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class DimensionKey(str, Enum):
    """六维度键（与 Java VoteRequest 字段对齐）。"""

    THEME = "theme"            # 主旨   dim_theme
    IMAGINATION = "imagination"  # 想象  dim_imagination
    LOGIC = "logic"            # 逻辑   dim_logic
    LANGUAGE = "language"      # 语言   dim_language
    WRITING = "writing"        # 书写   dim_writing
    OVERALL = "overall"        # 整体评价（决定最终胜负） dim_overall


# 中文维度描述（供 Prompt 与返回体展示）
DIMENSION_LABELS: dict[DimensionKey, str] = {
    DimensionKey.THEME: "主旨：是否紧扣题意、中心明确",
    DimensionKey.IMAGINATION: "想象：创意与想象力",
    DimensionKey.LOGIC: "逻辑：结构与逻辑性",
    DimensionKey.LANGUAGE: "语言：语言表达能力",
    DimensionKey.WRITING: "书写：书写规范性",
    DimensionKey.OVERALL: "整体评价：综合来看哪个批改更好",
}


class _InternalBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class BattleContext(_InternalBase):
    """评审工作流的输入上下文。"""

    battle_id: int
    essay_title: str
    essay_content: Optional[str] = None
    grade_level: Optional[str] = "初中"
    requirements: Optional[str] = None
    # 两份 AI 批改（由 Java 平台 generate 接口产出，这里以 A/B 内部视角）
    response_a: str
    response_b: str
    # 可选：原作文图片（base64），用于辅助评审
    essay_images: Optional[List[str]] = None
    metadata: Optional[dict] = None


class ExtractedPoints(_InternalBase):
    """从单份批改内容中抽取的结构化要点（预处理节点输出）。"""

    side: Literal["A", "B"]
    highlights: List[str] = Field(default_factory=list, description="亮点")
    issues: List[str] = Field(default_factory=list, description="问题/不足")
    suggestions: List[str] = Field(default_factory=list, description="建议")
    summary: str = ""
    word_count: int = 0


class RagHit(_InternalBase):
    """RAG 检索命中结果。"""

    source: Literal["rubric", "exemplar", "gold_case"]
    content: str
    score: float = 0.0
    metadata: dict = Field(default_factory=dict)


class DimensionScore(_InternalBase):
    """单一维度的评审结果（维度 Agent 的输出）。"""

    dim: DimensionKey
    score_a: float = Field(ge=0, le=5)
    score_b: float = Field(ge=0, le=5)
    winner: Literal["A", "B", "tie"]  # 内部 A/B 视角；最终映射到 left/right 在决策器层完成
    reason: str = Field(description="合并理由，<=500 字")
    evidence: List[str] = Field(default_factory=list, description="引用的批改片段")
    confidence: float = Field(ge=0, le=1, default=0.5)


class ArbitrationResult(_InternalBase):
    """仲裁 Agent 的输出。"""

    final_winner: Literal["A", "B", "tie"]
    overall_confidence: float = Field(ge=0, le=1)
    rationale: str = ""
    adjusted_dimensions: List[DimensionScore] = Field(
        default_factory=list,
        description="若仲裁者修正了个别维度，此处给出最终版维度列表（覆盖式）",
    )


class ReviewReport(_InternalBase):
    """评审最终报告（由工作流汇总产出）。"""

    battle_id: int
    dimensions: List[DimensionScore]  # 必须含 6 个维度
    final_winner: Literal["A", "B", "tie"]
    overall_confidence: float = Field(ge=0, le=1)
    review_version: str = "v1"
    errors: List[str] = Field(default_factory=list)
