from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, Literal


Lang = Literal["cn", "en"]


@dataclass(frozen=True)
class WritingSample:
    lang: Lang
    image_file: str
    essay_title: str


_CN_SCORE_BLOCK_RE = re.compile(r"\s\d+\s\d+\s\d+\s\d+\s\d+\s\d+\s")


def _parse_cn_line(line: str) -> WritingSample | None:
    line = line.strip()
    if not line:
        return None

    # 0001.jpg <题干...> <若干分数> <评语...>
    parts = line.split(maxsplit=1)
    if len(parts) < 2:
        return None

    image_file, rest = parts[0].strip(), parts[1].strip()
    # 分数块在行尾附近，取“最后一次出现”的分数块作为分隔点，避免作文材料里出现数字干扰
    matches = list(_CN_SCORE_BLOCK_RE.finditer(f" {rest} "))
    m = matches[-1] if matches else None
    essay_title = rest[: m.start()].strip() if m else rest.strip()
    return WritingSample(lang="cn", image_file=image_file, essay_title=essay_title)


def _parse_en_line(line: str) -> WritingSample | None:
    line = line.strip()
    if not line:
        return None

    # 0001.jpg;题干...;...;评语
    parts = [p.strip() for p in line.split(";")]
    if len(parts) < 2:
        return None
    image_file = parts[0]
    essay_title = parts[1]
    return WritingSample(lang="en", image_file=image_file, essay_title=essay_title)


def iter_samples(label_path: Path, lang: Lang) -> Iterator[WritingSample]:
    parser = _parse_cn_line if lang == "cn" else _parse_en_line
    with label_path.open("r", encoding="utf-8") as f:
        for raw in f:
            sample = parser(raw)
            if sample:
                yield sample


def load_all_samples(writing_dir: Path) -> list[WritingSample]:
    samples: list[WritingSample] = []

    cn = writing_dir / "label_cn.txt"
    en = writing_dir / "label_en.txt"

    if cn.exists():
        samples.extend(iter_samples(cn, "cn"))
    if en.exists():
        samples.extend(iter_samples(en, "en"))

    return samples

