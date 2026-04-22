"""批量离线处理 CLI。

用法：
    python -m batch.cli run --input data/sample_dataset.jsonl --concurrency 3
    python -m batch.cli run --input data/sample_dataset.jsonl --dry-run
    python -m batch.cli status
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from app.common.logger import init_logger, logger
from app.settings import get_settings

from .dataset_loader import JsonlDatasetLoader
from .orchestrator import BatchOrchestrator
from .task_store import SqliteTaskStore


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="batch.cli", description="agent-review batch runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    pr = sub.add_parser("run", help="执行批量处理")
    pr.add_argument("--input", "-i", required=True, help="JSONL 清单文件路径")
    pr.add_argument("--concurrency", "-c", type=int, default=None)
    pr.add_argument("--dry-run", action="store_true", help="只评审不投票")
    pr.add_argument("--store", default=None, help="任务状态 SQLite 文件路径")
    pr.add_argument("--output", "-o", default=None, help="结果 JSONL 输出路径（可选）")

    ps = sub.add_parser("status", help="查看任务状态统计")
    ps.add_argument("--store", default=None)

    return p


async def _cmd_run(args: argparse.Namespace) -> int:
    loader = JsonlDatasetLoader(args.input, strict=False)
    store = SqliteTaskStore(path=args.store) if args.store else None
    orch = BatchOrchestrator(
        dataset=loader,
        store=store,
        concurrency=args.concurrency,
        dry_run=args.dry_run,
    )
    try:
        results = await orch.run()
    finally:
        await orch.close()

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            for j in results:
                f.write(json.dumps(j.model_dump(mode="json"), ensure_ascii=False) + "\n")
        logger.info(f"[cli] 结果写入 {args.output}")

    failed = sum(1 for j in results if j.stage.value == "failed")
    return 1 if failed else 0


def _cmd_status(args: argparse.Namespace) -> int:
    store = SqliteTaskStore(path=args.store) if args.store else SqliteTaskStore()
    summary: dict[str, Any] = store.summary()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    s = get_settings()
    init_logger(level=s.log_level, log_dir=s.log_dir)

    if args.cmd == "run":
        return asyncio.run(_cmd_run(args))
    if args.cmd == "status":
        return _cmd_status(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
