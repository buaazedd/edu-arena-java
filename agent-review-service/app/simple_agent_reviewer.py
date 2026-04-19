from __future__ import annotations

from app.arena_dto import AgentDimensionVote, AgentVoteResult


class SimpleAgentReviewer:
    """
    可替换的评审器骨架。
    当前默认实现：长度 + 关键词命中 的轻量规则评审，便于先跑通全链路。
    后续可替换为调用你现有 /review/run 或真实 LLM 判分。
    """

    def review(self, essay_title: str, essay_content: str, left_text: str, right_text: str) -> AgentVoteResult:
        left_score = self._score(left_text)
        right_score = self._score(right_text)

        if abs(left_score - right_score) <= 0.8:
            winner = "tie"
        elif left_score > right_score:
            winner = "A"
        else:
            winner = "B"

        reason = f"规则评分: left={left_score:.2f}, right={right_score:.2f}"
        dim = AgentDimensionVote(winner=winner, reason=reason)

        return AgentVoteResult(
            dim_theme=dim,
            dim_imagination=dim,
            dim_logic=dim,
            dim_language=dim,
            dim_writing=dim,
        )

    @staticmethod
    def _score(text: str) -> float:
        if not text:
            return 0.0

        length_score = min(len(text) / 300.0, 5.0)
        keyword_bonus = 0.0
        keywords = ["因此", "首先", "其次", "总之", "比如", "因为", "所以"]
        for kw in keywords:
            if kw in text:
                keyword_bonus += 0.3

        return length_score + keyword_bonus
