#!/usr/bin/env python3
"""从 resource/ 下的 txt 描述文件 + picture/ 下的图片，生成批量评审用的 JSONL 清单。

txt 文件格式（每行一条）：
    <图片文件名> <作文题目> <score1> <score2> <score3> <score4> <score5> <total> <评语>

示例：
    0001.jpg 读下面的材料... 8 6 8 8 3 33 这篇作文以...

其中 6 个数字为人工评分（theme, imagination, logic, language, writing, total），
评语为人工批注（写入 metadata.human_comment）。

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

# 维度名称（与 DimensionKey 对齐）
_DIM_NAMES = ["theme", "imagination", "logic", "language", "writing", "total"]


def _parse_line(line: str, picture_dir: Path, grade_level: str) -> dict | None:
    """解析一行 txt，返回 DatasetItem 格式的 dict 或 None（解析失败时）。"""
    line = line.strip()
    if not line or line.startswith("#"):
        return None

    # 1. 提取图片文件名（行首，如 "0001.jpg"）
    parts = line.split(None, 1)
    if len(parts) < 2:
        print(f"  ⚠️  跳过（无法拆分文件名与内容）: {line[:60]}...", file=sys.stderr)
        return None

    image_filename = parts[0]
    rest = parts[1]

    # 2. 用正则找评分位置，把 rest 切分为：题目 | 评分 | 评语
    m = _SCORE_PATTERN.search(rest)
    if not m:
        print(f"  ⚠️  跳过（未找到评分数字）: {image_filename}", file=sys.stderr)
        return None

    essay_title = rest[: m.start()].strip()
    scores_raw = [m.group(i) for i in range(1, 7)]
    comment = rest[m.end():].strip()

    # 3. 解析评分
    scores = {}
    for name, val in zip(_DIM_NAMES, scores_raw):
        try:
            scores[name] = float(val) if "." in val else int(val)
        except ValueError:
            scores[name] = val

    # 4. 从文件名提取 item_id（去掉扩展名）
    item_id = Path(image_filename).stem  # "0001.jpg" → "0001"

    # 5. 确定图片路径（支持 picture_dir 下直接放文件，或按 item_id 子目录放）
    images = []
    direct_path = picture_dir / image_filename
    sub_dir = picture_dir / item_id

    if direct_path.exists():
        # 图片直接在 picture/ 下
        images.append({"kind": "local", "path": str(direct_path)})
    elif sub_dir.is_dir():
        # 图片在 picture/<item_id>/ 子目录下
        for img in sorted(sub_dir.iterdir()):
            if img.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                images.append({"kind": "local", "path": str(img)})
    else:
        # 图片尚未放入，先生成占位路径（用户后续放入即可）
        images.append({"kind": "local", "path": str(direct_path)})
        print(f"  ⚠️  图片不存在（已生成占位路径）: {direct_path}", file=sys.stderr)

    # 6. 截取作文题目（如果太长，取第一句话或前 50 字作为 title）
    title = _extract_title(essay_title)

    # 7. 组装 DatasetItem
    return {
        "item_id": f"essay-{item_id}",
        "essay_title": title,
        "images": images,
        "essay_content": None,
        "grade_level": grade_level,
        "requirements": essay_title if essay_title != title else None,
        "metadata": {
            "source": "txt-import",
            "image_filename": image_filename,
            "human_scores": scores,
            "human_comment": comment if comment else None,
        },
    }


def _extract_title(raw_title: str) -> str:
    """从作文题目文本中提取简短标题。

    策略：
    1. 如果包含书名号《》，取书名号内容
    2. 如果包含引号中的标题关键词，取引号内容
    3. 如果以"以"..."为题"模式，提取题目
    4. 否则取前 50 字
    """
    # 尝试匹配 《xxx》
    m = re.search(r"《(.+?)》", raw_title)
    if m:
        return m.group(1)

    # 尝试匹配 "以"xxx"为题" 或 "以"xxx"为题"
    m = re.search(r'[以][\s]*["\u201c](.+?)["\u201d][\s]*为题', raw_title)
    if m:
        return m.group(1)

    # 尝试匹配 "请以"...为题" 变体
    m = re.search(r'请以\s*"(.+?)"\s*为题', raw_title)
    if m:
        return m.group(1)

    # 尝试匹配"原来，我也很______" 这类半命题
    m = re.search(r'["\u201c](.+?(?:_{2,}|……).+?)["\u201d"]', raw_title)
    if m:
        return m.group(1)

    # 尝试匹配引号内的短标题
    for q_open, q_close in [('\u201c', '\u201d'), ('"', '"'), ('\u300a', '\u300b')]:
        m = re.search(re.escape(q_open) + r'(.{2,30})' + re.escape(q_close), raw_title)
        if m:
            candidate = m.group(1)
            # 排除过长的引文
            if len(candidate) <= 20:
                return candidate

    # 兜底：取前 50 字
    return raw_title[:50] + ("..." if len(raw_title) > 50 else "")


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
                print(f"  ✅  [{lineno}] {item['item_id']} → {item['essay_title']}")
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
