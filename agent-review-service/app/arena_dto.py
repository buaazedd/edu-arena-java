from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


VoteSide = Literal["left", "right", "tie"]


class ArenaResult(BaseModel):
    code: int
    message: str
    data: Any | None = None


class ArenaLoginRequest(BaseModel):
    username: str
    password: str


class ArenaLoginData(BaseModel):
    token: str
    role: Optional[str] = None
    user_id: Optional[int] = Field(default=None, alias="user_id")
    display_name: Optional[str] = Field(default=None, alias="display_name")


class ArenaCreateBattleRequest(BaseModel):
    essay_title: str
    essay_content: str | None = None
    grade_level: str = "高中"
    requirements: str = "请从主旨、想象、逻辑、语言、书写五个维度综合评价。"
    images: list[str] = Field(default_factory=list)


class ArenaModelSimple(BaseModel):
    id: int | None = None
    name: str | None = None
    company: str | None = None


class ArenaBattleData(BaseModel):
    battle_id: int = Field(alias="battle_id")
    status: str
    essay_title: str | None = Field(default=None, alias="essay_title")
    essay_content: str | None = Field(default=None, alias="essay_content")
    response_left: str | None = Field(default=None, alias="response_left")
    response_right: str | None = Field(default=None, alias="response_right")
    model_left: ArenaModelSimple | None = Field(default=None, alias="model_left")
    model_right: ArenaModelSimple | None = Field(default=None, alias="model_right")


class ArenaVoteRequest(BaseModel):
    dim_theme: VoteSide
    dim_imagination: VoteSide
    dim_logic: VoteSide
    dim_language: VoteSide
    dim_writing: VoteSide
    dim_theme_reason: str | None = None
    dim_imagination_reason: str | None = None
    dim_logic_reason: str | None = None
    dim_language_reason: str | None = None
    dim_writing_reason: str | None = None
    vote_time: float = 5.0


class AgentDimensionVote(BaseModel):
    winner: Literal["A", "B", "tie"]
    reason: str


class AgentVoteResult(BaseModel):
    dim_theme: AgentDimensionVote
    dim_imagination: AgentDimensionVote
    dim_logic: AgentDimensionVote
    dim_language: AgentDimensionVote
    dim_writing: AgentDimensionVote
