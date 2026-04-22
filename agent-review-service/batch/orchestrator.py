"""批量编排：并发 + 断点续跑 + 阶段化重试。

每条 DatasetItem 的处理阶段：
    pending → created → generated → reviewed → voted → done

幂等策略：
- created 阶段：若 TaskStore 已有 battle_id，则直接跳过创建。
- generated 阶段：若对战已是 ready/voted 状态，直接跳过 generate。
- voted 阶段：Java 端 UNIQUE(battle_id,user_id) 约束；若 409/"已投票" 视为成功。
"""
from __future__ import annotations

import asyncio
import time
from typing import List, Optional

from app.common.logger import logger
from app.contracts.arena_dto import ArenaBattleVO, ArenaCreateBattleRequest
from app.contracts.dataset_dto import DatasetItem
from app.contracts.review_dto import ReviewRequest
from app.settings import get_settings

from .arena_client import ArenaClient
from .dataset_loader import DatasetLoader
from .image_encoder import ImageEncoder
from .models import BatchJob, StageStatus, stage_rank
from .review_client import ReviewClient
from .task_store import SqliteTaskStore, TaskStore
from .vote_builder import vote_payload_to_request


class BatchOrchestrator:
    def __init__(
        self,
        dataset: DatasetLoader,
        *,
        arena: Optional[ArenaClient] = None,
        review: Optional[ReviewClient] = None,
        store: Optional[TaskStore] = None,
        concurrency: Optional[int] = None,
        dry_run: bool = False,
    ) -> None:
        s = get_settings()
        self.dataset = dataset
        self.arena = arena or ArenaClient()
        self.review = review or ReviewClient()
        self.store: TaskStore = store or SqliteTaskStore()
        self.sem = asyncio.Semaphore(concurrency or s.batch_concurrency)
        self.image_encoder = ImageEncoder()
        self.dry_run = dry_run

    async def close(self) -> None:
        for c in (self.arena, self.review):
            try:
                await c.close()
            except Exception:  # pragma: no cover
                pass
        if hasattr(self.store, "close"):
            try:
                self.store.close()  # type: ignore[attr-defined]
            except Exception:
                pass

    # ------------------- 单条流程 -------------------

    async def _poll_until_ready(
        self, battle_id: int, timeout: int = 180, interval: float = 2.0
    ) -> ArenaBattleVO:
        """轮询直到 status != 'generating'。"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            vo = await self.arena.get_battle(battle_id)
            if vo.status != "generating":
                return vo
            await asyncio.sleep(interval)
        raise TimeoutError(f"battle {battle_id} 生成超时 (>{timeout}s)")

    async def _process_one(self, item: DatasetItem) -> BatchJob:
        job = self.store.get(item.item_id) or BatchJob(item_id=item.item_id)

        if job.stage == StageStatus.DONE:
            logger.info(f"[batch/{item.item_id}] 已完成，跳过")
            return job

        t0 = time.perf_counter()

        # ---- 1. CREATE ----
        if stage_rank(job.stage) < stage_rank(StageStatus.CREATED):
            if not item.has_images():
                raise ValueError(f"[{item.item_id}] 图片必传（Java 端要求）")
            images_b64 = self.image_encoder.encode_all(item.images)
            if not images_b64:
                raise ValueError(f"[{item.item_id}] 没有可用图片")
            req = ArenaCreateBattleRequest(
                essay_title=item.essay_title,
                images=images_b64,
                essay_content=item.essay_content,
                grade_level=item.grade_level or "初中",
                requirements=item.requirements,
            )
            battle_id = await self.arena.create_battle(req)
            job.battle_id = battle_id
            job.stage = StageStatus.CREATED
            self.store.upsert(job)

        assert job.battle_id is not None, "battle_id 应已生成"

        # ---- 2. GENERATE ----
        vo: ArenaBattleVO
        if stage_rank(job.stage) < stage_rank(StageStatus.GENERATED):
            try:
                vo = await self.arena.generate(job.battle_id)
            except Exception as e:
                logger.warning(f"[batch/{item.item_id}] generate 调用失败 {e}，改用轮询")
                vo = await self._poll_until_ready(job.battle_id)
            if vo.status == "generating":
                vo = await self._poll_until_ready(job.battle_id)
            if vo.status == "failed":
                raise RuntimeError(f"battle {job.battle_id} 生成失败")
            job.stage = StageStatus.GENERATED
            self.store.upsert(job)
        else:
            vo = await self.arena.get_battle(job.battle_id)

        # ---- 3. REVIEW ----
        if stage_rank(job.stage) < stage_rank(StageStatus.REVIEWED):
            if not (vo.response_left and vo.response_right):
                raise RuntimeError(f"battle {job.battle_id} 缺少 response_left/right")
            rr = ReviewRequest(
                battle_id=job.battle_id,
                essay_title=item.essay_title,
                response_a=vo.response_left,
                response_b=vo.response_right,
                essay_content=item.essay_content,
                grade_level=item.grade_level or "初中",
                requirements=item.requirements,
                metadata=item.metadata,
            )
            resp = await self.review.review(rr)
            job.review_winner = resp.report.final_winner
            job.stage = StageStatus.REVIEWED
            self.store.upsert(job)
            vote_payload = resp.vote_payload
        else:
            logger.info(f"[batch/{item.item_id}] 已评审过，跳过（dry_run 视为无事）")
            vote_payload = None  # type: ignore[assignment]

        # ---- 4. VOTE ----
        if self.dry_run:
            logger.info(f"[batch/{item.item_id}] dry_run=True，跳过投票")
            job.stage = StageStatus.DONE
        elif stage_rank(job.stage) < stage_rank(StageStatus.VOTED):
            if vote_payload is None:
                # 续跑场景：重新跑一次评审获取 payload
                rr = ReviewRequest(
                    battle_id=job.battle_id,
                    essay_title=item.essay_title,
                    response_a=vo.response_left or "",
                    response_b=vo.response_right or "",
                    essay_content=item.essay_content,
                    grade_level=item.grade_level or "初中",
                    requirements=item.requirements,
                    metadata=item.metadata,
                )
                vote_payload = (await self.review.review(rr)).vote_payload
            arena_req = vote_payload_to_request(vote_payload)
            try:
                result = await self.arena.vote(job.battle_id, arena_req)
                job.vote_winner_side = result.winner_side
            except Exception as e:
                msg = str(e)
                if "已投票" in msg or "409" in msg or "duplicate" in msg.lower():
                    logger.info(f"[batch/{item.item_id}] 已投票，视为成功")
                else:
                    raise
            job.stage = StageStatus.VOTED
            self.store.upsert(job)

        # ---- 5. DONE ----
        job.stage = StageStatus.DONE
        job.latency_ms = int((time.perf_counter() - t0) * 1000)
        job.last_error = None
        self.store.upsert(job)
        logger.info(
            f"[batch/{item.item_id}] DONE battle_id={job.battle_id} "
            f"winner={job.review_winner} cost={job.latency_ms}ms"
        )
        return job

    async def _process_one_safe(self, item: DatasetItem) -> BatchJob:
        async with self.sem:
            try:
                return await self._process_one(item)
            except Exception as e:
                logger.exception(f"[batch/{item.item_id}] 失败: {e}")
                job = self.store.get(item.item_id) or BatchJob(item_id=item.item_id)
                job.retry_count += 1
                job.last_error = str(e)[:500]
                job.stage = StageStatus.FAILED
                self.store.upsert(job)
                return job

    # ------------------- 对外 -------------------

    async def run(self) -> List[BatchJob]:
        items = list(self.dataset.iter_items())
        logger.info(f"[batch] 载入 {len(items)} 条任务，并发={self.sem._value}")
        tasks = [self._process_one_safe(it) for it in items]
        results = await asyncio.gather(*tasks)
        self._print_summary(results)
        return results

    def _print_summary(self, jobs: List[BatchJob]) -> None:
        total = len(jobs)
        done = sum(1 for j in jobs if j.stage == StageStatus.DONE)
        failed = sum(1 for j in jobs if j.stage == StageStatus.FAILED)
        winners = {"A": 0, "B": 0, "tie": 0}
        for j in jobs:
            if j.review_winner in winners:
                winners[j.review_winner] += 1
        logger.info(
            f"[batch] summary total={total} done={done} failed={failed} "
            f"A={winners['A']} B={winners['B']} tie={winners['tie']}"
        )


__all__ = ["BatchOrchestrator"]
