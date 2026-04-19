from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.arena_dto import ArenaCreateBattleRequest


@dataclass
class JsonWritingSample:
    sample_id: str
    essay_title: str
    essay_content: str | None
    grade_level: str = "高中"
    requirements: str = "请从主旨、想象、逻辑、语言、书写五个维度综合评价。"
    image_paths: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "JsonWritingSample":
        return cls(
            sample_id=str(data["sample_id"]),
            essay_title=str(data.get("essay_title", "作文评测")),
            essay_content=data.get("essay_content"),
            grade_level=str(data.get("grade_level", "高中")),
            requirements=str(data.get("requirements", "请从主旨、想象、逻辑、语言、书写五个维度综合评价。")),
            image_paths=[str(p) for p in data.get("image_paths", [])],
        )


def load_samples_from_json(json_file: str) -> list[JsonWritingSample]:
    p = Path(json_file)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"JSON root must be list, got: {type(raw)}")
    return [JsonWritingSample.from_dict(item) for item in raw]


def _read_image_base64(image_path: str, base_dir: Path | None = None) -> str:
    p = Path(image_path)
    if not p.is_absolute() and base_dir is not None:
        p = (base_dir / p).resolve()
    if not p.exists():
        raise FileNotFoundError(f"image not found: {p}")
    return base64.b64encode(p.read_bytes()).decode("utf-8")


def to_create_battle_request(sample: JsonWritingSample, json_file: str | None = None) -> ArenaCreateBattleRequest:
    base_dir = Path(json_file).resolve().parent if json_file else None
    images_b64: list[str] = []
    for ip in sample.image_paths:
        images_b64.append(_read_image_base64(ip, base_dir=base_dir))

    essay_content = (sample.essay_content or "").strip()
    # 平台端有“内容至少10字”校验：纯图片场景下提供占位文本
    if len(essay_content) < 10:
        essay_content = "作文正文见上传图片，请结合图片内容评阅。"

    return ArenaCreateBattleRequest(
        essay_title=sample.essay_title,
        essay_content=essay_content,
        grade_level=sample.grade_level,
        requirements=sample.requirements,
        images=images_b64,
    )
