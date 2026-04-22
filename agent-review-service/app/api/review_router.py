"""评审 HTTP 路由：/api/review 与 /api/health。"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, status

from app.common.logger import logger
from app.contracts.review_dto import ReviewRequest, ReviewResponse
from app.review import get_service
from app.settings import get_settings

router = APIRouter(tags=["review"])


@router.get("/health")
async def health() -> Dict[str, Any]:
    """健康检查：返回基础环境信息，不触发 LLM/RAG 调用。"""
    s = get_settings()
    return {
        "status": "ok",
        "service": "agent-review-service",
        "review_port": s.review_port,
        "review_model": s.ai_review_model,
        "arbitrator_model": s.ai_arbitrator_model,
        "chroma_dir": str(s.chroma_path),
    }


@router.post(
    "/review",
    response_model=ReviewResponse,
    response_model_exclude_none=False,
    status_code=status.HTTP_200_OK,
    summary="对一场对战的两份批改执行 multi-agent 评审",
)
async def review(req: ReviewRequest) -> ReviewResponse:
    """评审接口：输入 battle 上下文与两份批改，返回结构化报告 + 投票载荷。"""
    if not req.response_a or not req.response_b:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="response_a/response_b 不能为空",
        )
    try:
        service = get_service()
        resp = await service.arun(req)
        return resp
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"[api/review] 失败 battle_id={req.battle_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"评审失败: {e}",
        ) from e
