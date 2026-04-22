"""契约层序列化测试：确保对 Java 端 snake_case 的字段兼容。"""
from __future__ import annotations

import json

from app.contracts.arena_dto import (
    ArenaCreateBattleRequest,
    ArenaVoteRequest,
    ArenaVoteResultVO,
)
from app.contracts.review_dto import ReviewRequest, VotePayload
from app.contracts.review_models import DimensionKey, DimensionScore, ReviewReport


def test_create_battle_request_snake_case():
    req = ArenaCreateBattleRequest(
        essay_title="秋天",
        images=["AAA"],
        essay_content="内容",
        grade_level="初中",
        requirements="要求",
    )
    j = json.loads(req.model_dump_json(exclude_none=True))
    assert j["essay_title"] == "秋天"
    assert j["grade_level"] == "初中"
    assert "images" in j


def test_vote_request_values_restricted():
    v = ArenaVoteRequest(
        dim_theme="left",
        dim_imagination="right",
        dim_logic="tie",
        dim_language="left",
        dim_writing="tie",
        dim_overall="left",
    )
    j = v.model_dump(exclude_none=True)
    assert j["dim_theme"] == "left"
    assert j["dim_overall"] == "left"


def test_review_request_roundtrip():
    req = ReviewRequest(
        battle_id=1, essay_title="t", response_a="aaa", response_b="bbb"
    )
    d = req.model_dump()
    assert d["response_a"] == "aaa"
    assert d["battle_id"] == 1


def test_review_report_with_dimensions():
    scores = [
        DimensionScore(
            dim=dim, score_a=3, score_b=4, winner="B", reason="r", confidence=0.8
        )
        for dim in DimensionKey
    ]
    report = ReviewReport(
        battle_id=1,
        dimensions=scores,
        final_winner="B",
        overall_confidence=0.8,
    )
    assert len(report.dimensions) == 6
    assert report.dimensions[-1].dim == DimensionKey.OVERALL


def test_vote_payload_all_sides():
    p = VotePayload(
        dim_theme="left",
        dim_imagination="right",
        dim_logic="tie",
        dim_language="left",
        dim_writing="tie",
        dim_overall="right",
    )
    assert p.dim_overall == "right"


def test_vote_result_vo_snake_case_parse():
    raw = {
        "message": "ok",
        "overall_winner": "A",
        "a_wins": 4,
        "b_wins": 1,
        "winner_side": "left",
        "winner_label": "模型A",
        "left_model_slot": "A",
        "right_model_slot": "B",
        "elo_a_before": 1500.0,
        "elo_a_after": 1516.0,
        "elo_b_before": 1500.0,
        "elo_b_after": 1484.0,
    }
    vo = ArenaVoteResultVO.model_validate(raw)
    assert vo.winner_side == "left"
    assert vo.elo_a_after > vo.elo_a_before
