"""决策器 VoteMapper 深度测试。"""
from __future__ import annotations

import pytest

from app.contracts.review_dto import VotePayload
from app.contracts.review_models import DimensionKey, DimensionScore, ReviewReport
from app.review.decision import VoteMapper, _map_side, _resolve_dim, _truncate


# ─────────────── 辅助函数测试 ───────────────

class TestHelpers:
    def test_map_side_A(self):
        assert _map_side("A") == "left"

    def test_map_side_B(self):
        assert _map_side("B") == "right"

    def test_map_side_tie(self):
        assert _map_side("tie") == "tie"

    def test_map_side_unknown(self):
        assert _map_side("X") == "tie"

    def test_map_side_empty(self):
        assert _map_side("") == "tie"

    def test_truncate_short(self):
        assert _truncate("短文本") == "短文本"

    def test_truncate_exact_limit(self):
        text = "a" * 500
        assert _truncate(text) == text

    def test_truncate_over_limit(self):
        text = "a" * 600
        result = _truncate(text)
        assert len(result) == 500
        assert result.endswith("…")

    def test_truncate_empty(self):
        assert _truncate("") == ""

    def test_truncate_none_safe(self):
        assert _truncate("") == ""

    def test_truncate_strips_whitespace(self):
        assert _truncate("  hello  ") == "hello"


class TestResolveDim:
    def test_overall_uses_winner(self):
        score = DimensionScore(
            dim=DimensionKey.OVERALL, score_a=3.1, score_b=3.0,
            winner="A", reason="ok", confidence=0.8,
        )
        # OVERALL 不看分差阈值
        assert _resolve_dim(DimensionKey.OVERALL, score, tie_threshold=1.0) == "left"

    def test_non_overall_within_threshold(self):
        score = DimensionScore(
            dim=DimensionKey.THEME, score_a=3.3, score_b=3.0,
            winner="A", reason="ok", confidence=0.8,
        )
        # 分差 0.3 < 阈值 0.5 → tie
        assert _resolve_dim(DimensionKey.THEME, score, tie_threshold=0.5) == "tie"

    def test_non_overall_exceeds_threshold(self):
        score = DimensionScore(
            dim=DimensionKey.THEME, score_a=4.0, score_b=3.0,
            winner="A", reason="ok", confidence=0.8,
        )
        # 分差 1.0 >= 阈值 0.5 → left (A)
        assert _resolve_dim(DimensionKey.THEME, score, tie_threshold=0.5) == "left"


# ─────────────── VoteMapper 集成测试 ───────────────

def _score(dim, a, b, winner, reason="ok"):
    return DimensionScore(dim=dim, score_a=a, score_b=b, winner=winner, reason=reason, confidence=0.8)


def _report(scores, final):
    return ReviewReport(battle_id=1, dimensions=scores, final_winner=final, overall_confidence=0.8)


class TestVoteMapper:
    def test_all_a_wins(self):
        mapper = VoteMapper(tie_threshold=0.5)
        scores = [_score(d, 4, 2, "A") for d in DimensionKey]
        payload = mapper.to_vote_payload(_report(scores, "A"))
        assert payload.dim_overall == "left"
        assert payload.dim_theme == "left"

    def test_all_b_wins(self):
        mapper = VoteMapper(tie_threshold=0.5)
        scores = [_score(d, 2, 4, "B") for d in DimensionKey]
        payload = mapper.to_vote_payload(_report(scores, "B"))
        assert payload.dim_overall == "right"
        assert payload.dim_theme == "right"

    def test_all_tie(self):
        mapper = VoteMapper(tie_threshold=0.5)
        scores = [_score(d, 3, 3, "tie") for d in DimensionKey]
        payload = mapper.to_vote_payload(_report(scores, "tie"))
        assert payload.dim_overall == "tie"
        assert payload.dim_theme == "tie"

    def test_missing_dims_fallback_tie(self):
        mapper = VoteMapper(tie_threshold=0.5)
        scores = [
            _score(DimensionKey.THEME, 4, 3, "A"),
            _score(DimensionKey.OVERALL, 4, 3, "A"),
        ]
        payload = mapper.to_vote_payload(_report(scores, "A"))
        assert payload.dim_theme == "left"
        assert payload.dim_overall == "left"
        # 缺失的维度回退为 tie
        assert payload.dim_imagination == "tie"
        assert payload.dim_logic == "tie"
        assert payload.dim_language == "tie"
        assert payload.dim_writing == "tie"

    def test_threshold_forces_tie(self):
        mapper = VoteMapper(tie_threshold=2.0)  # 很大的阈值
        scores = [_score(d, 4, 3, "A") for d in DimensionKey]
        payload = mapper.to_vote_payload(_report(scores, "A"))
        # OVERALL 不看阈值，直接用 winner
        assert payload.dim_overall == "left"
        # 其他维度分差 1.0 < 2.0 → 强制 tie
        assert payload.dim_theme == "tie"

    def test_reason_truncation(self):
        mapper = VoteMapper(tie_threshold=0.5)
        long_reason = "很" * 800
        scores = [_score(d, 3, 3, "tie", reason=long_reason) for d in DimensionKey]
        payload = mapper.to_vote_payload(_report(scores, "tie"))
        assert len(payload.dim_theme_reason) <= 500

    def test_consistency_protection(self):
        """当 report.final_winner 与 OVERALL.winner 不一致时，以 OVERALL 为准。"""
        mapper = VoteMapper(tie_threshold=0.5)
        scores = [
            _score(DimensionKey.THEME, 4, 3, "A"),
            _score(DimensionKey.IMAGINATION, 3, 4, "B"),
            _score(DimensionKey.LOGIC, 3, 3, "tie"),
            _score(DimensionKey.LANGUAGE, 3, 3, "tie"),
            _score(DimensionKey.WRITING, 3, 3, "tie"),
            _score(DimensionKey.OVERALL, 3, 4, "B"),
        ]
        # 故意传 final_winner="A"，但 OVERALL.winner="B"
        report = _report(scores, "A")
        payload = mapper.to_vote_payload(report)
        # 一致性保护：dim_overall 应跟 OVERALL.winner
        assert payload.dim_overall == "right"  # B -> right

    def test_zero_threshold(self):
        mapper = VoteMapper(tie_threshold=0.0)
        scores = [_score(d, 3.01, 3.0, "A") for d in DimensionKey]
        payload = mapper.to_vote_payload(_report(scores, "A"))
        assert payload.dim_theme == "left"  # 分差 0.01 >= 0
