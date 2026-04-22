"""ReviewService 外观类测试：_build_report / _merge_dimensions / 错误处理。"""
from __future__ import annotations

from typing import Dict, List

import pytest

from app.contracts.review_dto import ReviewRequest
from app.contracts.review_models import (
    ArbitrationResult,
    DimensionKey,
    DimensionScore,
    ReviewReport,
)
from app.review.service import _build_report, _merge_dimensions, _to_battle_ctx


class TestToBattleCtx:
    def test_basic_conversion(self, sample_review_request):
        ctx = _to_battle_ctx(sample_review_request)
        assert ctx.battle_id == sample_review_request.battle_id
        assert ctx.essay_title == sample_review_request.essay_title
        assert ctx.response_a == sample_review_request.response_a
        assert ctx.response_b == sample_review_request.response_b

    def test_default_grade_level(self):
        req = ReviewRequest(
            battle_id=1, essay_title="test",
            response_a="a", response_b="b",
            grade_level=None,
        )
        ctx = _to_battle_ctx(req)
        assert ctx.grade_level == "初中"


class TestMergeDimensions:
    def test_no_arbitration(self, all_dimension_scores):
        merged = _merge_dimensions(all_dimension_scores, None)
        assert len(merged) == 6
        # 应按枚举顺序排列
        assert merged[0].dim == DimensionKey.THEME
        assert merged[-1].dim == DimensionKey.OVERALL

    def test_arbitration_overrides(self, all_dimension_scores):
        adjusted = DimensionScore(
            dim=DimensionKey.LANGUAGE, score_a=5, score_b=2,
            winner="A", reason="仲裁修正", confidence=0.9,
        )
        arb = ArbitrationResult(
            final_winner="A", overall_confidence=0.8,
            rationale="仲裁", adjusted_dimensions=[adjusted],
        )
        merged = _merge_dimensions(all_dimension_scores, arb)
        lang = next(d for d in merged if d.dim == DimensionKey.LANGUAGE)
        assert lang.score_a == 5
        assert lang.reason == "仲裁修正"

    def test_empty_arbitration_no_change(self, all_dimension_scores):
        arb = ArbitrationResult(
            final_winner="A", overall_confidence=0.8,
            adjusted_dimensions=[],
        )
        merged = _merge_dimensions(all_dimension_scores, arb)
        assert len(merged) == 6


class TestBuildReport:
    def test_with_arbitration(self, all_dimension_scores):
        arb = ArbitrationResult(
            final_winner="A", overall_confidence=0.85,
            rationale="仲裁结论",
        )
        state = {
            "dimension_scores": all_dimension_scores,
            "arbitration": arb,
            "errors": [],
        }
        report = _build_report(42, state)
        assert report.battle_id == 42
        assert report.final_winner == "A"
        assert report.overall_confidence == 0.85

    def test_without_arbitration(self, all_dimension_scores):
        state = {
            "dimension_scores": all_dimension_scores,
            "arbitration": None,
            "errors": [],
        }
        report = _build_report(42, state)
        # 应从 OVERALL 维度取 winner
        assert report.final_winner == "A"

    def test_missing_dimensions(self):
        """不足 6 维时不崩溃。"""
        scores = [
            DimensionScore(
                dim=DimensionKey.THEME, score_a=4, score_b=3,
                winner="A", reason="ok", confidence=0.8,
            ),
        ]
        state = {"dimension_scores": scores, "arbitration": None, "errors": []}
        report = _build_report(1, state)
        assert len(report.dimensions) == 1
        assert report.final_winner == "tie"  # 没有 OVERALL 维度

    def test_empty_scores(self):
        state = {"dimension_scores": [], "arbitration": None, "errors": ["some error"]}
        report = _build_report(1, state)
        assert report.final_winner == "tie"
        assert len(report.errors) == 1

    def test_errors_propagated(self, all_dimension_scores):
        state = {
            "dimension_scores": all_dimension_scores,
            "arbitration": None,
            "errors": ["error1", "error2"],
        }
        report = _build_report(42, state)
        assert report.errors == ["error1", "error2"]
