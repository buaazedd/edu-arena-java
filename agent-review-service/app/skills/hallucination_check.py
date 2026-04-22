"""批改幻觉检测 Skill：检查批改中引用的"原文片段"是否确实存在于作文中。

工作方式：
- 从批改内容里用正则/引号提取被引用的短句片段（如 "……"/「……」/原文"……"）
- 把每个片段与作文原文做子串/shingle 匹配
- 匹配失败的片段视为疑似幻觉
"""
from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from .base import BaseSkill
from .duplicate_detect import _jaccard, _shingles

_QUOTE_PATTERNS = [
    re.compile(r"[“\"]([^”\"]{4,40})[”\"]"),
    re.compile(r"「([^」]{4,40})」"),
    re.compile(r"原文[:：]?\s*“?([^\"”\n]{4,40})”?"),
]


class HallucinationCheckInput(BaseModel):
    feedback: str = Field(description="批改内容")
    essay_text: Optional[str] = Field(default=None, description="作文原文（若无则跳过检测）")
    similarity_threshold: float = Field(default=0.5, ge=0, le=1)


class SuspectQuote(BaseModel):
    quote: str
    max_similarity: float


class HallucinationCheckOutput(BaseModel):
    total_quotes: int
    suspect_quotes: List[SuspectQuote] = Field(default_factory=list)
    hallucination_rate: float = Field(ge=0, le=1, description="可疑引用占比")
    skipped: bool = Field(default=False, description="无原文时为 True")


class HallucinationCheckSkill(BaseSkill[HallucinationCheckInput, HallucinationCheckOutput]):
    name = "hallucination_check"
    desc = "检查批改中引用的原文片段是否真的出现在作文里，定位疑似幻觉"
    InputModel = HallucinationCheckInput
    OutputModel = HallucinationCheckOutput

    def run(self, inp: HallucinationCheckInput) -> HallucinationCheckOutput:
        if not inp.essay_text or not inp.essay_text.strip():
            return HallucinationCheckOutput(total_quotes=0, hallucination_rate=0.0, skipped=True)

        quotes: List[str] = []
        for rx in _QUOTE_PATTERNS:
            quotes.extend(m.group(1) for m in rx.finditer(inp.feedback or ""))
        quotes = [q.strip() for q in quotes if q.strip()]
        if not quotes:
            return HallucinationCheckOutput(total_quotes=0, hallucination_rate=0.0)

        essay = inp.essay_text
        essay_sh = _shingles(essay, n=3)
        suspects: List[SuspectQuote] = []
        for q in quotes:
            if q in essay:
                continue
            sim = _jaccard(_shingles(q, n=3), essay_sh)
            if sim < inp.similarity_threshold:
                suspects.append(SuspectQuote(quote=q, max_similarity=round(sim, 3)))
        rate = len(suspects) / len(quotes)
        return HallucinationCheckOutput(
            total_quotes=len(quotes),
            suspect_quotes=suspects,
            hallucination_rate=round(rate, 3),
        )
