"""离线批量的内部数据模型与枚举。"""
from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class StageStatus(str, Enum):
    """任务阶段。顺序：pending → created → generated → reviewed → voted → done。"""

    PENDING = "pending"
    CREATED = "created"
    GENERATED = "generated"
    REVIEWED = "reviewed"
    VOTED = "voted"
    DONE = "done"
    FAILED = "failed"


# 执行顺序（便于"从失败阶段继续"判断）
_STAGE_ORDER = [
    StageStatus.PENDING,
    StageStatus.CREATED,
    StageStatus.GENERATED,
    StageStatus.REVIEWED,
    StageStatus.VOTED,
    StageStatus.DONE,
]


def stage_rank(s: StageStatus) -> int:
    try:
        return _STAGE_ORDER.index(s)
    except ValueError:
        return -1  # FAILED


class BatchJob(BaseModel):
    """任务状态表一行（用于续跑/观测）。"""

    model_config = ConfigDict(extra="ignore")

    item_id: str
    battle_id: Optional[int] = None
    stage: StageStatus = StageStatus.PENDING
    retry_count: int = 0
    last_error: Optional[str] = None
    review_winner: Optional[str] = None  # A/B/tie
    vote_winner_side: Optional[str] = None  # left/right/tie
    latency_ms: int = 0
    updated_at: Optional[str] = None


__all__ = ["StageStatus", "BatchJob", "stage_rank"]
