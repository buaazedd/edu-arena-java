from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json


@dataclass
class TestCase:
    sample_id: str
    essay_title: str
    essay_content: Optional[str]
    image_paths: list[str] = field(default_factory=list)
    grade_level: str = "初中"
    requirements: str = "请结合作文图片内容，从主旨、想象、逻辑、语言、书写五个维度综合评价。"



def load_test_cases(json_file: str) -> list[TestCase]:
    p = Path(json_file)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"JSON root must be list, got: {type(raw)}")

    cases: list[TestCase] = []
    for item in raw:
        cases.append(
            TestCase(
                sample_id=str(item["sample_id"]),
                essay_title=str(item.get("essay_title", "作文评测")),
                essay_content=item.get("essay_content"),
                image_paths=[str(x) for x in item.get("image_paths", [])],
                grade_level=str(item.get("grade_level", "初中")),
                requirements=str(item.get("requirements", "请结合作文图片内容，从主旨、想象、逻辑、语言、书写五个维度综合评价。")),
            )
        )
    return cases
