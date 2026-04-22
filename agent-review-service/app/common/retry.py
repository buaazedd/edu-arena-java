"""基于 tenacity 的统一重试工具。

策略：
- 指数退避 base=0.5s, max=8s
- 仅对"可重试异常"重试；4xx 这类业务错误直接抛出
"""
from __future__ import annotations

from typing import Callable

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from .exceptions import ArenaApiError, LLMInvokeError


def _is_retryable(exc: BaseException) -> bool:
    """判断异常是否可重试。"""
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.ReadError, httpx.RemoteProtocolError)):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return 500 <= exc.response.status_code < 600
    if isinstance(exc, ArenaApiError):
        return exc.http_status is not None and 500 <= exc.http_status < 600
    if isinstance(exc, LLMInvokeError):
        return True
    return False


def retry_http(max_attempts: int = 3) -> Callable:
    """同步函数的 http 重试装饰器。"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    )


async def aretry_http(func: Callable, *args, max_attempts: int = 3, **kwargs):
    """异步函数的 http 重试（显式调用）。"""
    async for attempt in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=0.5, max=8),
        retry=retry_if_exception(_is_retryable),
        reraise=True,
    ):
        with attempt:
            return await func(*args, **kwargs)
    raise RetryError("unreachable")  # pragma: no cover


__all__ = ["retry_http", "aretry_http"]
