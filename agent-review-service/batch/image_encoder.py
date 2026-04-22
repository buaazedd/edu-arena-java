"""图片编码器：把多种来源统一为 Java 端所需的纯 base64 字符串列表。

Java `BattleController.create` 要求：
- images 为纯 base64 字符串列表（不带 data:image 前缀）
- 总体积建议 <= 10MB
- 单图若过大，先 Pillow 缩放 + JPEG 压缩
"""
from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import List, Optional

import httpx

from app.common.exceptions import DataValidationError
from app.common.logger import logger
from app.contracts.dataset_dto import ImageSource

# 最长边像素限制（超出则缩放）
_MAX_SIDE = 1600
# 单图目标上限（字节）
_PER_IMAGE_LIMIT = 2 * 1024 * 1024  # 2MB


def _strip_data_url_prefix(s: str) -> str:
    """去掉 `data:image/xxx;base64,` 前缀，仅保留 base64 正文。"""
    if s.startswith("data:") and ";base64," in s:
        return s.split(";base64,", 1)[1]
    return s


def _compress_image(raw: bytes) -> bytes:
    """若图片过大则缩放并转 JPEG 压缩。"""
    try:
        from PIL import Image  # type: ignore
    except ImportError:  # pragma: no cover
        logger.warning("[image_encoder] Pillow 未安装，跳过压缩")
        return raw

    if len(raw) <= _PER_IMAGE_LIMIT:
        return raw

    try:
        img = Image.open(io.BytesIO(raw))
    except Exception as e:
        logger.warning(f"[image_encoder] 图片解析失败，原样返回: {e}")
        return raw

    # 保持比例缩放
    w, h = img.size
    scale = min(1.0, _MAX_SIDE / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")

    buf = io.BytesIO()
    quality = 85
    while True:
        buf.seek(0)
        buf.truncate(0)
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        if buf.tell() <= _PER_IMAGE_LIMIT or quality <= 55:
            break
        quality -= 10
    return buf.getvalue()


def _encode_bytes(raw: bytes) -> str:
    compressed = _compress_image(raw)
    return base64.b64encode(compressed).decode("ascii")


def _load_local(path: str) -> bytes:
    p = Path(path).expanduser()
    if not p.exists():
        raise DataValidationError(f"本地图片不存在: {p}")
    return p.read_bytes()


def _load_url(url: str, timeout: float = 15.0) -> bytes:
    resp = httpx.get(url, timeout=timeout, follow_redirects=True)
    resp.raise_for_status()
    return resp.content


class ImageEncoder:
    """把 ImageSource 列表转为 Java create 接口期望的 base64 列表。"""

    def encode_one(self, src: ImageSource) -> Optional[str]:
        try:
            if src.kind == "base64":
                if not src.data:
                    return None
                return _strip_data_url_prefix(src.data)
            if src.kind == "local":
                if not src.path:
                    return None
                return _encode_bytes(_load_local(src.path))
            if src.kind == "url":
                if not src.path:
                    return None
                return _encode_bytes(_load_url(src.path))
        except Exception as e:
            logger.warning(f"[image_encoder] 编码失败 kind={src.kind}: {e}")
            return None
        return None

    def encode_all(self, sources: list[ImageSource]) -> List[str]:
        out: List[str] = []
        for s in sources:
            enc = self.encode_one(s)
            if enc:
                out.append(enc)
        return out


__all__ = ["ImageEncoder"]
