"""自定义异常体系。"""
from __future__ import annotations


class ReviewServiceError(Exception):
    """本服务的基异常。"""

    code: int = 500

    def __init__(self, message: str, *, code: int | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code
        self.cause = cause

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.message}


class DataValidationError(ReviewServiceError):
    """输入数据校验失败。"""

    code = 400


class LLMInvokeError(ReviewServiceError):
    """LLM 调用异常（网络/超时/空响应/JSON 解析失败）。"""

    code = 502


class RagError(ReviewServiceError):
    """RAG 检索异常。"""

    code = 503


class ArenaApiError(ReviewServiceError):
    """调用 Java 对战平台接口失败。"""

    code = 502

    def __init__(self, message: str, *, http_status: int | None = None, body: str | None = None):
        super().__init__(message)
        self.http_status = http_status
        self.body = body


class ReviewGraphError(ReviewServiceError):
    """LangGraph 工作流执行失败。"""

    code = 500
