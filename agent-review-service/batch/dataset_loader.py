"""JSONL 清单加载器。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator, Protocol

from app.common.exceptions import DataValidationError
from app.common.logger import logger
from app.contracts.dataset_dto import DatasetItem


class DatasetLoader(Protocol):
    def iter_items(self) -> Iterable[DatasetItem]: ...


class JsonlDatasetLoader:
    """JSONL 清单加载器：逐行解析为 DatasetItem。"""

    def __init__(self, path: str | Path, strict: bool = False) -> None:
        self.path = Path(path).expanduser().resolve()
        if not self.path.exists():
            raise DataValidationError(f"清单文件不存在: {self.path}")
        self.strict = strict

    def iter_items(self) -> Iterator[DatasetItem]:
        with self.path.open("r", encoding="utf-8") as f:
            for lineno, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                try:
                    obj = json.loads(line)
                    item = DatasetItem.model_validate(obj)
                except Exception as e:
                    msg = f"第 {lineno} 行解析失败: {e}"
                    if self.strict:
                        raise DataValidationError(msg) from e
                    logger.warning(f"[dataset] {msg} -> 跳过")
                    continue
                yield item

    def load_all(self) -> list[DatasetItem]:
        return list(self.iter_items())


__all__ = ["DatasetLoader", "JsonlDatasetLoader"]
