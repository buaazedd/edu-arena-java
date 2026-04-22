"""FastAPI 应用入口。

启动方式：
    uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
或：
    python -m app.main
"""
from __future__ import annotations

import time
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import admin_router, review_router
from app.common.exceptions import ReviewServiceError
from app.common.logger import init_logger, logger
from app.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    init_logger(level=settings.log_level, log_dir=settings.log_dir)

    app = FastAPI(
        title="agent-review-service",
        description="Multi-Agent 作文批改评审服务（LangGraph + RAG + Skill）",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---- 中间件：访问日志 ----
    @app.middleware("http")
    async def access_log(request: Request, call_next):
        t0 = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed = int((time.perf_counter() - t0) * 1000)
            logger.exception(
                f"[http] {request.method} {request.url.path} -> EXCEPTION cost={elapsed}ms"
            )
            raise
        elapsed = int((time.perf_counter() - t0) * 1000)
        logger.info(
            f"[http] {request.method} {request.url.path} -> {response.status_code} cost={elapsed}ms"
        )
        return response

    # ---- 全局异常处理 ----
    @app.exception_handler(ReviewServiceError)
    async def _on_service_error(_: Request, exc: ReviewServiceError) -> JSONResponse:
        payload: Dict[str, Any] = {"code": exc.code, "message": exc.message, "data": None}
        return JSONResponse(status_code=exc.code if 400 <= exc.code < 600 else 500, content=payload)

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"code": 422, "message": "请求参数校验失败", "data": exc.errors()},
        )

    # ---- 路由 ----
    app.include_router(review_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    @app.get("/", tags=["meta"])
    async def root() -> Dict[str, Any]:
        return {
            "service": "agent-review-service",
            "version": "0.1.0",
            "docs": "/docs",
            "review_port": settings.review_port,
        }

    logger.info(
        f"[startup] agent-review-service ready on {settings.review_host}:{settings.review_port}"
    )
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn  # type: ignore

    s = get_settings()
    uvicorn.run(
        "app.main:app",
        host=s.review_host,
        port=s.review_port,
        reload=False,
        log_level=s.log_level.lower(),
    )
