"""loguru 日志初始化：结构化 + 轮转 + 敏感字段脱敏。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

from loguru import logger

_SENSITIVE_KEYS = ("api_key", "password", "token", "authorization")
_BASE64_PATTERN = re.compile(r"([A-Za-z0-9+/=]{200,})")


def _sanitize(record: dict) -> None:
    """脱敏：token/密码/长 base64 只保留前 12 字符 + 省略号。"""
    msg = record.get("message", "")
    if not isinstance(msg, str):
        return
    # 长 base64（可能是图片）
    msg = _BASE64_PATTERN.sub(lambda m: m.group(1)[:12] + "...<base64len=%d>" % len(m.group(1)), msg)
    # 敏感键
    for key in _SENSITIVE_KEYS:
        msg = re.sub(
            rf"({key}\s*[=:]\s*)(\S+)",
            lambda m: m.group(1) + "***",
            msg,
            flags=re.IGNORECASE,
        )
    record["message"] = msg


_INITIALIZED = False


def init_logger(level: str = "INFO", log_dir: str | Path = "./logs") -> None:
    """全局日志初始化（幂等）。"""
    global _INITIALIZED
    if _INITIALIZED:
        return

    logger.remove()
    # 控制台
    logger.add(
        sys.stderr,
        level=level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
            "<level>{message}</level>"
        ),
        filter=lambda record: _sanitize(record) or True,
    )
    # 文件（按天轮转）
    log_path = Path(log_dir).expanduser()
    log_path.mkdir(parents=True, exist_ok=True)
    logger.add(
        log_path / "review_{time:YYYY-MM-DD}.log",
        level=level,
        rotation="00:00",
        retention="14 days",
        encoding="utf-8",
        enqueue=True,
        filter=lambda record: _sanitize(record) or True,
        format=(
            "{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
    )
    _INITIALIZED = True


__all__ = ["logger", "init_logger"]
