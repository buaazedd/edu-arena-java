"""两份批改对比 Skill：长度/维度覆盖/优点数/问题数/具体度等客观指标对比。"""
from __future__ import annotations

import re
from typing import Dict, List

from pydantic import BaseModel, Field

from .base import BaseSkill

# 关键词匹配（简单的词典法，用于粗粒度维度识别）
_DIM_KEYWORDS: Dict[str, List[str]] = {
    "theme": ["主旨", "中心", "题意", "立意", "主题"],
    "imagination": ["想象", "联想", "创意", "创新"],
    "logic": ["结构", "层次", "逻辑", "段落", "过渡", "顺序"],
    "language": ["语言", "用词", "修辞", "比喻", "拟人", "排比", "病句"],
    "writing": ["书写", "字迹", "卷面", "标点", "整洁"],
    "overall": ["总评", "整体", "总的来说", "综合", "总结"],
}

_POS_KW = ["亮点", "优点", "突出", "好", "精彩", "生动", "成功"]
_NEG_KW = ["不足", "问题", "缺点", "错误", "病句", "欠缺"]
_SUG_KW = ["建议", "可以", "若", "不妨", "最好"]


def _count_kw(text: str, kws: List[str]) -> int:
    return sum(text.count(k) for k in kws)


class FeedbackCompareInput(BaseModel):
    response_a: str
    response_b: str


class FeedbackSummary(BaseModel):
    length: int
    dim_coverage: Dict[str, bool]
    positive_points: int
    negative_points: int
    suggestions: int


class FeedbackCompareOutput(BaseModel):
    a: FeedbackSummary
    b: FeedbackSummary
    verdict: Dict[str, str] = Field(
        description="各指标上的初步判断：A_better | B_better | tie"
    )


def _summarize(text: str) -> FeedbackSummary:
    t = text or ""
    cov = {k: any(w in t for w in kws) for k, kws in _DIM_KEYWORDS.items()}
    return FeedbackSummary(
        length=len(re.sub(r"\s", "", t)),
        dim_coverage=cov,
        positive_points=_count_kw(t, _POS_KW),
        negative_points=_count_kw(t, _NEG_KW),
        suggestions=_count_kw(t, _SUG_KW),
    )


def _cmp(a: int, b: int) -> str:
    if a == b:
        return "tie"
    return "A_better" if a > b else "B_better"


class FeedbackCompareSkill(BaseSkill[FeedbackCompareInput, FeedbackCompareOutput]):
    name = "feedback_compare"
    desc = "客观对比两份批改的长度、维度覆盖、优缺点数量、建议数量"
    InputModel = FeedbackCompareInput
    OutputModel = FeedbackCompareOutput

    def run(self, inp: FeedbackCompareInput) -> FeedbackCompareOutput:
        a = _summarize(inp.response_a)
        b = _summarize(inp.response_b)
        verdict = {
            "length": _cmp(a.length, b.length),
            "dim_coverage": _cmp(sum(a.dim_coverage.values()), sum(b.dim_coverage.values())),
            "positive": _cmp(a.positive_points, b.positive_points),
            "negative": _cmp(a.negative_points, b.negative_points),
            "suggestions": _cmp(a.suggestions, b.suggestions),
        }
        return FeedbackCompareOutput(a=a, b=b, verdict=verdict)
