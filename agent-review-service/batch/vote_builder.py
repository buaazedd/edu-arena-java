"""把评审服务返回的 VotePayload 转换为 ArenaVoteRequest。

由于 VotePayload 字段顺序与 Java `VoteRequest` 完全对齐，这里只是一个
显式字段复制 + 类型校验，保证即使 review 服务升级也能在此拦截。
"""
from __future__ import annotations

from app.contracts.arena_dto import ArenaVoteRequest
from app.contracts.review_dto import VotePayload


def vote_payload_to_request(payload: VotePayload) -> ArenaVoteRequest:
    return ArenaVoteRequest(
        dim_theme=payload.dim_theme,
        dim_theme_reason=payload.dim_theme_reason or None,
        dim_imagination=payload.dim_imagination,
        dim_imagination_reason=payload.dim_imagination_reason or None,
        dim_logic=payload.dim_logic,
        dim_logic_reason=payload.dim_logic_reason or None,
        dim_language=payload.dim_language,
        dim_language_reason=payload.dim_language_reason or None,
        dim_writing=payload.dim_writing,
        dim_writing_reason=payload.dim_writing_reason or None,
        dim_overall=payload.dim_overall,
        dim_overall_reason=payload.dim_overall_reason or None,
        vote_time=payload.vote_time,
    )


__all__ = ["vote_payload_to_request"]
