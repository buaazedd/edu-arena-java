#!/usr/bin/env python3
"""从 resource/ 下的 txt 描述文件 + picture/ 下的图片，生成批量评审用的 JSONL 清单。

支持两种行格式（按行自动识别）：

【格式 A：空格分隔，用于中文 label_cn.txt】
    <图片文件名> <作文题目> <score1> <score2> <score3> <score4> <score5> <total> <评语>
    示例：
        0001.jpg 读下面的材料... 8 6 8 8 3 33 这篇作文以...

【格式 B：分号分隔，用于英文 label_en.txt】
    <图片文件名>;<作文题目>;<score1>;<score2>;<score3>;<score4>;<score5>;<total>;<评语>
    示例：
        0001.jpg;假如你是李华...;3;3;3;2;4;15;作文观点明确...

其中 6 个数字为人工评分（theme, imagination, logic, language, writing, total），
评语为人工批注。**这些评分与评语仅用于定位作文题目的右边界，不会写入输出 JSON。**
输出的 essay_title = 图片名与第一个评分数字之间的完整原文（含材料、提示、字数要求等）。

用法：
    # 默认：resource/*.txt + picture/ → data/dataset.jsonl
    python scripts/gen_dataset.py

    # 指定路径
    python scripts/gen_dataset.py \
        --txt  resource/essays.txt \
        --pictures picture/ \
        --output data/dataset.jsonl \
        --grade 初中

    # 多个 txt 文件
    python scripts/gen_dataset.py \
        --txt resource/batch1.txt resource/batch2.txt \
        --pictures picture/ \
        --output data/dataset.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ──────────────────────────────────────────────
# 评分正则：匹配连续 6 个空格分隔的数字（整数或小数），如 "8 6 8 8 3 33"
# 前 5 个是各维度分，第 6 个是总分
# ──────────────────────────────────────────────
_SCORE_PATTERN = re.compile(
    r"\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)\s+"
    r"(\d+(?:\.\d+)?)"
    r"\s+"
)


def _parse_line(line: str, picture_dir: Path, grade_level: str) -> dict | None:
    """解析一行 txt，返回 DatasetItem 格式的 dict 或 None（解析失败时）。

    自动识别两种格式（人工评分与评语在解析时直接丢弃，不写入 JSON）：
      - 分号分隔（英文 label_en.txt）：9 段 = 文件名 + 题目 + 5 分 + 总分 + 评语
      - 空格分隔（中文 label_cn.txt）：题目与评分之间用空格
    """
    line = line.strip().lstrip("\ufeff")  # 去 BOM
    if not line or line.startswith("#"):
        return None

    # ── 格式 B：分号分隔（英文） ──
    # 典型行以 ".jpg;" / ".jpeg;" / ".png;" 开头，且分号段数 ≥ 9
    if ";" in line:
        seg = line.split(";")
        if len(seg) >= 9 and re.match(r".+\.(jpg|jpeg|png|webp|bmp)$", seg[0].strip(), re.I):
            image_filename = seg[0].strip()
            essay_title_raw = seg[1].strip()
            scores_raw = [s.strip() for s in seg[2:8]]
            # 校验评分段都是数字 → 确认命中格式 B（但分数本身丢弃）
            if all(re.fullmatch(r"\d+(?:\.\d+)?", s) for s in scores_raw):
                return _build_item(
                    image_filename=image_filename,
                    essay_title=essay_title_raw,
                    picture_dir=picture_dir,
                    grade_level=grade_level,
                )

    # ── 格式 A：空格分隔（中文） ──
    parts = line.split(None, 1)
    if len(parts) < 2:
        print(f"  ⚠️  跳过（无法拆分文件名与内容）: {line[:60]}...", file=sys.stderr)
        return None

    image_filename = parts[0]
    rest = parts[1]

    # 用正则定位评分起点，题目 = 评分之前的全部内容；评分与评语解析后直接丢弃
    m = _SCORE_PATTERN.search(rest)
    if not m:
        print(f"  ⚠️  跳过（未找到评分数字）: {image_filename}", file=sys.stderr)
        return None

    essay_title = rest[: m.start()].strip()

    return _build_item(
        image_filename=image_filename,
        essay_title=essay_title,
        picture_dir=picture_dir,
        grade_level=grade_level,
    )


def _build_item(
    image_filename: str,
    essay_title: str,
    picture_dir: Path,
    grade_level: str,
) -> dict:
    """把已解析出的原始字段拼装成一条 DatasetItem dict（不含人工评分/评语）。"""
    # 从文件名提取 item_id（去掉扩展名）
    item_id = Path(image_filename).stem  # "0001.jpg" → "0001"

    # 确定图片路径（支持 picture_dir 下直接放文件，或按 item_id 子目录放）
    images = []
    direct_path = picture_dir / image_filename
    sub_dir = picture_dir / item_id

    if direct_path.exists():
        images.append({"kind": "local", "path": str(direct_path)})
    elif sub_dir.is_dir():
        for img in sorted(sub_dir.iterdir()):
            if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                images.append({"kind": "local", "path": str(img)})
    else:
        # 图片尚未放入，先生成占位路径（用户后续放入即可）
        images.append({"kind": "local", "path": str(direct_path)})
        print(f"  ⚠️  图片不存在（已生成占位路径）: {direct_path}", file=sys.stderr)

    # 组装 DatasetItem
    # essay_title 保留「图片名与第一个评分数字之间」的完整原文（含材料、要求等）
    # requirements 统一为 None；不再写入 human_scores / human_comment / metadata
    return {
        "item_id": f"essay-{item_id}",
        "essay_title": essay_title,
        "images": images,
        "essay_content": None,
        "grade_level": grade_level,
        "requirements": None,
    }


def parse_txt_file(
    txt_path: Path,
    picture_dir: Path,
    grade_level: str,
) -> list[dict]:
    """解析整个 txt 文件，返回 DatasetItem dict 列表。"""
    items = []
    with txt_path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            item = _parse_line(line, picture_dir, grade_level)
            if item is not None:
                items.append(item)
                preview = item["essay_title"][:40] + ("…" if len(item["essay_title"]) > 40 else "")
                print(f"  ✅  [{lineno}] {item['item_id']} → {preview}")
    return items


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gen_dataset",
        description="从 resource/*.txt + picture/ 生成批量评审 JSONL 清单",
    )
    parser.add_argument(
        "--txt", "-t",
        nargs="+",
        default=None,
        help="txt 描述文件路径（可多个）。默认自动扫描 resource/*.txt",
    )
    parser.add_argument(
        "--pictures", "-p",
        default="picture",
        help="图片目录路径（默认 picture/）",
    )
    parser.add_argument(
        "--output", "-o",
        default="data/dataset.jsonl",
        help="输出 JSONL 路径（默认 data/dataset.jsonl）",
    )
    parser.add_argument(
        "--grade",
        default="初中",
        help="年级（默认 初中）",
    )
    args = parser.parse_args(argv)

    picture_dir = Path(args.pictures).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve()

    # 确定 txt 文件列表
    if args.txt:
        txt_files = [Path(p).expanduser().resolve() for p in args.txt]
    else:
        resource_dir = Path("resource").resolve()
        if not resource_dir.exists():
            print(f"❌ resource/ 目录不存在: {resource_dir}", file=sys.stderr)
            return 1
        txt_files = sorted(resource_dir.glob("*.txt"))
        if not txt_files:
            print(f"❌ resource/ 下没有 .txt 文件", file=sys.stderr)
            return 1

    print(f"📂 图片目录: {picture_dir}")
    print(f"📄 txt 文件: {[str(f) for f in txt_files]}")
    print(f"📝 输出路径: {output_path}")
    print()

    all_items: list[dict] = []
    for txt_path in txt_files:
        if not txt_path.exists():
            print(f"❌ 文件不存在: {txt_path}", file=sys.stderr)
            continue
        print(f"── 解析 {txt_path.name} ──")
        items = parse_txt_file(txt_path, picture_dir, args.grade)
        all_items.extend(items)
        print(f"   → {len(items)} 条\n")

    if not all_items:
        print("❌ 未解析到任何有效记录", file=sys.stderr)
        return 1

    # 检查 item_id 重复
    seen_ids = set()
    for item in all_items:
        if item["item_id"] in seen_ids:
            print(f"⚠️  重复 item_id: {item['item_id']}", file=sys.stderr)
        seen_ids.add(item["item_id"])

    # 写入 JSONL
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for item in all_items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"✅ 共生成 {len(all_items)} 条记录 → {output_path}")

    # 打印统计
    has_image = sum(1 for it in all_items if any(
        Path(img["path"]).exists() for img in it["images"]
    ))
    print(f"   图片就位: {has_image}/{len(all_items)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
