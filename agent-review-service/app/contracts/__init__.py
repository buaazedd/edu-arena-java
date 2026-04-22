"""contracts: 两系统共享的 Pydantic 契约层。

按接口对齐 Java 端 edu-arena-java:
- arena_dto.py       : 对战平台 REST API DTO（snake_case 严格对齐 Java JacksonConfig）
- review_dto.py      : 评审服务对外 HTTP 契约
- review_models.py   : 评审内部领域模型
- dataset_dto.py     : 离线清单条目模型

设计要点：
1. 所有 JSON 字段统一 snake_case。
2. Pydantic v2 `model_config = ConfigDict(populate_by_name=True)` 允许按字段名或 alias 构造。
3. 凡与 Java 端对应的字段，使用字段名直接等于 snake_case（而非 camelCase + alias）
   以降低心智成本；仅在必要时使用 alias。
"""

from .arena_dto import (
    ArenaBattleVO,
    ArenaCreateBattleRequest,
    ArenaLoginRequest,
    ArenaLoginVO,
    ArenaModelSimpleVO,
    ArenaResult,
    ArenaVoteRequest,
    ArenaVoteResultVO,
    VoteValue,
)
from .dataset_dto import DatasetItem, ImageSource
from .review_dto import ReviewRequest, ReviewResponse, VotePayload
from .review_models import (
    BattleContext,
    DimensionKey,
    DimensionScore,
    ExtractedPoints,
    RagHit,
    ReviewReport,
)

__all__ = [
    # arena
    "ArenaLoginRequest",
    "ArenaLoginVO",
    "ArenaCreateBattleRequest",
    "ArenaBattleVO",
    "ArenaVoteRequest",
    "ArenaVoteResultVO",
    "ArenaModelSimpleVO",
    "ArenaResult",
    "VoteValue",
    # review external
    "ReviewRequest",
    "ReviewResponse",
    "VotePayload",
    # review internal
    "DimensionKey",
    "DimensionScore",
    "ReviewReport",
    "BattleContext",
    "ExtractedPoints",
    "RagHit",
    # dataset
    "DatasetItem",
    "ImageSource",
]
