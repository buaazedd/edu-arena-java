"""中文病句规则检测 Skill（轻量规则版，不依赖外部模型）。"""
from __future__ import annotations

import re
from typing import List

from pydantic import BaseModel, Field

from .base import BaseSkill


class GrammarCheckInput(BaseModel):
    text: str


class GrammarIssue(BaseModel):
    pattern: str
    excerpt: str
    suggestion: str


class GrammarCheckOutput(BaseModel):
    issues: List[GrammarIssue] = Field(default_factory=list)
    score: float = Field(description="0~1，越高越规范")


# 常见病句/搭配问题的轻量规则
_RULES: List[tuple[re.Pattern, str, str]] = [
    (re.compile(r"([兴奋激动高兴伤心紧张开心害怕)(的)(?=[\u4e00-\u9fff]*[动动跑跳喊走听看说])"),
     "形容词+的+动词", "应为‘形容词+地+动词’"),
    (re.compile(r"非常地|十分地"),
     "非常/十分+地", "‘非常/十分’后直接接形容词，不需‘地’"),
    (re.compile(r"避免不([\u4e00-\u9fff])"),
     "避免不…", "‘避免’本身含‘不’的意思，改为‘避免…’或‘尽量不…’"),
    (re.compile(r"大约[\d一二三四五六七八九十百千万]+左右"),
     "大约…左右", "‘大约’和‘左右’语义重复，二选一"),
    (re.compile(r"切忌不要"),
     "切忌+不要", "‘切忌’含否定，应为‘切忌…’"),
    (re.compile(r"(?:的的|了了|地地)"),
     "助词重复", "删除多余助词"),
]


class GrammarCheckSkill(BaseSkill[GrammarCheckInput, GrammarCheckOutput]):
    name = "grammar_check"
    desc = "基于规则的中文常见病句/搭配错误检测"
    InputModel = GrammarCheckInput
    OutputModel = GrammarCheckOutput

    def run(self, inp: GrammarCheckInput) -> GrammarCheckOutput:
        text = inp.text or ""
        issues: List[GrammarIssue] = []
        for rx, pat, suggest in _RULES:
            for m in rx.finditer(text):
                start, end = m.span()
                excerpt = text[max(0, start - 8) : min(len(text), end + 8)]
                issues.append(GrammarIssue(pattern=pat, excerpt=excerpt, suggestion=suggest))
        # 归一化分数：问题越多分越低，每个问题扣 0.15，下限 0
        score = max(0.0, 1.0 - 0.15 * len(issues))
        return GrammarCheckOutput(issues=issues, score=round(score, 3))
