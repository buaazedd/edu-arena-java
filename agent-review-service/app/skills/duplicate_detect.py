"""重复内容检测 Skill（基于 n-gram shingle + Jaccard）。"""
from __future__ import annotations

import re
from typing import List, Tuple

from pydantic import BaseModel, Field

from .base import BaseSkill

_SENT_SPLIT = re.compile(r"[。！？!?；\n]+")


def _shingles(s: str, n: int = 3) -> set[str]:
    s2 = re.sub(r"\s+", "", s)
    if len(s2) < n:
        return {s2} if s2 else set()
    return {s2[i : i + n] for i in range(len(s2) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


class DuplicateInput(BaseModel):
    text: str
    threshold: float = Field(default=0.5, ge=0, le=1)


class DuplicatePair(BaseModel):
    a: str
    b: str
    similarity: float


class DuplicateOutput(BaseModel):
    pairs: List[DuplicatePair]
    ratio: float = Field(description="重复句子占比，0~1")


class DuplicateDetectSkill(BaseSkill[DuplicateInput, DuplicateOutput]):
    name = "duplicate_detect"
    desc = "检测文本中意思重复/高度相似的句子对"
    InputModel = DuplicateInput
    OutputModel = DuplicateOutput

    def run(self, inp: DuplicateInput) -> DuplicateOutput:
        sents = [s.strip() for s in _SENT_SPLIT.split(inp.text or "") if len(s.strip()) >= 6]
        pairs: List[DuplicatePair] = []
        dup_idx: set[int] = set()
        n = len(sents)
        sh_cache = [_shingles(s) for s in sents]
        for i in range(n):
            for j in range(i + 1, n):
                sim = _jaccard(sh_cache[i], sh_cache[j])
                if sim >= inp.threshold:
                    pairs.append(DuplicatePair(a=sents[i], b=sents[j], similarity=round(sim, 3)))
                    dup_idx.add(j)
        ratio = len(dup_idx) / n if n else 0.0
        return DuplicateOutput(pairs=pairs, ratio=round(ratio, 3))
