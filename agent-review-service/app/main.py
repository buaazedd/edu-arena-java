from __future__ import annotations

import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException

from app.config import settings
from app.graph import compiled_graph, run_review
from app.job_store import job_store
from app.models import (
    RagSearchHit,
    RagSearchRequest,
    RagUpsertRequest,
    ReviewJobRequest,
    ReviewJobResponse,
    ReviewJobStatusResponse,
    ReviewResult,
    ReviewStatus,
)
from app.retrieval import RetrievalService


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("app.graph").setLevel(logging.INFO)
logging.getLogger("app.retrieval").setLevel(logging.INFO)
logging.getLogger("app.llm").setLevel(logging.INFO)

app = FastAPI(title=settings.service_name, version="0.1.0")
executor = ThreadPoolExecutor(max_workers=4)
retrieval = RetrievalService()


def _run_and_store(job_id: str, payload: ReviewJobRequest):
    try:
        result = run_review(payload)
        result.jobId = job_id
        job_store.mark_completed(result)
    except Exception as ex:
        job_store.mark_failed(job_id, str(ex))


@app.get("/health")
def health():
    return {"status": "ok", "service": settings.service_name}


@app.get("/graph/ascii")
def graph_ascii():
    # 便于快速可视化节点结构
    return {"graph": compiled_graph.get_graph().draw_ascii()}


@app.post("/rag/upsert")
def rag_upsert(payload: RagUpsertRequest):
    count = retrieval.upsert_documents(payload.index, [d.model_dump() for d in payload.documents])
    return {"index": payload.index, "upserted": count}


@app.post("/rag/search", response_model=list[RagSearchHit])
def rag_search(payload: RagSearchRequest):
    return retrieval.search(payload.index, payload.query, payload.topK, payload.where)


@app.post("/review/jobs", response_model=ReviewJobResponse)
def create_review_job(payload: ReviewJobRequest):
    job_id = f"rev_{payload.battleId}_{uuid.uuid4().hex[:8]}"
    job_store.create_job(job_id, payload)
    executor.submit(_run_and_store, job_id, payload)
    return ReviewJobResponse(jobId=job_id, battleId=payload.battleId, status=ReviewStatus.QUEUED)


@app.get("/review/jobs/{job_id}", response_model=ReviewJobStatusResponse)
def get_review_job_status(job_id: str):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="job_not_found")

    result = job_store.get_result(job_id)
    battle_id = result.battleId if result else -1
    error = job_store.get_error(job_id)

    return ReviewJobStatusResponse(jobId=job_id, battleId=battle_id, status=status, error=error)


@app.get("/review/jobs/{job_id}/result", response_model=ReviewResult)
def get_review_job_result(job_id: str):
    status = job_store.get_status(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="job_not_found")
    if status != ReviewStatus.COMPLETED:
        raise HTTPException(status_code=409, detail=f"job_not_completed:{status}")

    result = job_store.get_result(job_id)
    if not result:
        raise HTTPException(status_code=500, detail="result_missing")
    return result


@app.post("/review/run", response_model=ReviewResult)
def run_review_sync(payload: ReviewJobRequest):
    try:
        return run_review(payload)
    except Exception as ex:
        raise HTTPException(status_code=500, detail=f"review_failed: {ex}")
