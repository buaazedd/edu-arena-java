"""LLM 调用封装：OpenAI 兼容 + JSON 输出 + 重试。"""
from __future__ import annotations

import asyncio
import json
from typing import Any, List, Optional

from openai import AsyncOpenAI, OpenAI
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.common.exceptions import LLMInvokeError
from app.common.logger import logger
from app.settings import get_settings


class LLMClient:
    """统一 LLM 客户端：支持 chat/JSON/多模态。"""

    def __init__(
        self,
        *,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        default_model: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        s = get_settings()
        self._api_key = api_key or s.ai_api_key
        self._base_url = base_url or s.ai_base_url
        self._default_model = default_model or s.ai_review_model
        self._timeout = timeout or s.ai_timeout
        self._max_retries = max_retries or s.ai_max_retries

        if not self._api_key:
            logger.warning("LLMClient 初始化时 ai_api_key 为空，实际调用会失败。")

        # 同步/异步客户端
        self._sync = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)
        self._async = AsyncOpenAI(api_key=self._api_key, base_url=self._base_url, timeout=self._timeout)

    # --------- 高阶方法 ---------

    async def achat_json(
        self,
        *,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
        images_base64: Optional[List[str]] = None,
    ) -> dict:
        """异步 chat 调用，要求模型以 JSON 格式输出。"""
        content = self._build_user_content(user, images_base64)
        messages: List[Any] = [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ]

        @retry(
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=0.5, max=6),
            retry=retry_if_exception_type((LLMInvokeError,)),
            reraise=True,
        )
        async def _call():
            try:
                resp = await self._async.chat.completions.create(
                    model=model or self._default_model,
                    messages=messages,
                    temperature=temperature,
                    response_format={"type": "json_object"},
                )
            except Exception as e:
                raise LLMInvokeError(f"LLM 调用失败: {e}", cause=e) from e
            text = (resp.choices[0].message.content or "").strip()
            if not text:
                raise LLMInvokeError("LLM 返回空内容")
            try:
                return json.loads(text)
            except json.JSONDecodeError as e:
                raise LLMInvokeError(f"LLM 返回非 JSON: {text[:200]}", cause=e) from e

        return await _call()

    def chat_json(
        self,
        *,
        system: str,
        user: str,
        model: Optional[str] = None,
        temperature: float = 0.2,
        images_base64: Optional[List[str]] = None,
    ) -> dict:
        """同步版本（给脚本/测试用）。"""
        return asyncio.run(
            self.achat_json(
                system=system,
                user=user,
                model=model,
                temperature=temperature,
                images_base64=images_base64,
            )
        )

    # --------- 内部 ---------

    @staticmethod
    def _build_user_content(text: str, images_base64: Optional[List[str]]) -> Any:
        """构造 OpenAI v1 多模态 content 列表。"""
        if not images_base64:
            return text
        parts: List[dict] = [{"type": "text", "text": text}]
        for b64 in images_base64:
            if not b64:
                continue
            url = b64 if b64.startswith("data:") else f"data:image/jpeg;base64,{b64}"
            parts.append({"type": "image_url", "image_url": {"url": url, "detail": "low"}})
        return parts


_SINGLETON: Optional[LLMClient] = None


def get_llm() -> LLMClient:
    global _SINGLETON
    if _SINGLETON is None:
        _SINGLETON = LLMClient()
    return _SINGLETON
