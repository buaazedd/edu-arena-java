"""决策器：把 ReviewReport 映射为对战平台的投票载荷 VotePayload。

业务规则（与 Java VoteController 的 @Pattern 约束对齐）：
1. 投票值只能是 left/right/tie，因此需要把内部 A/B 映射为 left/right：
   - 简化策略：创建对战时 `displayOrder` 固定为 "normal"，即 left==A, right==B。
   - 因此内部 "A" -> "left"，"B" -> "right"，"tie" -> "tie"。
2. OVERALL 维度的 winner 直接决定整体 winner（用户明确需求）。
3. 其余 5 维按 |score_a - score_b| 与阈值比较，小于阈值强制判 tie（即便 Agent 给出了 A/B，也视为信心不足）。
4. 理由字段 <= 500 字，超长截断并追加 "…"。

该模块是纯函数风格，便于单元测试。
"""
from __future__ import annotations

from typing import Dict, Literal

from app.common.logger import logger
from app.contracts.review_dto import VotePayload
from app.contracts.review_models import DimensionKey, DimensionScore, ReviewReport
from app.settings import get_settings

# 内部 A/B -> 对战平台 left/right 的映射表
_AB_TO_SIDE: Dict[str, Literal["left", "right", "tie"]] = {
    "A": "left",
    "B": "right",
    "tie": "tie",
}

# 维度键 -> VotePayload 字段前缀
_DIM_TO_FIELD: Dict[DimensionKey, str] = {
    DimensionKey.THEME: "dim_theme",
    DimensionKey.IMAGINATION: "dim_imagination",
    DimensionKey.LOGIC: "dim_logic",
    DimensionKey.LANGUAGE: "dim_language",
    DimensionKey.WRITING: "dim_writing",
    DimensionKey.OVERALL: "dim_overall",
}

_REASON_MAX = 500


def _truncate(text: str, limit: int = _REASON_MAX) -> str:
    if not text:
        return ""
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _map_side(ab: str) -> Literal["left", "right", "tie"]:
    """把内部 A/B/tie 转为 left/right/tie；未知值兜底 tie。"""
    side = _AB_TO_SIDE.get(ab)
    if side is None:
        logger.warning(f"[decision] 未知 winner 值 {ab!r}，回退为 tie")
        return "tie"
    return side


def _resolve_dim(
    dim: DimensionKey,
    score: DimensionScore,
    tie_threshold: float,
) -> Literal["left", "right", "tie"]:
    """按维度规则决定投票值。

    - OVERALL：以 Agent 输出 winner 为准（不走分差阈值，因为它是综合判断）。
    - 其余：若分差 < 阈值，强制 tie；否则采用 Agent 输出的 winner。
    """
    if dim == DimensionKey.OVERALL:
        return _map_side(score.winner)

    diff = abs(score.score_a - score.score_b)
    if diff < tie_threshold:
        if score.winner != "tie":
            logger.debug(
                f"[decision/{dim.value}] winner={score.winner} 但分差 {diff:.2f}"
                f" < 阈值 {tie_threshold}，强制判 tie"
            )
        return "tie"
    return _map_side(score.winner)


class VoteMapper:
    """将 ReviewReport 映射为 VotePayload。"""

    def __init__(self, tie_threshold: float | None = None) -> None:
        settings = get_settings()
        self.tie_threshold = (
            tie_threshold if tie_threshold is not None else settings.dim_score_tie_threshold
        )

    def to_vote_payload(self, report: ReviewReport) -> VotePayload:
        """核心映射函数。

        前置校验：report.dimensions 必须覆盖 6 个维度键，否则缺失维度以 tie/空理由兜底。
        """
        dim_map: Dict[DimensionKey, DimensionScore] = {d.dim: d for d in report.dimensions}

        payload_kwargs: Dict[str, object] = {}
        for dim, field_prefix in _DIM_TO_FIELD.items():
            score = dim_map.get(dim)
            if score is None:
                logger.warning(
                    f"[decision] 维度 {dim.value} 缺失，以 tie + 空理由兜底"
                )
                payload_kwargs[field_prefix] = "tie"
                payload_kwargs[f"{field_prefix}_reason"] = ""
                continue

            vote_side = _resolve_dim(dim, score, self.tie_threshold)
            payload_kwargs[field_prefix] = vote_side
            payload_kwargs[f"{field_prefix}_reason"] = _truncate(score.reason)

        # 一致性保护：OVERALL 必须等于 report.final_winner（内部 A/B）
        overall_score = dim_map.get(DimensionKey.OVERALL)
        if overall_score and overall_score.winner != report.final_winner:
            logger.warning(
                f"[decision] report.final_winner={report.final_winner} 与 OVERALL.winner"
                f"={overall_score.winner} 不一致，以 OVERALL.winner 为准"
            )
            payload_kwargs["dim_overall"] = _map_side(overall_score.winner)

        return VotePayload(**payload_kwargs)  # type: ignore[arg-type]


__all__ = ["VoteMapper"]
