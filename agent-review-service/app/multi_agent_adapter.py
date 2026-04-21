from __future__ import annotations

from typing import Any

from app.graph import run_review
from app.models import ModelOutput, ReviewInput, ReviewJobRequest, RubricConfig, TaskMeta
from app.review_contract import DimensionVote, ReviewCase, ReviewEngine, ReviewResult


class MultiAgentAdapter(ReviewEngine):
    """
    统一评审接口适配器。

    默认直接对接当前 agent-review-service 内置的 LangGraph 多 agent 系统。
    也支持注入外部 backend：
    - backend.review(case)
    - backend.run(case)
    - callable(case)
    """

    def __init__(self, backend: Any | None = None):
        self.backend = backend

    def review(self, case: ReviewCase) -> ReviewResult:
        if self.backend is None:
            raw = self._run_local_graph(case)
        else:
            raw = self._run_backend(case)
        return self._to_result(raw)

    def _run_local_graph(self, case: ReviewCase) -> dict:
        req = ReviewJobRequest(
            battleId=case.battle_id or 0,
            taskMeta=TaskMeta(
                essayTitle=case.essay_title,
                gradeLevel="初中",
                requirements=None,
            ),
            input=ReviewInput(
                essayText=case.essay_content or "",
                images=case.image_paths,
            ),
            outputs={
                "modelA": ModelOutput(modelId=case.model_left or "modelA", content=case.left_text),
                "modelB": ModelOutput(modelId=case.model_right or "modelB", content=case.right_text),
            },
            rubricConfig=RubricConfig(),
        )
        result = run_review(req)
        return result.model_dump()

    def _run_backend(self, case: ReviewCase) -> dict:
        if hasattr(self.backend, "review"):
            out = self.backend.review(case)
        elif hasattr(self.backend, "run"):
            out = self.backend.run(case)
        elif callable(self.backend):
            out = self.backend(case)
        else:
            raise TypeError("backend must provide review/run callable")

        if hasattr(out, "model_dump"):
            return out.model_dump()
        if isinstance(out, dict):
            return out
        raise TypeError(f"Unsupported backend output type: {type(out)}")

    @staticmethod
    def _to_result(raw: dict) -> ReviewResult:
        dimension_results = raw.get("dimensionResults") or raw.get("dimension_results") or []

        def dv(key: str) -> DimensionVote:
            item = None
            if isinstance(dimension_results, list):
                for row in dimension_results:
                    if row.get("dimension") == key:
                        item = row
                        break
            item = item or raw.get(key, {}) or {}
            return DimensionVote(
                winner=str(item.get("winner", "tie")),
                reason=str(item.get("reason", "")),
                score_a=float(item.get("scoreA", item.get("score_a", 0.0)) or 0.0),
                score_b=float(item.get("scoreB", item.get("score_b", 0.0)) or 0.0),
                confidence=float(item.get("confidence", 0.0) or 0.0),
                evidence_a=[str(x) for x in item.get("evidenceA", item.get("evidence_a", [])) or []],
                evidence_b=[str(x) for x in item.get("evidenceB", item.get("evidence_b", [])) or []],
            )

        final_winner = str(raw.get("finalWinner", raw.get("overall_winner", raw.get("winner", "tie"))))
        confidence = raw.get("finalConfidence", raw.get("confidence"))
        if confidence is not None:
            confidence = float(confidence)

        return ReviewResult(
            overall_winner=final_winner,
            dim_theme=dv("theme"),
            dim_imagination=dv("imagination"),
            dim_logic=dv("logic"),
            dim_language=dv("language"),
            dim_writing=dv("writing"),
            confidence=confidence,
            reason=raw.get("reason") or raw.get("summary"),
            raw_output=raw,
        )
