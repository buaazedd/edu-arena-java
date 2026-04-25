"""向 Java arena 拉回 results_all100.jsonl 中每条 battle 的真实状态。

只读对账，用来定位"本地标 done、Java 未投票"的 battle。

用法：
    python -m scripts.reconcile_battles \
        --results data/results_all100.jsonl \
        --out data/reconcile_all100.jsonl
"""
from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from pathlib import Path
from typing import List, Optional

from app.common.logger import logger
from batch.arena_client import ArenaClient


async def fetch_one(arena: ArenaClient, battle_id: int) -> dict:
    try:
        vo = await arena.get_battle(battle_id)
        return {
            "battle_id": battle_id,
            "ok": True,
            "status": vo.status,
            "winner": vo.winner,
            "has_left": bool(vo.response_left),
            "has_right": bool(vo.response_right),
        }
    except Exception as e:  # noqa: BLE001
        return {"battle_id": battle_id, "ok": False, "error": str(e)[:200]}


async def main_async(results_path: Path, out_path: Path, concurrency: int) -> None:
    rows = [json.loads(l) for l in results_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    items: List[dict] = [
        {"item_id": r["item_id"], "battle_id": r.get("battle_id"), "local_stage": r.get("stage")}
        for r in rows
        if r.get("battle_id")
    ]
    logger.info(f"[reconcile] 待对账 {len(items)} 条 battle")

    arena = ArenaClient()
    sem = asyncio.Semaphore(concurrency)

    async def worker(entry: dict) -> dict:
        async with sem:
            info = await fetch_one(arena, entry["battle_id"])
            return {**entry, **info}

    records = await asyncio.gather(*(worker(e) for e in items))
    await arena.close()

    # 写明细
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # 汇总
    status_cnt = Counter(r.get("status") for r in records if r.get("ok"))
    err_cnt = sum(1 for r in records if not r.get("ok"))
    logger.info(f"[reconcile] 完成，错误 {err_cnt} 条")
    logger.info(f"[reconcile] Java 侧 status 分布: {dict(status_cnt)}")

    # 把 pending（状态为 ready，即生成完但未投票）的单独列出来
    pending = [r for r in records if r.get("status") == "ready"]
    logger.info(f"[reconcile] pending(需补投) = {len(pending)} 条")
    if pending:
        ids = sorted(r["battle_id"] for r in pending)
        logger.info(f"[reconcile] pending battle_ids = {ids}")

    # 输出一个纯 pending 列表文件，供补投脚本消费
    pending_path = out_path.with_name(out_path.stem + "_pending.jsonl")
    with pending_path.open("w", encoding="utf-8") as f:
        for r in pending:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    logger.info(f"[reconcile] pending 清单写入 {pending_path}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="data/results_all100.jsonl")
    ap.add_argument("--out", default="data/reconcile_all100.jsonl")
    ap.add_argument("--concurrency", type=int, default=4)
    args = ap.parse_args()
    asyncio.run(main_async(Path(args.results), Path(args.out), args.concurrency))


if __name__ == "__main__":
    main()
