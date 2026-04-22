"""离线清单条目模型。

JSONL 清单每行一个 `DatasetItem`：
```json
{
  "item_id": "essay-001",
  "essay_title": "记一次秋游",
  "images": [
    {"kind": "local", "path": "./data/images/essay-001/page1.jpg"},
    {"kind": "local", "path": "./data/images/essay-001/page2.jpg"}
  ],
  "essay_content": "可选的 OCR 转写或已有正文",
  "grade_level": "初中",
  "requirements": "可选批改要求",
  "metadata": {"source": "dataset-v2"}
}
```
"""
from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class ImageSource(BaseModel):
    """图片来源：本地路径 / URL / 预编码 base64。"""

    model_config = ConfigDict(extra="ignore")

    kind: Literal["local", "url", "base64"] = "local"
    path: Optional[str] = Field(default=None, description="当 kind=local 或 url 时使用")
    data: Optional[str] = Field(default=None, description="当 kind=base64 时为纯 base64（不带 data: 前缀）")


class DatasetItem(BaseModel):
    """离线清单单条记录。"""

    model_config = ConfigDict(extra="ignore")

    item_id: str = Field(description="业务唯一 ID，用于断点续跑幂等去重")
    essay_title: str
    images: List[ImageSource] = Field(default_factory=list)
    essay_content: Optional[str] = None
    grade_level: Optional[str] = "初中"
    requirements: Optional[str] = None
    metadata: dict = Field(default_factory=dict)

    def has_images(self) -> bool:
        return len(self.images) > 0
