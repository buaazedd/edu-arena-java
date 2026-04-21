from __future__ import annotations

import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, List, TypedDict

import logging

from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.llm import LLMService
from app.models import CostInfo, DimensionResult, ReviewJobRequest, ReviewResult
from app.prompts import (
    build_aggregate_prompt,
    build_aggregate_system_prompt,
    build_dimension_prompt,
    build_dimension_system_prompt,
)
from app.retrieval import RetrievalService


DIMENSIONS = ["theme", "imagination", "logic", "language", "writing"]
logger = logging.getLogger(__name__)


class ReviewState(TypedDict, total=False):
    request: ReviewJobRequest
    job_id: str
    trace_id: str
    started_at: float
    rubric_context: List[dict]
    dimension_context: Dict[str, dict]
    dimension_results: List[dict]
    final: dict
    node_outputs: Dict[str, dict]


retrieval = RetrievalService()


def _mark_node(state: ReviewState, node: str, payload: Dict[str, Any]) -> None:
    nodes = state.get("node_outputs", {})
    nodes[node] = payload
    state["node_outputs"] = nodes


def _judge_models() -> List[str]:
    models = settings.judge_panel_models[: settings.judge_panel_size]
    return models if models else [settings.llm_model]


def _build_dimension_query(req: ReviewJobRequest) -> str:
    return f"{req.input.essayText[:300]}\n{req.outputs['modelA'].content[:300]}\n{req.outputs['modelB'].content[:300]}"


def _preprocess(state: ReviewState) -> ReviewState:
    req = state["request"]
    logger.info(
        "[preprocess] start battleId=%s essayTitleLen=%s essayTextLen=%s modelA=%s modelB=%s",
        req.battleId,
        len(req.taskMeta.essayTitle or ""),
        len(req.input.essayText or ""),
        req.outputs["modelA"].modelId,
        req.outputs["modelB"].modelId,
    )
    rubric_ctx = retrieval.get_rubric_context(req.rubricConfig.dimensions, req.rubricConfig.version)
    state["rubric_context"] = rubric_ctx
    logger.info("[preprocess] rubric hits=%s judgePanel=%s", len(rubric_ctx), _judge_models())
    _mark_node(
        state,
        "preprocess",
        {
            "rubricHits": rubric_ctx,
            "judgePanel": _judge_models(),
        },
    )
    return state


def _dimension_fallback(_dimension: str, model_id: str) -> dict:
    return {
        "modelId": model_id,
        "winner": "tie",
        "scoreA": 7.0,
        "scoreB": 7.0,
        "confidence": 0.5,
        "reason": f"{model_id} 默认回退结果",
        "evidenceA": [""],
        "evidenceB": [""],
    }


def _run_panel_judge(dimension: str, state: ReviewState, model_id: str, ctx: Dict) -> dict:
    req = state["request"]
    essay = req.input.essayText
    output_a = req.outputs["modelA"].content
    output_b = req.outputs["modelB"].content

    prompt = build_dimension_prompt(dimension, essay, output_a, output_b, ctx, model_id)
    llm = LLMService.create(model_id)
    logger.info(
        "[panel] start dimension=%s model=%s essayLen=%s leftLen=%s rightLen=%s ctxKeys=%s",
        dimension,
        model_id,
        len(essay or ""),
        len(output_a or ""),
        len(output_b or ""),
        list(ctx.keys()) if isinstance(ctx, dict) else type(ctx).__name__,
    )
    try:
        result = llm.invoke_json(
            prompt,
            _dimension_fallback(dimension, model_id),
            build_dimension_system_prompt(dimension, model_id),
        )
        result["modelId"] = model_id
        logger.info(
            "[panel] done dimension=%s model=%s winner=%s scoreA=%s scoreB=%s confidence=%s",
            dimension,
            model_id,
            result.get("winner"),
            result.get("scoreA"),
            result.get("scoreB"),
            result.get("confidence"),
        )
        return result
    except Exception as ex:
        fb = _dimension_fallback(dimension, model_id)
        fb["reason"] = f"{model_id} 评审异常回退: {ex}"
        fb["modelId"] = model_id
        logger.exception("[panel] error dimension=%s model=%s", dimension, model_id)
        return fb


def _summarize_dimension(dimension: str, panel_results: List[dict]) -> dict:
    winner_votes = Counter(r.get("winner", "tie") for r in panel_results)
    score_a = round(sum(float(r.get("scoreA", 7.0)) for r in panel_results) / max(len(panel_results), 1), 2)
    score_b = round(sum(float(r.get("scoreB", 7.0)) for r in panel_results) / max(len(panel_results), 1), 2)
    confidence = round(
        sum(float(r.get("confidence", 0.5)) for r in panel_results) / max(len(panel_results), 1),
        4,
    )

    winner = "tie"
    if winner_votes.get("A", 0) > winner_votes.get("B", 0) and winner_votes.get("A", 0) > winner_votes.get("tie", 0):
        winner = "A"
    elif winner_votes.get("B", 0) > winner_votes.get("A", 0) and winner_votes.get("B", 0) > winner_votes.get("tie", 0):
        winner = "B"

    lead_result = max(panel_results, key=lambda item: float(item.get("confidence", 0.0))) if panel_results else {}
    logger.info(
        "[dimension] summary dimension=%s panelCount=%s consensus=%s winner=%s scoreA=%s scoreB=%s confidence=%s",
        dimension,
        len(panel_results),
        dict(winner_votes),
        winner,
        score_a,
        score_b,
        confidence,
    )
    return {
        "dimension": dimension,
        "winner": winner,
        "scoreA": score_a,
        "scoreB": score_b,
        "confidence": confidence,
        "reason": lead_result.get("reason", "评审团汇总结果"),
        "evidenceA": lead_result.get("evidenceA", []),
        "evidenceB": lead_result.get("evidenceB", []),
        "panelResults": panel_results,
        "panelConsensus": dict(winner_votes),
    }


def _run_dimension_one(dimension: str, state: ReviewState) -> dict:
    models = _judge_models()
    dimension_contexts = state.get("dimension_context") or {}
    ctx = dimension_contexts.get(dimension) or {}

    with ThreadPoolExecutor(max_workers=len(models)) as executor:
        panel_results = list(executor.map(lambda model_id: _run_panel_judge(dimension, state, model_id, ctx), models))

    summary = _summarize_dimension(dimension, panel_results)
    summary["retrieval"] = ctx
    return summary


def _dimension_eval_parallel(state: ReviewState) -> ReviewState:
    req = state["request"]
    dims = req.rubricConfig.dimensions or DIMENSIONS
    query_text = _build_dimension_query(req)
    logger.info("[dimension_eval] start battleId=%s dims=%s", req.battleId, dims)
    # Retrieval可能失败（向量库/embedding不可用等），此处做容错，避免整单失败
    try:
        dimension_context = {dimension: retrieval.get_dimension_context(dimension, query_text) for dimension in dims}
        logger.info("[dimension_eval] retrieval ok dims=%s", list(dimension_context.keys()))
    except Exception as ex:
        logger.exception("[dimension_eval] retrieval error battleId=%s", req.battleId)
        dimension_context = {dimension: {"error": str(ex)} for dimension in dims}
    state["dimension_context"] = dimension_context

    with ThreadPoolExecutor(max_workers=5) as executor:
        try:
            results = list(executor.map(lambda d: _run_dimension_one(d, state), dims))
        except Exception as ex:
            # 兜底：至少返回空结果，让aggregate走fallback
            logger.exception("[dimension_eval] parallel error battleId=%s", req.battleId)
            _mark_node(state, "dimension_eval_parallel_error", {"error": str(ex)})
            results = []
    state["dimension_results"] = results

    retrieval_used = {
        r["dimension"]: {
            "exemplarCount": len(r.get("retrieval", {}).get("exemplars", [])),
            "goldCaseCount": len(r.get("retrieval", {}).get("gold_cases", [])),
            "riskCount": len(r.get("retrieval", {}).get("risk_patterns", [])),
            "judgeModels": [item.get("modelId", "") for item in r.get("panelResults", [])],
        }
        for r in results
    }
    dimension_summaries = [
        {
            "dimension": r["dimension"],
            "winner": r["winner"],
            "scoreA": r["scoreA"],
            "scoreB": r["scoreB"],
            "confidence": r["confidence"],
            "panelConsensus": r.get("panelConsensus", {}),
        }
        for r in results
    ]
    logger.info("[dimension_eval] done battleId=%s resultCount=%s", req.battleId, len(results))
    _mark_node(
        state,
        "dimension_eval_parallel",
        {
            "retrievalUsed": retrieval_used,
            "dimensionSummaries": dimension_summaries,
        },
    )
    return state


def _aggregate_fallback(results: List[dict]) -> dict:
    wins_a = sum(1 for r in results if r.get("winner") == "A")
    wins_b = sum(1 for r in results if r.get("winner") == "B")
    winner = "tie"
    if wins_a > wins_b:
        winner = "A"
    elif wins_b > wins_a:
        winner = "B"
    confidence = round(
        sum(float(r.get("confidence", 0.5)) for r in results) / max(len(results), 1),
        4,
    )
    return {
        "winner": winner,
        "confidence": confidence,
        "needsHuman": confidence < settings.default_confidence_threshold,
        "summary": "基于评审团多数票的默认汇总结果",
        "panelConsensus": "medium",
    }


def _aggregate(state: ReviewState) -> ReviewState:
    results = state.get("dimension_results", [])
    aggregate_model = settings.aggregate_model or settings.llm_model
    logger.info("[aggregate] start battleId=%s resultCount=%s model=%s", state["request"].battleId, len(results), aggregate_model)
    prompt = build_aggregate_prompt(
        results,
        [
            {
                "dimension": r.get("dimension"),
                "winner": r.get("winner"),
                "confidence": r.get("confidence"),
                "panelConsensus": r.get("panelConsensus"),
            }
            for r in results
        ],
    )
    llm = LLMService.create(aggregate_model)
    try:
        final = llm.invoke_json(
            prompt,
            _aggregate_fallback(results),
            build_aggregate_system_prompt(aggregate_model),
        )
    except Exception as ex:
        logger.exception("[aggregate] llm error battleId=%s", state["request"].battleId)
        final = _aggregate_fallback(results)
        final["summary"] = f"aggregate fallback due to error: {ex}"

    final_confidence = float(final.get("confidence", 0.5))
    final.setdefault("needsHuman", final_confidence < settings.default_confidence_threshold)
    state["final"] = final
    logger.info(
        "[aggregate] done battleId=%s winner=%s confidence=%s needsHuman=%s summary=%s",
        state["request"].battleId,
        final.get("winner"),
        final.get("confidence"),
        final.get("needsHuman"),
        final.get("summary"),
    )
    _mark_node(state, "aggregate", {**final, "aggregateModel": aggregate_model})
    return state


def build_graph():
    graph = StateGraph(ReviewState)
    graph.add_node("preprocess", _preprocess)
    graph.add_node("dimension_eval_parallel", _dimension_eval_parallel)
    graph.add_node("aggregate", _aggregate)

    graph.add_edge(START, "preprocess")
    graph.add_edge("preprocess", "dimension_eval_parallel")
    graph.add_edge("dimension_eval_parallel", "aggregate")
    graph.add_edge("aggregate", END)

    return graph.compile()


compiled_graph = build_graph()


def run_review(request: ReviewJobRequest) -> ReviewResult:
    started = perf_counter()
    job_id = f"rev_{request.battleId}_{uuid.uuid4().hex[:8]}"
    trace_id = f"trace_{uuid.uuid4().hex[:10]}"

    logger.info(
        "[run_review] start jobId=%s battleId=%s modelA=%s modelB=%s essayTitleLen=%s essayTextLen=%s",
        job_id,
        request.battleId,
        request.outputs["modelA"].modelId,
        request.outputs["modelB"].modelId,
        len(request.taskMeta.essayTitle or ""),
        len(request.input.essayText or ""),
    )

    state: ReviewState = {
        "request": request,
        "job_id": job_id,
        "trace_id": trace_id,
        "started_at": started,
        "node_outputs": {},
    }

    out = compiled_graph.invoke(state)

    dim_results = []
    retrieval_used: Dict[str, dict] = {}
    for r in out.get("dimension_results", []):
        retrieval_used[r["dimension"]] = r.get("retrieval", {})
        payload = {k: v for k, v in r.items() if k not in {"retrieval", "panelResults", "panelConsensus"}}
        dim_results.append(DimensionResult(**payload))

    final = out.get("final", {"winner": "tie", "confidence": 0.5, "needsHuman": True})

    latency_ms = int((perf_counter() - started) * 1000)
    cost = CostInfo(
        promptTokens=0,
        completionTokens=0,
        estimatedCny=0.0,
        latencyMs=latency_ms,
    )

    logger.info(
        "[run_review] done jobId=%s battleId=%s winner=%s confidence=%s needsHuman=%s latencyMs=%s dims=%s",
        job_id,
        request.battleId,
        final.get("winner"),
        final.get("confidence"),
        final.get("needsHuman"),
        latency_ms,
        len(dim_results),
    )

    return ReviewResult(
        jobId=job_id,
        battleId=request.battleId,
        status="completed",
        finalWinner=final["winner"],
        finalConfidence=final["confidence"],
        needsHuman=final["needsHuman"],
        reviewVersion=settings.review_version,
        dimensionResults=dim_results,
        traceId=trace_id,
        cost=cost,
        createdAt=datetime.now(),
        nodeOutputs=out.get("node_outputs", {}),
        retrievalUsed=retrieval_used,
    )
