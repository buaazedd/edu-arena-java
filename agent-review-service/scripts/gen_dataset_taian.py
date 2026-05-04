#!/usr/bin/env python3
"""为「泰安市高二年级期末考试」批量评审生成 JSONL 清单。

目录约定：
    agent-review-service/picture/泰安市高二年级期末考试/
        ├─ 张三-201330123-正面.jpg
        ├─ 张三-201330123-背面.jpg
        ├─ 李四-201330124-正面.jpg
        ├─ 李四-201330124-背面.jpg
        └─ ...

本脚本按「学号」聚合正面+背面两张为一条 DatasetItem：
    item_id = "essay-<学号>"
    images  = 正面 + 背面（按顺序）
    essay_title = 固定作文题（英雄与选择）
    grade_level = "高中"

用法：
    cd agent-review-service
    python scripts/gen_dataset_taian.py \
        --pictures picture/泰安市高二年级期末考试 \
        --output data/dataset_taian_hero.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# ────────────────────────────────────────────────────────────────
# 固定作文题目（英雄与选择）
# ────────────────────────────────────────────────────────────────
ESSAY_TITLE = (
    "阅读下面的材料，根据要求写作。"
    "有人说，英雄是历史长河中闪耀的名字，是少数人的光辉；"
    "也有人说，英雄并不遥远，在平凡生活中，每一个人都可能在关键时刻做出选择，"
    "承担责任，从而成就不平凡的人生。"
    "在现实生活中，我们常常面临各种抉择："
    "有的选择关乎个人得失，有的选择关乎他人利益，有的甚至关乎国家与社会的发展。"
    "不同的选择，往往会塑造不同的人生，也会影响一个人的价值与意义。"
    "请结合材料，联系实际，谈谈你对“选择与英雄”的理解。"
    "写作要求：选准角度，自拟标题 ；明确文体（诗歌除外） ；不少于800字 ；"
    "不得套作，不得抄袭。"
)

# 匹配形如 "张三-201330123-正面.jpg" / "张三-201330123-背面.jpg"
_FNAME_RE = re.compile(r"^(?P<name>.+?)-(?P<sid>\d{6,})-(?P<side>正面|背面)\.(?P<ext>jpg|jpeg|png)$", re.IGNORECASE)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="gen_dataset_taian")
    parser.add_argument("--pictures", "-p", required=True, help="图片目录")
    parser.add_argument("--output", "-o", default="data/dataset_taian_hero.jsonl")
    parser.add_argument("--grade", default="高中")
    parser.add_argument("--limit", type=int, default=0, help="仅生成前 N 条（0 = 不限制）")
    args = parser.parse_args(argv)

    pic_dir = Path(args.pictures).expanduser().resolve()
    if not pic_dir.is_dir():
        print(f"❌ 图片目录不存在: {pic_dir}", file=sys.stderr)
        return 1

    out_path = Path(args.output).expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 按学号聚合 {sid: {"name": 张三, "front": path, "back": path}}
    groups: dict[str, dict] = defaultdict(dict)
    skipped_downloading = 0
    skipped_unmatched = 0

    for fp in sorted(pic_dir.iterdir()):
        if not fp.is_file():
            continue
        # 跳过百度云未下载完的占位文件
        if ".downloading" in fp.name:
            skipped_downloading += 1
            continue
        m = _FNAME_RE.match(fp.name)
        if not m:
            skipped_unmatched += 1
            continue
        sid = m.group("sid")
        side = m.group("side")
        groups[sid].setdefault("name", m.group("name"))
        groups[sid]["front" if side == "正面" else "back"] = fp

    # 组装 DatasetItem
    items: list[dict] = []
    only_front = only_back = both = 0
    for sid in sorted(groups):
        g = groups[sid]
        images = []
        if "front" in g:
            images.append({"kind": "local", "path": str(g["front"])})
        if "back" in g:
            images.append({"kind": "local", "path": str(g["back"])})

        if not images:
            continue
        if "front" in g and "back" in g:
            both += 1
        elif "front" in g:
            only_front += 1
        else:
            only_back += 1

        items.append({
            "item_id": f"essay-{sid}",
            "essay_title": ESSAY_TITLE,
            "images": images,
            "essay_content": None,
            "grade_level": args.grade,
            "requirements": None,
            "metadata": {
                "source": "taian-gaoer-qimo",
                "student_name": g.get("name", ""),
                "student_id": sid,
            },
        })

    if args.limit and args.limit > 0:
        items = items[: args.limit]

    with out_path.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    print(f"📂 图片目录: {pic_dir}")
    print(f"📝 输出清单: {out_path}")
    print(f"✅ 生成 {len(items)} 条")
    print(f"   跳过 .downloading: {skipped_downloading}")
    print(f"   跳过命名不符: {skipped_unmatched}")
    print(f"   正背面齐全: {both}  仅正面: {only_front}  仅背面: {only_back}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
