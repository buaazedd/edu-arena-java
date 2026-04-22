"""Skill 工具包测试。"""
from __future__ import annotations

from app.skills import registry
from app.skills.coverage_analyzer import CoverageInput
from app.skills.duplicate_detect import DuplicateInput
from app.skills.feedback_compare import FeedbackCompareInput
from app.skills.grammar_check import GrammarCheckInput
from app.skills.hallucination_check import HallucinationCheckInput
from app.skills.text_stats import TextStatsInput


def test_registry_has_six_skills():
    names = {"text_stats", "grammar_check", "duplicate_detect",
             "feedback_compare", "coverage_analyzer", "hallucination_check"}
    assert names.issubset(set(registry.list()))


def test_text_stats_basic():
    out = registry.get("text_stats").run(TextStatsInput(text="今天天气很好。我们去公园玩。"))
    assert out.char_count > 0
    assert out.sentence_count >= 2


def test_grammar_check_produces_score():
    out = registry.get("grammar_check").run(
        GrammarCheckInput(text="我非常十分开心。再次又重复了一遍。")
    )
    assert 0 <= out.score <= 1


def test_duplicate_detect_returns_ratio():
    out = registry.get("duplicate_detect").run(
        DuplicateInput(text="春天花开。春天花开。春天花开。")
    )
    assert out.ratio >= 0


def test_feedback_compare_runs():
    out = registry.get("feedback_compare").run(
        FeedbackCompareInput(response_a="A 的批改" * 20, response_b="B 的批改" * 30)
    )
    assert isinstance(out.verdict, dict)
    assert "length" in out.verdict
    assert out.verdict["length"] in ("A_better", "B_better", "tie")


def test_coverage_analyzer_basic():
    out = registry.get("coverage_analyzer").run(
        CoverageInput(response="作文主旨明确。语言流畅。结构清晰。")
    )
    assert isinstance(out.coverage, dict)


def test_hallucination_check_basic():
    out = registry.get("hallucination_check").run(
        HallucinationCheckInput(
            feedback='作者写道："秋天真美"，表达准确。',
            essay_text="秋天真美丽，树叶飘落。",
        )
    )
    assert hasattr(out, "hallucination_rate")
