"""批改覆盖度分析 Skill：对单份批改输出其对六个维度的覆盖度与粒度。"""
from __future__ import annotations

from typing import Dict

from pydantic import BaseModel, Field

from .base import BaseSkill
from .feedback_compare import _DIM_KEYWORDS  # 复用关键词字典


class CoverageInput(BaseModel):
    response: str


class CoverageOutput(BaseModel):
    coverage: Dict[str, float] = Field(
        description="每个维度的覆盖分 0~1，基于关键词命中频次归一化"
    )
    covered_dims: int


class CoverageAnalyzerSkill(BaseSkill[CoverageInput, CoverageOutput]):
    name = "coverage_analyzer"
    desc = "评估单份批改对六维度的覆盖度"
    InputModel = CoverageInput
    OutputModel = CoverageOutput

    def run(self, inp: CoverageInput) -> CoverageOutput:
        text = inp.response or ""
        coverage: Dict[str, float] = {}
        covered = 0
        for dim, kws in _DIM_KEYWORDS.items():
            hits = sum(text.count(k) for k in kws)
            # 命中 0 次 -> 0；命中 1 次 -> 0.4；命中 2 次 -> 0.7；>=3 次 -> 1.0
            if hits == 0:
                score = 0.0
            elif hits == 1:
                score = 0.4
            elif hits == 2:
                score = 0.7
            else:
                score = 1.0
            coverage[dim] = score
            if score > 0:
                covered += 1
        return CoverageOutput(coverage=coverage, covered_dims=covered)
