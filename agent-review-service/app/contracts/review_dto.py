"""评审服务对外 HTTP 契约：/api/review 的请求/响应。"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from .review_models import ReviewReport

# 对战平台投票值（left/right/tie，与 Java @Pattern 对齐）
VoteSide = Literal["left", "right", "tie"]


class _ApiBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class ReviewRequest(_ApiBase):
    """POST /api/review 请求体。

    由离线批量系统调用：把 Java 平台 `GET /api/battle/{id}` 的相关字段整合后传入。
    注意：由于 Java 端只返回 response_left/right，调用方需确定内部 A/B 对应关系：
    - 简化策略：本服务把 response_left 视作 A，response_right 视作 B
      （因为对战创建时 displayOrder 固定为 normal，left==A、right==B 一一对应）
    - 评审得到的 winner(A/B) 经 VoteMapper 转换为 left/right 提交投票。
    """

    battle_id: int
    essay_title: str
    response_a: str = Field(description="批改A（通常等于 response_left）")
    response_b: str = Field(description="批改B（通常等于 response_right）")
    essay_content: Optional[str] = None
    grade_level: Optional[str] = "初中"
    requirements: Optional[str] = None
    essay_images: Optional[List[str]] = Field(default=None, description="base64 图片，可选辅助输入")
    metadata: Optional[dict] = None


class VotePayload(_ApiBase):
    """决策器产出的投票载荷（已映射为 left/right/tie 并附带理由）。

    字段顺序与 Java `VoteRequest` 严格对应，可直接 dump 成 `ArenaVoteRequest`。
    """

    dim_theme: VoteSide
    dim_theme_reason: str = ""
    dim_imagination: VoteSide
    dim_imagination_reason: str = ""
    dim_logic: VoteSide
    dim_logic_reason: str = ""
    dim_language: VoteSide
    dim_language_reason: str = ""
    dim_writing: VoteSide
    dim_writing_reason: str = ""
    dim_overall: VoteSide
    dim_overall_reason: str = ""
    vote_time: Optional[float] = None


class ReviewResponse(_ApiBase):
    """POST /api/review 响应体。"""

    report: ReviewReport
    vote_payload: VotePayload
    latency_ms: int = 0
    model_trace: dict = Field(
        default_factory=dict,
        description="各节点耗时/模型/token统计（可选，用于观测）",
    )
