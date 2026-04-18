from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


Winner = Literal["A", "B", "tie"]
DimensionName = Literal["theme", "imagination", "logic", "language", "writing"]


class ReviewStatus(str, Enum):
    QUEUED = "queued"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskMeta(BaseModel):
    essayTitle: str
    gradeLevel: str
    requirements: Optional[str] = None


class ModelOutput(BaseModel):
    modelId: str
    content: str


class ReviewInput(BaseModel):
    essayText: str = ""
    images: List[str] = Field(default_factory=list)


class RubricConfig(BaseModel):
    version: str = "rubric_v1"
    dimensions: List[DimensionName] = Field(
        default_factory=lambda: ["theme", "imagination", "logic", "language", "writing"]
    )


class ReviewJobRequest(BaseModel):
    battleId: int
    taskMeta: TaskMeta
    input: ReviewInput
    outputs: Dict[Literal["modelA", "modelB"], ModelOutput]
    rubricConfig: RubricConfig = Field(default_factory=RubricConfig)


class DimensionResult(BaseModel):
    dimension: DimensionName
    winner: Winner
    scoreA: float = Field(ge=0, le=10)
    scoreB: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)
    reason: str
    evidenceA: List[str] = Field(default_factory=list)
    evidenceB: List[str] = Field(default_factory=list)


class PanelJudgeResult(BaseModel):
    modelId: str
    winner: Winner
    scoreA: float = Field(ge=0, le=10)
    scoreB: float = Field(ge=0, le=10)
    confidence: float = Field(ge=0, le=1)
    reason: str
    evidenceA: List[str] = Field(default_factory=list)
    evidenceB: List[str] = Field(default_factory=list)


class CostInfo(BaseModel):
    promptTokens: int = 0
    completionTokens: int = 0
    estimatedCny: float = 0.0
    latencyMs: int = 0


class ReviewJobResponse(BaseModel):
    jobId: str
    battleId: int
    status: ReviewStatus


class ReviewJobStatusResponse(BaseModel):
    jobId: str
    battleId: int
    status: ReviewStatus
    error: Optional[str] = None


class ReviewResult(BaseModel):
    jobId: str
    battleId: int
    status: ReviewStatus
    finalWinner: Winner
    finalConfidence: float = Field(ge=0, le=1)
    needsHuman: bool
    reviewVersion: str
    dimensionResults: List[DimensionResult]
    traceId: str
    cost: CostInfo
    createdAt: datetime
    nodeOutputs: Dict[str, Any] = Field(default_factory=dict)
    retrievalUsed: Dict[str, Any] = Field(default_factory=dict)


class RagDocument(BaseModel):
    id: str
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RagUpsertRequest(BaseModel):
    index: Literal["rubric", "exemplar", "gold_case", "error_pattern"]
    documents: List[RagDocument]


class RagSearchRequest(BaseModel):
    index: Literal["rubric", "exemplar", "gold_case", "error_pattern"]
    query: str
    topK: int = Field(default=3, ge=1, le=20)
    where: Dict[str, Any] = Field(default_factory=dict)


class RagSearchHit(BaseModel):
    id: str
    score: float
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
