"""决策器 VoteMapper 测试。"""
from __future__ import annotations

from app.contracts.review_models import DimensionKey, DimensionScore, ReviewReport
from app.review.decision import VoteMapper


def _score(dim: DimensionKey, a: float, b: float, winner: str, reason: str = "ok") -> DimensionScore:
    return DimensionScore(
        dim=dim, score_a=a, score_b=b, winner=winner, reason=reason, confidence=0.8  # type: ignore[arg-type]
    )


def _report(scores, final):
    return ReviewReport(
        battle_id=1, dimensions=scores, final_winner=final, overall_confidence=0.8
    )


def test_mapper_ab_to_leftright():
    mapper = VoteMapper(tie_threshold=0.5)
    scores = [
        _score(DimensionKey.THEME, 4, 3, "A"),
        _score(DimensionKey.IMAGINATION, 3, 4, "B"),
        _score(DimensionKey.LOGIC, 5, 5, "tie"),
        _score(DimensionKey.LANGUAGE, 4, 3, "A"),
        _score(DimensionKey.WRITING, 3, 4, "B"),
        _score(DimensionKey.OVERALL, 4, 3, "A"),
    ]
    payload = mapper.to_vote_payload(_report(scores, "A"))
    assert payload.dim_theme == "left"
    assert payload.dim_imagination == "right"
    assert payload.dim_logic == "tie"
    assert payload.dim_overall == "left"


def test_mapper_tie_threshold_forces_tie():
    mapper = VoteMapper(tie_threshold=1.0)
    scores = [
        _score(DimensionKey.THEME, 4.0, 3.5, "A"),  # 分差 0.5 < 1.0 -> tie
        _score(DimensionKey.IMAGINATION, 3, 4.5, "B"),  # 分差 1.5 -> 保留 B
        _score(DimensionKey.LOGIC, 3, 3, "tie"),
        _score(DimensionKey.LANGUAGE, 3, 3, "tie"),
        _score(DimensionKey.WRITING, 3, 3, "tie"),
        _score(DimensionKey.OVERALL, 3.2, 3.0, "A"),  # OVERALL 不看阈值
    ]
    payload = mapper.to_vote_payload(_report(scores, "A"))
    assert payload.dim_theme == "tie"
    assert payload.dim_imagination == "right"
    assert payload.dim_overall == "left"


def test_mapper_missing_dim_fallback_tie():
    mapper = VoteMapper(tie_threshold=0.5)
    scores = [
        _score(DimensionKey.THEME, 4, 3, "A"),
        _score(DimensionKey.OVERALL, 3, 4, "B"),
    ]
    payload = mapper.to_vote_payload(_report(scores, "B"))
    assert payload.dim_imagination == "tie"
    assert payload.dim_logic == "tie"
    assert payload.dim_overall == "right"


def test_mapper_reason_truncation():
    long = "很" * 800
    mapper = VoteMapper(tie_threshold=0.5)
    scores = [_score(d, 3, 3, "tie", reason=long) for d in DimensionKey]
    payload = mapper.to_vote_payload(_report(scores, "tie"))
    assert len(payload.dim_theme_reason) <= 500
