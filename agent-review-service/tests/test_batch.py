"""batch 离线批量系统测试。"""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.contracts.arena_dto import (
    ArenaBattleVO,
    ArenaVoteRequest,
    ArenaVoteResultVO,
)
from app.contracts.dataset_dto import DatasetItem, ImageSource
from app.contracts.review_dto import ReviewRequest, ReviewResponse, VotePayload
from app.contracts.review_models import DimensionKey, DimensionScore, ReviewReport
from batch.models import BatchJob, StageStatus, stage_rank


# ─────────────── Models & stage_rank ───────────────

class TestStageRank:
    def test_order(self):
        assert stage_rank(StageStatus.PENDING) < stage_rank(StageStatus.CREATED)
        assert stage_rank(StageStatus.CREATED) < stage_rank(StageStatus.GENERATED)
        assert stage_rank(StageStatus.GENERATED) < stage_rank(StageStatus.REVIEWED)
        assert stage_rank(StageStatus.REVIEWED) < stage_rank(StageStatus.VOTED)
        assert stage_rank(StageStatus.VOTED) < stage_rank(StageStatus.DONE)

    def test_failed_rank(self):
        assert stage_rank(StageStatus.FAILED) == -1

    def test_batch_job_defaults(self):
        job = BatchJob(item_id="test-001")
        assert job.stage == StageStatus.PENDING
        assert job.battle_id is None
        assert job.retry_count == 0


# ─────────────── TaskStore (SQLite) ───────────────

class TestSqliteTaskStore:
    @pytest.fixture
    def store(self, tmp_path):
        from batch.task_store import SqliteTaskStore
        return SqliteTaskStore(path=str(tmp_path / "test.sqlite"))

    def test_upsert_and_get(self, store):
        job = BatchJob(item_id="t-001", battle_id=42, stage=StageStatus.CREATED)
        store.upsert(job)

        loaded = store.get("t-001")
        assert loaded is not None
        assert loaded.item_id == "t-001"
        assert loaded.battle_id == 42
        assert loaded.stage == StageStatus.CREATED
        assert loaded.updated_at is not None

    def test_get_nonexistent(self, store):
        assert store.get("not-exist") is None

    def test_upsert_updates_existing(self, store):
        job = BatchJob(item_id="t-002", stage=StageStatus.PENDING)
        store.upsert(job)

        job.stage = StageStatus.CREATED
        job.battle_id = 99
        store.upsert(job)

        loaded = store.get("t-002")
        assert loaded.stage == StageStatus.CREATED
        assert loaded.battle_id == 99

    def test_list_unfinished(self, store):
        store.upsert(BatchJob(item_id="done-1", stage=StageStatus.DONE))
        store.upsert(BatchJob(item_id="failed-1", stage=StageStatus.FAILED))
        store.upsert(BatchJob(item_id="pending-1", stage=StageStatus.PENDING))
        store.upsert(BatchJob(item_id="created-1", stage=StageStatus.CREATED))

        unfinished = store.list_unfinished()
        ids = {j.item_id for j in unfinished}
        assert "pending-1" in ids
        assert "created-1" in ids
        assert "done-1" not in ids
        assert "failed-1" not in ids

    def test_summary(self, store):
        store.upsert(BatchJob(item_id="a", stage=StageStatus.DONE))
        store.upsert(BatchJob(item_id="b", stage=StageStatus.DONE))
        store.upsert(BatchJob(item_id="c", stage=StageStatus.FAILED))

        s = store.summary()
        assert s.get("done") == 2
        assert s.get("failed") == 1

    def test_close(self, store):
        store.upsert(BatchJob(item_id="x", stage=StageStatus.PENDING))
        store.close()
        # 关闭后重新打开应能读取
        from batch.task_store import SqliteTaskStore
        store2 = SqliteTaskStore(path=store.path)
        assert store2.get("x") is not None
        store2.close()


# ─────────────── ImageEncoder ───────────────

class TestImageEncoder:
    @pytest.fixture
    def encoder(self):
        from batch.image_encoder import ImageEncoder
        return ImageEncoder()

    def test_encode_base64_strips_prefix(self, encoder):
        src = ImageSource(kind="base64", data="data:image/png;base64,AAAA")
        result = encoder.encode_one(src)
        assert result == "AAAA"

    def test_encode_base64_no_prefix(self, encoder):
        src = ImageSource(kind="base64", data="QUFBQQ==")
        result = encoder.encode_one(src)
        assert result == "QUFBQQ=="

    def test_encode_base64_empty_data(self, encoder):
        src = ImageSource(kind="base64", data=None)
        assert encoder.encode_one(src) is None

    def test_encode_local_file(self, encoder, tmp_path):
        # 创建测试图片文件
        img_path = tmp_path / "test.jpg"
        # 最小 JPEG（略去真实 JPEG header，用小数据测试）
        img_data = b"\xff\xd8\xff\xe0" + b"\x00" * 50 + b"\xff\xd9"
        img_path.write_bytes(img_data)

        src = ImageSource(kind="local", path=str(img_path))
        result = encoder.encode_one(src)
        assert result is not None
        # 验证是有效的 base64
        base64.b64decode(result)

    def test_encode_local_file_not_exist(self, encoder):
        src = ImageSource(kind="local", path="/nonexistent/file.jpg")
        assert encoder.encode_one(src) is None

    def test_encode_all(self, encoder):
        sources = [
            ImageSource(kind="base64", data="AAAA"),
            ImageSource(kind="base64", data="BBBB"),
            ImageSource(kind="base64", data=None),  # 空的，应被过滤
        ]
        results = encoder.encode_all(sources)
        assert len(results) == 2


# ─────────────── DatasetLoader ───────────────

class TestJsonlDatasetLoader:
    @pytest.fixture
    def jsonl_file(self, tmp_path):
        path = tmp_path / "test.jsonl"
        items = [
            {"item_id": "e-001", "essay_title": "秋游", "images": [{"kind": "base64", "data": "AA"}]},
            {"item_id": "e-002", "essay_title": "春天", "images": [{"kind": "base64", "data": "BB"}]},
        ]
        path.write_text("\n".join(json.dumps(i, ensure_ascii=False) for i in items))
        return path

    def test_load_all(self, jsonl_file):
        from batch.dataset_loader import JsonlDatasetLoader
        loader = JsonlDatasetLoader(jsonl_file)
        items = loader.load_all()
        assert len(items) == 2
        assert items[0].item_id == "e-001"
        assert items[1].essay_title == "春天"

    def test_iter_items(self, jsonl_file):
        from batch.dataset_loader import JsonlDatasetLoader
        loader = JsonlDatasetLoader(jsonl_file)
        items = list(loader.iter_items())
        assert len(items) == 2

    def test_skip_empty_lines(self, tmp_path):
        path = tmp_path / "sparse.jsonl"
        path.write_text(
            '{"item_id":"a","essay_title":"test","images":[{"kind":"base64","data":"X"}]}\n'
            "\n"
            "# comment\n"
            '{"item_id":"b","essay_title":"test2","images":[{"kind":"base64","data":"Y"}]}\n'
        )
        from batch.dataset_loader import JsonlDatasetLoader
        loader = JsonlDatasetLoader(path)
        assert len(loader.load_all()) == 2

    def test_strict_mode_raises(self, tmp_path):
        path = tmp_path / "bad.jsonl"
        path.write_text("not json\n")
        from batch.dataset_loader import JsonlDatasetLoader
        from app.common.exceptions import DataValidationError
        loader = JsonlDatasetLoader(path, strict=True)
        with pytest.raises(DataValidationError):
            loader.load_all()

    def test_lenient_mode_skips(self, tmp_path):
        path = tmp_path / "mixed.jsonl"
        path.write_text(
            'bad line\n'
            '{"item_id":"ok","essay_title":"t","images":[]}\n'
        )
        from batch.dataset_loader import JsonlDatasetLoader
        loader = JsonlDatasetLoader(path, strict=False)
        items = loader.load_all()
        assert len(items) == 1
        assert items[0].item_id == "ok"

    def test_nonexistent_file_raises(self, tmp_path):
        from batch.dataset_loader import JsonlDatasetLoader
        from app.common.exceptions import DataValidationError
        with pytest.raises(DataValidationError, match="不存在"):
            JsonlDatasetLoader(tmp_path / "no.jsonl")


# ─────────────── VoteBuilder ───────────────

class TestVoteBuilder:
    def test_vote_payload_to_request(self):
        from batch.vote_builder import vote_payload_to_request

        payload = VotePayload(
            dim_theme="left", dim_theme_reason="A主旨好",
            dim_imagination="right", dim_imagination_reason="B更有创意",
            dim_logic="tie", dim_logic_reason="差不多",
            dim_language="left",
            dim_writing="tie",
            dim_overall="left", dim_overall_reason="A整体更优",
        )
        req = vote_payload_to_request(payload)
        assert isinstance(req, ArenaVoteRequest)
        assert req.dim_theme == "left"
        assert req.dim_imagination == "right"
        assert req.dim_overall == "left"
        assert req.dim_theme_reason == "A主旨好"
        assert req.dim_language_reason is None  # 空字符串被 `or None` 处理

    def test_vote_payload_empty_reasons(self):
        from batch.vote_builder import vote_payload_to_request
        payload = VotePayload(
            dim_theme="tie", dim_imagination="tie", dim_logic="tie",
            dim_language="tie", dim_writing="tie", dim_overall="tie",
        )
        req = vote_payload_to_request(payload)
        assert req.dim_theme == "tie"
        assert req.dim_theme_reason is None


# ─────────────── ArenaClient (mock HTTP) ───────────────

class TestArenaClient:
    @pytest.fixture
    def mock_arena(self):
        """创建 ArenaClient 但 mock 掉底层 HTTP。"""
        from batch.arena_client import ArenaClient
        client = ArenaClient(base_url="http://test:5001", username="u", password="p")
        return client

    async def test_login(self, mock_arena):
        """登录应正确提取 token。"""
        mock_arena._request = AsyncMock(return_value={
            "code": 200,
            "message": "ok",
            "data": {"token": "jwt-abc", "role": "admin", "user_id": 1, "display_name": "Test"},
        })
        token = await mock_arena.login()
        assert token == "jwt-abc"
        assert mock_arena._token == "jwt-abc"

    async def test_create_battle(self, mock_arena):
        mock_arena._token = "jwt"
        mock_arena._request = AsyncMock(return_value={"code": 200, "data": 42})
        from app.contracts.arena_dto import ArenaCreateBattleRequest
        req = ArenaCreateBattleRequest(essay_title="test", images=["AA"])
        bid = await mock_arena.create_battle(req)
        assert bid == 42

    async def test_generate(self, mock_arena):
        mock_arena._token = "jwt"
        mock_arena._request = AsyncMock(return_value={
            "code": 200,
            "data": {
                "battle_id": 42, "status": "ready", "essay_title": "test",
                "response_left": "left resp", "response_right": "right resp",
            },
        })
        vo = await mock_arena.generate(42)
        assert vo.status == "ready"
        assert vo.response_left == "left resp"

    async def test_get_battle(self, mock_arena):
        mock_arena._token = "jwt"
        mock_arena._request = AsyncMock(return_value={
            "code": 200,
            "data": {
                "battle_id": 42, "status": "voted", "essay_title": "test",
                "winner": "left",
            },
        })
        vo = await mock_arena.get_battle(42)
        assert vo.battle_id == 42
        assert vo.winner == "left"

    async def test_vote(self, mock_arena):
        mock_arena._token = "jwt"
        mock_arena._request = AsyncMock(return_value={
            "code": 200,
            "data": {
                "message": "ok", "overall_winner": "A", "a_wins": 4, "b_wins": 2,
                "winner_side": "left", "winner_label": "模型A",
                "left_model_slot": "A", "right_model_slot": "B",
                "elo_a_before": 1500.0, "elo_a_after": 1516.0,
                "elo_b_before": 1500.0, "elo_b_after": 1484.0,
            },
        })
        req = ArenaVoteRequest(
            dim_theme="left", dim_imagination="right", dim_logic="tie",
            dim_language="left", dim_writing="tie", dim_overall="left",
        )
        vo = await mock_arena.vote(42, req)
        assert vo.winner_side == "left"

    async def test_business_error(self, mock_arena):
        from app.common.exceptions import ArenaApiError
        mock_arena._token = "jwt"
        mock_arena._request = AsyncMock(return_value={
            "code": 400, "message": "参数错误", "data": None,
        })
        with pytest.raises(ArenaApiError, match="参数错误"):
            from app.contracts.arena_dto import ArenaCreateBattleRequest
            await mock_arena.create_battle(
                ArenaCreateBattleRequest(essay_title="t", images=["A"])
            )


# ─────────────── Orchestrator ───────────────

class TestBatchOrchestrator:
    def _make_review_response(self, winner="A"):
        scores = [
            DimensionScore(dim=d, score_a=4, score_b=3, winner=winner, reason="ok", confidence=0.8)
            for d in DimensionKey
        ]
        report = ReviewReport(
            battle_id=42, dimensions=scores,
            final_winner=winner, overall_confidence=0.8,
        )
        side = "left" if winner == "A" else ("right" if winner == "B" else "tie")
        payload = VotePayload(
            dim_theme=side, dim_imagination=side, dim_logic=side,
            dim_language=side, dim_writing=side, dim_overall=side,
        )
        return ReviewResponse(report=report, vote_payload=payload)

    @pytest.fixture
    def setup(self, tmp_path):
        """构造 mock 组件的 orchestrator。"""
        from batch.orchestrator import BatchOrchestrator
        from batch.dataset_loader import JsonlDatasetLoader
        from batch.task_store import SqliteTaskStore

        # 写测试清单
        jsonl = tmp_path / "test.jsonl"
        jsonl.write_text(json.dumps({
            "item_id": "test-001",
            "essay_title": "测试",
            "images": [{"kind": "base64", "data": "AAAA"}],
        }))

        dataset = JsonlDatasetLoader(jsonl)
        store = SqliteTaskStore(path=str(tmp_path / "tasks.sqlite"))

        # Mock arena / review
        arena = MagicMock()
        arena.login = AsyncMock(return_value="jwt")
        arena.create_battle = AsyncMock(return_value=42)
        arena.generate = AsyncMock(return_value=ArenaBattleVO(
            battle_id=42, status="ready", essay_title="测试",
            response_left="left resp" * 20, response_right="right resp" * 20,
        ))
        arena.get_battle = AsyncMock(return_value=ArenaBattleVO(
            battle_id=42, status="ready", essay_title="测试",
            response_left="left resp" * 20, response_right="right resp" * 20,
        ))
        arena.vote = AsyncMock(return_value=ArenaVoteResultVO(
            message="ok", overall_winner="A", a_wins=4, b_wins=2,
            winner_side="left", winner_label="A",
            left_model_slot="A", right_model_slot="B",
            elo_a_before=1500, elo_a_after=1516,
            elo_b_before=1500, elo_b_after=1484,
        ))
        arena.close = AsyncMock()

        review = MagicMock()
        review.review = AsyncMock(return_value=self._make_review_response())
        review.close = AsyncMock()

        orch = BatchOrchestrator(
            dataset=dataset,
            arena=arena,
            review=review,
            store=store,
            concurrency=1,
        )
        return orch, store, arena, review

    async def test_full_pipeline(self, setup):
        """单条完整流水线：create → generate → review → vote → done。"""
        orch, store, arena, review = setup
        jobs = await orch.run()

        assert len(jobs) == 1
        job = jobs[0]
        assert job.stage == StageStatus.DONE
        assert job.battle_id == 42
        assert job.review_winner == "A"

        arena.create_battle.assert_called_once()
        arena.generate.assert_called_once()
        review.review.assert_called_once()
        arena.vote.assert_called_once()

        await orch.close()

    async def test_dry_run_skips_vote(self, setup):
        """dry_run=True 时应跳过投票。"""
        orch, store, arena, review = setup
        orch.dry_run = True

        jobs = await orch.run()
        assert jobs[0].stage == StageStatus.DONE
        arena.vote.assert_not_called()
        await orch.close()

    async def test_resume_from_created(self, setup):
        """断点续跑：从 CREATED 阶段恢复。"""
        orch, store, arena, review = setup

        # 预设任务已到 CREATED
        store.upsert(BatchJob(item_id="test-001", battle_id=42, stage=StageStatus.CREATED))

        jobs = await orch.run()
        assert jobs[0].stage == StageStatus.DONE
        # 不应再次创建对战
        arena.create_battle.assert_not_called()
        await orch.close()

    async def test_error_marks_failed(self, setup):
        """执行失败时应标记为 FAILED。"""
        orch, store, arena, review = setup
        arena.create_battle = AsyncMock(side_effect=Exception("网络错误"))

        jobs = await orch.run()
        assert jobs[0].stage == StageStatus.FAILED
        assert jobs[0].last_error is not None
        assert jobs[0].retry_count == 1
        await orch.close()

    async def test_already_done_skips(self, setup):
        """已完成的任务应直接跳过。"""
        orch, store, arena, review = setup
        store.upsert(BatchJob(item_id="test-001", stage=StageStatus.DONE, battle_id=42))

        jobs = await orch.run()
        assert jobs[0].stage == StageStatus.DONE
        arena.create_battle.assert_not_called()
        arena.generate.assert_not_called()
        review.review.assert_not_called()
        arena.vote.assert_not_called()
        await orch.close()
