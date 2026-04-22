"""文本统计 Skill：中文字数 / 段落数 / 平均句长。"""
from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .base import BaseSkill

_CN_CHAR = re.compile(r"[\u4e00-\u9fff]")
_SENT_SPLIT = re.compile(r"[。！？；!?;]+")


class TextStatsInput(BaseModel):
    text: str


class TextStatsOutput(BaseModel):
    char_count: int = Field(description="中文字符数")
    total_char_count: int = Field(description="总字符数（含标点/空格）")
    paragraph_count: int
    sentence_count: int
    avg_sentence_length: float


class WordCountSkill(BaseSkill[TextStatsInput, TextStatsOutput]):
    name = "text_stats"
    desc = "统计中文字符数、段落数、句子数、平均句长"
    InputModel = TextStatsInput
    OutputModel = TextStatsOutput

    def run(self, inp: TextStatsInput) -> TextStatsOutput:
        text = inp.text or ""
        cn_chars = _CN_CHAR.findall(text)
        paragraphs = [p for p in re.split(r"\n\s*\n+", text) if p.strip()]
        sentences = [s for s in _SENT_SPLIT.split(text) if s.strip()]
        avg = (len(cn_chars) / len(sentences)) if sentences else 0.0
        return TextStatsOutput(
            char_count=len(cn_chars),
            total_char_count=len(text),
            paragraph_count=max(1, len(paragraphs)),
            sentence_count=len(sentences),
            avg_sentence_length=round(avg, 2),
        )
