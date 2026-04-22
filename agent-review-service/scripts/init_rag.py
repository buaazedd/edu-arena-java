"""从 app/rag/seed/ 把初始知识导入 ChromaDB 三个集合。

使用：
    python -m scripts.init_rag           # 追加导入
    python -m scripts.init_rag --reset   # 先清空再导入
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.common.logger import init_logger, logger
from app.rag.store import ChromaStore
from app.settings import get_settings

SEED_DIR = Path(__file__).resolve().parent.parent / "app" / "rag" / "seed"


def _split_rubric(md_text: str) -> list[tuple[str, dict]]:
    """把 rubric.md 按二级标题拆成每段一个文档。"""
    docs: list[tuple[str, dict]] = []
    blocks = md_text.split("\n## ")
    for idx, block in enumerate(blocks):
        text = block if idx == 0 else "## " + block
        text = text.strip()
        if not text or len(text) < 20:
            continue
        title_line = text.splitlines()[0].strip("# ").strip()
        docs.append((text, {"title": title_line}))
    return docs


def _load_jsonl(path: Path) -> list[tuple[str, dict]]:
    docs: list[tuple[str, dict]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        content = rec.pop("content", None) or rec.pop("overall_reason", None) or json.dumps(rec, ensure_ascii=False)
        docs.append((content, rec))
    return docs


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset", action="store_true", help="导入前清空集合")
    args = parser.parse_args()

    s = get_settings()
    init_logger(level=s.log_level, log_dir=s.log_dir)
    store = ChromaStore()

    if args.reset:
        try:
            store.reset()
        except Exception as e:
            logger.warning(f"reset skipped: {e}")

    # rubric
    rubric = _split_rubric((SEED_DIR / "rubric.md").read_text(encoding="utf-8"))
    store.add_documents("rubric", [d for d, _ in rubric], [m for _, m in rubric])

    # exemplar
    exemplar = _load_jsonl(SEED_DIR / "exemplar.jsonl")
    store.add_documents("exemplar", [d for d, _ in exemplar], [m for _, m in exemplar])

    # gold_case
    gold = _load_jsonl(SEED_DIR / "gold_case.jsonl")
    store.add_documents("gold_case", [d for d, _ in gold], [m for _, m in gold])

    for name in ("rubric", "exemplar", "gold_case"):
        logger.info(f"  {name} count = {store.count(name)}")


if __name__ == "__main__":
    main()
