"""LLMClient 测试：mock OpenAI SDK 验证 JSON 解析/错误处理/多模态。"""
from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.common.exceptions import LLMInvokeError
from app.review.llm import LLMClient


def _mock_response(content: str):
    """构造 OpenAI SDK 格式的 mock 响应。"""
    message = MagicMock()
    message.content = content
    choice = MagicMock()
    choice.message = message
    resp = MagicMock()
    resp.choices = [choice]
    return resp


class TestLLMClient:
    """LLMClient 单元测试。"""

    @pytest.fixture
    def client(self):
        return LLMClient(
            api_key="test-key",
            base_url="http://localhost:0/v1",
            default_model="test",
            timeout=5,
            max_retries=1,
        )

    async def test_achat_json_success(self, client):
        """正常 JSON 返回解析正确。"""
        expected = {"score_a": 4.0, "score_b": 3.0, "winner": "A"}
        mock_resp = _mock_response(json.dumps(expected))

        client._async = MagicMock()
        client._async.chat.completions.create = AsyncMock(return_value=mock_resp)

        result = await client.achat_json(system="test", user="test")
        assert result == expected

    async def test_achat_json_empty_response(self, client):
        """空内容应抛 LLMInvokeError。"""
        mock_resp = _mock_response("")
        client._async = MagicMock()
        client._async.chat.completions.create = AsyncMock(return_value=mock_resp)

        with pytest.raises(LLMInvokeError, match="空内容"):
            await client.achat_json(system="test", user="test")

    async def test_achat_json_invalid_json(self, client):
        """非 JSON 内容应抛 LLMInvokeError。"""
        mock_resp = _mock_response("这不是 JSON")
        client._async = MagicMock()
        client._async.chat.completions.create = AsyncMock(return_value=mock_resp)

        with pytest.raises(LLMInvokeError, match="非 JSON"):
            await client.achat_json(system="test", user="test")

    async def test_achat_json_api_error(self, client):
        """SDK 异常应包装为 LLMInvokeError。"""
        client._async = MagicMock()
        client._async.chat.completions.create = AsyncMock(
            side_effect=Exception("connection refused")
        )

        with pytest.raises(LLMInvokeError, match="调用失败"):
            await client.achat_json(system="test", user="test")

    def test_build_user_content_text_only(self, client):
        """无图片时返回纯文本。"""
        result = LLMClient._build_user_content("你好", None)
        assert result == "你好"

    def test_build_user_content_with_images(self, client):
        """有图片时返回多模态内容列表。"""
        result = LLMClient._build_user_content("你好", ["AAAA"])
        assert isinstance(result, list)
        assert result[0] == {"type": "text", "text": "你好"}
        assert result[1]["type"] == "image_url"
        # 自动添加 data:image 前缀
        assert result[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_build_user_content_with_data_prefix(self, client):
        """已有 data: 前缀的图片不再重复添加。"""
        img = "data:image/png;base64,AAAA"
        result = LLMClient._build_user_content("text", [img])
        assert result[1]["image_url"]["url"] == img

    def test_build_user_content_empty_images(self, client):
        """空图片列表等同于纯文本。"""
        result = LLMClient._build_user_content("text", [])
        assert result == "text"

    def test_build_user_content_skip_empty_b64(self, client):
        """空 base64 字符串应跳过。"""
        result = LLMClient._build_user_content("text", ["", "AAAA"])
        assert len(result) == 2  # text + 1 image

    async def test_achat_json_with_custom_model(self, client):
        """指定自定义 model 应传递给 SDK。"""
        expected = {"ok": True}
        mock_resp = _mock_response(json.dumps(expected))

        client._async = MagicMock()
        create_mock = AsyncMock(return_value=mock_resp)
        client._async.chat.completions.create = create_mock

        await client.achat_json(system="s", user="u", model="custom-model")
        _, kwargs = create_mock.call_args
        assert kwargs["model"] == "custom-model"

    async def test_achat_json_json_mode(self, client):
        """应传递 response_format=json_object。"""
        expected = {"ok": True}
        mock_resp = _mock_response(json.dumps(expected))

        client._async = MagicMock()
        create_mock = AsyncMock(return_value=mock_resp)
        client._async.chat.completions.create = create_mock

        await client.achat_json(system="s", user="u")
        _, kwargs = create_mock.call_args
        assert kwargs["response_format"] == {"type": "json_object"}
