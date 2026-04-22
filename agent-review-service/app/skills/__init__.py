"""Skill 领域工具包：可复用的中文文本/批改分析能力。

所有 Skill 统一继承 `BaseSkill` 并注册到 `SkillRegistry`，
Agent 节点通过 `registry.get("name").run(input)` 调用。
"""

from .base import BaseSkill, SkillRegistry, registry
from .coverage_analyzer import CoverageAnalyzerSkill, CoverageInput, CoverageOutput
from .duplicate_detect import DuplicateDetectSkill, DuplicateInput, DuplicateOutput
from .feedback_compare import FeedbackCompareInput, FeedbackCompareOutput, FeedbackCompareSkill
from .grammar_check import GrammarCheckInput, GrammarCheckOutput, GrammarCheckSkill
from .hallucination_check import HallucinationCheckInput, HallucinationCheckOutput, HallucinationCheckSkill
from .text_stats import TextStatsInput, TextStatsOutput, WordCountSkill


def _register_all() -> None:
    registry.register(WordCountSkill())
    registry.register(GrammarCheckSkill())
    registry.register(DuplicateDetectSkill())
    registry.register(FeedbackCompareSkill())
    registry.register(CoverageAnalyzerSkill())
    registry.register(HallucinationCheckSkill())


_register_all()

__all__ = [
    "BaseSkill",
    "SkillRegistry",
    "registry",
    "WordCountSkill",
    "TextStatsInput",
    "TextStatsOutput",
    "GrammarCheckSkill",
    "GrammarCheckInput",
    "GrammarCheckOutput",
    "DuplicateDetectSkill",
    "DuplicateInput",
    "DuplicateOutput",
    "FeedbackCompareSkill",
    "FeedbackCompareInput",
    "FeedbackCompareOutput",
    "CoverageAnalyzerSkill",
    "CoverageInput",
    "CoverageOutput",
    "HallucinationCheckSkill",
    "HallucinationCheckInput",
    "HallucinationCheckOutput",
]
