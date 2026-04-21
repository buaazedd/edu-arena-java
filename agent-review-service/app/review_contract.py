from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class DimensionVote:
    winner: str  # 'A' | 'B' | 'tie'
    reason: str
    score_a: float = 0.0
    score_b: float = 0.0
    confidence: float = 0.0
    evidence_a: list[str] = field(default_factory=list)
    evidence_b: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "winner": self.winner,
            "reason": self.reason,
            "score_a": self.score_a,
            "score_b": self.score_b,
            "confidence": self.confidence,
            "evidence_a": self.evidence_a,
            "evidence_b": self.evidence_b,
        }


@dataclass
class ReviewCase:
    sample_id: str
    essay_title: str
    essay_content: Optional[str]
    image_paths: list[str] = field(default_factory=list)
    left_text: str = ""
    right_text: str = ""
    model_left: Optional[str] = None
    model_right: Optional[str] = None
    battle_id: Optional[int] = None


@dataclass
class ReviewResult:
    overall_winner: str  # 'A' | 'B' | 'tie'
    dim_theme: DimensionVote
    dim_imagination: DimensionVote
    dim_logic: DimensionVote
    dim_language: DimensionVote
    dim_writing: DimensionVote
    confidence: float | None = None
    reason: str | None = None
    raw_output: dict | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "overall_winner": self.overall_winner,
            "dim_theme": self.dim_theme.to_dict(),
            "dim_imagination": self.dim_imagination.to_dict(),
            "dim_logic": self.dim_logic.to_dict(),
            "dim_language": self.dim_language.to_dict(),
            "dim_writing": self.dim_writing.to_dict(),
            "confidence": self.confidence,
            "reason": self.reason,
            "raw_output": self.raw_output,
        }


class ReviewEngine(ABC):
    @abstractmethod
    def review(self, case: ReviewCase) -> ReviewResult:
        raise NotImplementedError
