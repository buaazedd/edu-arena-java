from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from app.runner_config import runner_settings


@dataclass
class WritingSample:
    sample_id: str
    source_file: str
    essay_title: str
    essay_content: str
    image_paths: list[str] = field(default_factory=list)
    grade_level: str = "高中"
    requirements: str = "请从主旨、想象、逻辑、语言、书写五个维度综合评价。"

    @property
    def task_key(self) -> str:
        raw = f"{self.sample_id}|{self.essay_title}|{runner_settings.prompt_version}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()


def _parse_line(line: str) -> WritingSample | None:
    line = line.strip()
    if not line:
        return None

    # 每行格式：0001.jpg <作文题目/材料> s1 s2 s3 s4 s5 total <评语>
    m = re.match(r"^(\d{4})\.jpg\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$", line)
    if not m:
        return None

    sample_id = m.group(1)
    essay_title = m.group(2).strip()  # 从文件名到打分之间全部作为作文题目

    return WritingSample(
        sample_id=sample_id,
        source_file=f"{sample_id}.jpg",
        essay_title=essay_title,
        essay_content="",  # 正文在图片中，文本可为空
        image_paths=[f"../writing/chinese/{sample_id}.jpg"],
        grade_level="初中",
        requirements="请结合作文图片内容，从主旨、想象、逻辑、语言、书写五个维度综合评价。",
    )


def load_writing_samples(limit: int | None = None) -> list[WritingSample]:
    file_path = Path(runner_settings.writing_dir) / runner_settings.writing_file
    lines = file_path.read_text(encoding="utf-8").splitlines()

    samples: list[WritingSample] = []
    for line in lines:
        sample = _parse_line(line)
        if not sample:
            continue
        samples.append(sample)
        if limit and len(samples) >= limit:
            break

    return samples
