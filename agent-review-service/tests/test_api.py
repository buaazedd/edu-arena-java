"""FastAPI 路由集成测试：TestClient + mock service。"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.contracts.review_dto import ReviewResponse, VotePayload
from app.contracts.review_models import DimensionKey, DimensionScore, ReviewReport


def _make_review_response(battle_id: int = 42) -> ReviewResponse:
    scores = [
        DimensionScore(dim=d, score_a=4, score_b=3, winner="A", reason="ok", confidence=0.8)
        for d in DimensionKey
    ]
    report = ReviewReport(
        battle_id=battle_id, dimensions=scores,
        final_winner="A", overall_confidence=0.8,
    )
    payload = VotePayload(
        dim_theme="left", dim_imagination="left", dim_logic="tie",
        dim_language="left", dim_writing="tie", dim_overall="left",
    )
    return ReviewResponse(report=report, vote_payload=payload, latency_ms=123)


@pytest.fixture
def client(monkeypatch):
    """创建 TestClient，mock 掉 ReviewService。"""
    mock_service = MagicMock()
    mock_service.arun = AsyncMock(return_value=_make_review_response())

    # 清除 lru_cache
    import app.review.graph as graph_mod
    import app.review.service as svc_mod
    graph_mod.get_graph.cache_clear()
    svc_mod.get_service.cache_clear()

    # 通过 sys.modules 获取实际的 review_router 模块（不是 APIRouter 对象）
    # 先确保模块被加载
    import app.api.review_router
    review_router_mod = sys.modules["app.api.review_router"]

    # monkeypatch 模块中的 get_service 函数
    monkeypatch.setattr(review_router_mod, "get_service", lambda: mock_service)

    from app.main import create_app
    app = create_app()

    from fastapi.testclient import TestClient
    tc = TestClient(app)

    yield tc, mock_service

    graph_mod.get_graph.cache_clear()
    svc_mod.get_service.cache_clear()


class TestHealthEndpoint:
    def test_health_ok(self, client):
        tc, _ = client
        resp = tc.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "agent-review-service"

    def test_root(self, client):
        tc, _ = client
        resp = tc.get("/")
        assert resp.status_code == 200
        assert resp.json()["service"] == "agent-review-service"


class TestReviewEndpoint:
    def test_review_success(self, client):
        tc, mock_svc = client
        req = {
            "battle_id": 42,
            "essay_title": "测试",
            "response_a": "批改A内容",
            "response_b": "批改B内容",
        }
        resp = tc.post("/api/review", json=req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["report"]["battle_id"] == 42
        assert data["report"]["final_winner"] == "A"
        assert data["vote_payload"]["dim_overall"] == "left"

    def test_review_empty_response_a(self, client):
        tc, _ = client
        req = {
            "battle_id": 42,
            "essay_title": "测试",
            "response_a": "",
            "response_b": "内容",
        }
        resp = tc.post("/api/review", json=req)
        assert resp.status_code == 400

    def test_review_empty_response_b(self, client):
        tc, _ = client
        req = {
            "battle_id": 42,
            "essay_title": "测试",
            "response_a": "内容",
            "response_b": "",
        }
        resp = tc.post("/api/review", json=req)
        assert resp.status_code == 400

    def test_review_missing_fields(self, client):
        tc, _ = client
        resp = tc.post("/api/review", json={"battle_id": 42})
        assert resp.status_code == 422

    def test_review_service_error(self, client):
        tc, mock_svc = client
        from app.common.exceptions import ReviewGraphError
        mock_svc.arun = AsyncMock(side_effect=ReviewGraphError("工作流崩溃"))
        req = {
            "battle_id": 42,
            "essay_title": "测试",
            "response_a": "A",
            "response_b": "B",
        }
        resp = tc.post("/api/review", json=req)
        assert resp.status_code == 500


class TestAdminRagEndpoints:
    def test_rag_stats(self, client):
        tc, _ = client
        resp = tc.get("/api/rag/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "counts" in data

    def test_rag_upsert(self, client):
        tc, _ = client
        req = {
            "collection": "rubric",
            "documents": ["测试文档1", "测试文档2"],
        }
        resp = tc.post("/api/rag/upsert", json=req)
        assert resp.status_code == 200
        data = resp.json()
        assert data["collection"] == "rubric"
        assert data["upserted"] == 2

    def test_rag_upsert_invalid_collection(self, client):
        tc, _ = client
        req = {"collection": "invalid", "documents": ["test"]}
        resp = tc.post("/api/rag/upsert", json=req)
        assert resp.status_code == 422  # pattern validation

    def test_rag_upsert_empty_docs(self, client):
        tc, _ = client
        req = {"collection": "rubric", "documents": []}
        resp = tc.post("/api/rag/upsert", json=req)
        assert resp.status_code == 400

    def test_rag_seed(self, client):
        tc, _ = client
        resp = tc.post("/api/rag/seed", json={"reset": False})
        assert resp.status_code == 200
        data = resp.json()
        assert "seeded" in data
