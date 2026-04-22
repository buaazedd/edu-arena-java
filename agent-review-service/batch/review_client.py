"""评审服务 HTTP 客户端：POST /api/review。"""
from __future__ import annotations

from typing import Optional

import httpx

from app.common.exceptions import ReviewServiceError
from app.common.logger import logger
from app.common.retry import aretry_http
from app.contracts.review_dto import ReviewRequest, ReviewResponse
from app.settings import get_settings


class ReviewClient:
    """评审服务异步客户端。"""

    def __init__(self, base_url: Optional[str] = None, timeout: float = 300.0) -> None:
        s = get_settings()
        self.base_url = (base_url or s.review_url).rstrip("/")
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "ReviewClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    async def health(self) -> dict:
        async def _do():
            r = await self._client.get("/api/health")
            r.raise_for_status()
            return r.json()

        return await aretry_http(_do, max_attempts=3)

    async def review(self, req: ReviewRequest) -> ReviewResponse:
        async def _do():
            r = await self._client.post(
                "/api/review", json=req.model_dump(exclude_none=True)
            )
            if r.status_code >= 500:
                raise httpx.HTTPStatusError(str(r.status_code), request=r.request, response=r)
            if r.status_code >= 400:
                raise ReviewServiceError(f"评审服务 HTTP {r.status_code}: {r.text[:300]}")
            return r.json()

        data = await aretry_http(_do, max_attempts=3)
        try:
            return ReviewResponse.model_validate(data)
        except Exception as e:
            logger.exception("[review_client] 响应解析失败")
            raise ReviewServiceError(f"评审响应解析失败: {e}") from e


__all__ = ["ReviewClient"]
