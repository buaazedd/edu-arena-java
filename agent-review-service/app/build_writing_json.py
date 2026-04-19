from __future__ import annotations

import json
import re
from pathlib import Path


def parse_label_line(line: str) -> dict | None:
    line = line.strip()
    if not line:
        return None

    m = re.match(r"^(\d{4})\.jpg\s+(.+?)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s+(.+)$", line)
    if not m:
        return None

    sample_id = m.group(1)
    essay_title = m.group(2).strip()  # 文件名到打分之间全部是作文题目
    scores = [int(m.group(i)) for i in range(3, 9)]
    teacher_comment = m.group(9).strip()

    image_abs_path = str((Path(__file__).resolve().parents[2] / "writing" / "chinese" / f"{sample_id}.jpg").resolve())

    return {
        "sample_id": sample_id,
        "essay_title": essay_title,
        "essay_content": None,
        "grade_level": "初中",
        "requirements": "请结合作文图片内容，从主旨、想象、逻辑、语言、书写五个维度综合评价。",
        "image_paths": [image_abs_path],
        "metadata": {
            "human_scores": {
                "theme": scores[0],
                "imagination": scores[1],
                "logic": scores[2],
                "language": scores[3],
                "writing": scores[4],
                "total": scores[5]
            },
            "teacher_comment": teacher_comment,
            "source": "writing/label_cn.txt"
        }
    }


def build_dataset(label_file: Path, out_file: Path) -> int:
    lines = label_file.read_text(encoding="utf-8").splitlines()
    items = []
    for ln in lines:
        obj = parse_label_line(ln)
        if obj:
            items.append(obj)

    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    return len(items)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    label = root.parent / "writing" / "label_cn.txt"
    out_file = root / "data" / "writing_dataset_all.json"
    n = build_dataset(label, out_file)
    print(f"[OK] built dataset: {out_file} (count={n})")


if __name__ == "__main__":
    main()
