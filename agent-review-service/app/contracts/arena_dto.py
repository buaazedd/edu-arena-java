"""对战平台 (edu-arena-java) REST API 对应的 Pydantic DTO。

严格对齐 Java 端 `JacksonConfig`：
- 全局 snake_case
- 忽略 null 字段（ResponseVO 中 Optional 字段序列化时省略）
- 日期格式 yyyy-MM-dd HH:mm:ss

与 Java DTO 逐字段对应表参见 contracts/__init__.py。
"""
from __future__ import annotations

from typing import Generic, List, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

# 投票维度的合法值（Java @Pattern 限制）
VoteValue = Literal["left", "right", "tie"]


class _ArenaBase(BaseModel):
    """所有 Arena DTO 的基类，统一 Pydantic 配置。"""

    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=False,
        validate_assignment=False,
    )


# -------------------- Auth --------------------


class ArenaLoginRequest(_ArenaBase):
    """POST /api/login 请求体。"""

    username: str
    password: str


class ArenaLoginVO(_ArenaBase):
    """POST /api/login 响应 data。"""

    token: str
    role: str  # "teacher" | "admin"
    user_id: int
    display_name: str


# -------------------- Battle --------------------


class ArenaCreateBattleRequest(_ArenaBase):
    """POST /api/battle/create 请求体。

    - essay_title: 必填
    - images: 纯 base64 字符串列表（不带 data:image 前缀），图片必传，<=10 张
    - essay_content / grade_level / requirements: 可选
    """

    essay_title: str
    images: List[str] = Field(default_factory=list)
    essay_content: Optional[str] = None
    grade_level: Optional[str] = "初中"
    requirements: Optional[str] = None


class ArenaModelSimpleVO(_ArenaBase):
    """BattleVO 中的模型简信息。"""

    name: str
    company: Optional[str] = None


class ArenaBattleVO(_ArenaBase):
    """GET /api/battle/{id} 响应 data。

    注意：
    - 后端不返回 response_a/b 与 model_a/b，只返回 left/right 视角字段
    - winner 的值为 left/right/tie 或 null（未投票）
    - model_left/right 仅在 status=voted 时返回，否则为 null
    """

    battle_id: int
    status: Literal["generating", "ready", "voted", "failed"]
    essay_title: str
    essay_content: Optional[str] = None
    grade_level: Optional[str] = None
    requirements: Optional[str] = None
    images: Optional[List[str]] = None

    winner: Optional[Literal["left", "right", "tie"]] = None
    response_left: Optional[str] = None
    response_right: Optional[str] = None
    model_left: Optional[ArenaModelSimpleVO] = None
    model_right: Optional[ArenaModelSimpleVO] = None


class ArenaVoteRequest(_ArenaBase):
    """POST /api/battle/{id}/vote 请求体。

    6 个维度均必填，值只能是 left/right/tie（Java @Pattern 强校验）。
    """

    dim_theme: VoteValue
    dim_imagination: VoteValue
    dim_logic: VoteValue
    dim_language: VoteValue
    dim_writing: VoteValue
    dim_overall: VoteValue
    dim_theme_reason: Optional[str] = None
    dim_imagination_reason: Optional[str] = None
    dim_logic_reason: Optional[str] = None
    dim_language_reason: Optional[str] = None
    dim_writing_reason: Optional[str] = None
    dim_overall_reason: Optional[str] = None
    vote_time: Optional[float] = None


class ArenaVoteResultVO(_ArenaBase):
    """POST /api/battle/{id}/vote 响应 data。"""

    message: str
    overall_winner: Literal["A", "B", "tie"]  # 槽位视角
    a_wins: int
    b_wins: int
    winner_side: Literal["left", "right", "tie"]  # 展示视角
    winner_label: str
    left_model_slot: Literal["A", "B"]
    right_model_slot: Literal["A", "B"]
    elo_a_before: float
    elo_a_after: float
    elo_b_before: float
    elo_b_after: float


# -------------------- Result 包装 --------------------

T = TypeVar("T")


class ArenaResult(_ArenaBase, Generic[T]):
    """Java 端统一包装 `Result<T>`。

    业务成功 code == 200；出错 code ∈ {400, 401, 500}。
    """

    code: int
    message: Optional[str] = None
    data: Optional[T] = None

    @property
    def is_success(self) -> bool:
        return self.code == 200
