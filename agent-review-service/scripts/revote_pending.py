"""对 Java 侧 status=ready 但未 voted 的 battle 做补救：
    get_battle -> 本地 /api/review -> arena.vote

用法：
    python -m scripts.revote_pending \
        --pending data/reconcile_all100_pending.jsonl \
        --dataset data/dataset_all.jsonl \
        --review-timeout 900 \
        --concurrency 1

说明：
- 不涉及 create_battle / generate，依赖 Java 侧已有 response_left/right
- review_client 的 timeout 可通过 --review-timeout 放大，避开 300s ReadTimeout
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List

from app.common.logger import logger
from app.contracts.dataset_dto import DatasetItem
from app.contracts.review_dto import ReviewRequest
from batch.arena_client import ArenaClient
from batch.review_client import ReviewClient
from batch.vote_builder import vote_payload_to_request


def load_dataset_index(path: Path) -> Dict[str, DatasetItem]:
    idx: Dict[str, DatasetItem] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = DatasetItem.model_validate(json.loads(line))
        idx[item.item_id] = item
    return idx


def load_pending(path: Path) -> List[dict]:
    return [
        json.loads(l)
        for l in path.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]


async def process_one(
    entry: dict,
    dataset_idx: Dict[str, DatasetItem],
    arena: ArenaClient,
    review: ReviewClient,
) -> dict:
    t0 = time.perf_counter()
    battle_id = entry["battle_id"]
    item_id = entry.get("item_id", "<unknown>")
    item = dataset_idx.get(item_id)

    # 1) 拉回 battle 最新状态
    vo = await arena.get_battle(battle_id)
    if vo.status == "voted":
        return {"item_id": item_id, "battle_id": battle_id, "skip": "already_voted"}
    if vo.status != "ready":
        return {
            "item_id": item_id,
            "battle_id": battle_id,
            "skip": f"status={vo.status}",
        }
    if not (vo.response_left and vo.response_right):
        return {
            "item_id": item_id,
            "battle_id": battle_id,
            "error": "missing response_left/right",
        }

    # 2) 构造 ReviewRequest（优先用 dataset 中的题干/要求，fallback 到 battle 的）
    essay_title = (item.essay_title if item else vo.essay_title)
    essay_content = (item.essay_content if item else vo.essay_content)
    grade_level = (item.grade_level if item else vo.grade_level) or "初中"
    requirements = (item.requirements if item else vo.requirements)
    metadata = item.metadata if item else {}

    rr = ReviewRequest(
        battle_id=battle_id,
        essay_title=essay_title,
        response_a=vo.response_left,
        response_b=vo.response_right,
        essay_content=essay_content,
        grade_level=grade_level,
        requirements=requirements,
        metadata=metadata,
    )
    resp = await review.review(rr)

    # 3) vote
    arena_req = vote_payload_to_request(resp.vote_payload)
    try:
        result = await arena.vote(battle_id, arena_req)
        winner_side = result.winner_side
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        if "已投票" in msg or "409" in msg or "duplicate" in msg.lower():
            logger.info(f"[revote/{item_id}] 幂等，视为成功")
            winner_side = "tie"  # 占位
        else:
            raise

    cost_ms = int((time.perf_counter() - t0) * 1000)
    logger.info(
        f"[revote/{item_id}] DONE battle={battle_id} winner={resp.report.final_winner} "
        f"side={winner_side} cost={cost_ms}ms"
    )
    return {
        "item_id": item_id,
        "battle_id": battle_id,
        "review_winner": resp.report.final_winner,
        "vote_winner_side": winner_side,
        "latency_ms": cost_ms,
    }


async def main_async(
    pending_path: Path,
    dataset_path: Path,
    out_path: Path,
    review_timeout: float,
    concurrency: int,
) -> None:
    pending = load_pending(pending_path)
    dataset_idx = load_dataset_index(dataset_path)
    logger.info(
        f"[revote] 待补投 {len(pending)} 条; dataset 中找到 "
        f"{sum(1 for p in pending if p.get('item_id') in dataset_idx)} 条 item"
    )

    arena = ArenaClient()
    review = ReviewClient(timeout=review_timeout)
    sem = asyncio.Semaphore(concurrency)

    async def worker(entry: dict) -> dict:
        async with sem:
            try:
                return await process_one(entry, dataset_idx, arena, review)
            except Exception as e:  # noqa: BLE001
                logger.exception(
                    f"[revote/{entry.get('item_id')}] 失败: {e}"
                )
                return {
                    "item_id": entry.get("item_id"),
                    "battle_id": entry["battle_id"],
                    "error": str(e)[:300],
                }

    results = []
    for entry in pending:
        results.append(await worker(entry))  # 串行执行 or 按 concurrency

    await review.close()
    await arena.close()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    ok = sum(1 for r in results if r.get("vote_winner_side"))
    err = sum(1 for r in results if r.get("error"))
    skip = sum(1 for r in results if r.get("skip"))
    logger.info(f"[revote] 汇总 ok={ok} error={err} skip={skip}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pending", default="data/reconcile_all100_pending.jsonl")
    ap.add_argument("--dataset", default="data/dataset_all.jsonl")
    ap.add_argument("--out", default="data/revote_results.jsonl")
    ap.add_argument("--review-timeout", type=float, default=900.0)
    ap.add_argument("--concurrency", type=int, default=1)
    args = ap.parse_args()
    asyncio.run(
        main_async(
            Path(args.pending),
            Path(args.dataset),
            Path(args.out),
            args.review_timeout,
            args.concurrency,
        )
    )


if __name__ == "__main__":
    main()
