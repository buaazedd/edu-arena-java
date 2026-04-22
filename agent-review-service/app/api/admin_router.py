"""管理 HTTP 路由：RAG 知识库维护。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.common.logger import logger
from app.rag.store import get_store

router = APIRouter(prefix="/rag", tags=["admin/rag"])


class RagUpsertRequest(BaseModel):
    collection: str = Field(pattern=r"^(rubric|exemplar|gold_case)$")
    documents: List[str]
    metadatas: Optional[List[dict]] = None


class RagUpsertResponse(BaseModel):
    collection: str
    upserted: int


class RagStatsResponse(BaseModel):
    counts: Dict[str, int]
    persist_dir: str


class RagSeedRequest(BaseModel):
    reset: bool = False
    seed_dir: Optional[str] = None


class RagSeedResponse(BaseModel):
    seeded: Dict[str, int]
    seed_dir: str


@router.get("/stats", response_model=RagStatsResponse)
async def stats() -> RagStatsResponse:
    store = get_store()
    counts: Dict[str, int] = {}
    for name in ("rubric", "exemplar", "gold_case"):
        try:
            counts[name] = store.count(name)
        except Exception as e:
            logger.warning(f"[admin/rag] 统计 {name} 失败: {e}")
            counts[name] = -1
    return RagStatsResponse(counts=counts, persist_dir=str(store._persist_dir))


@router.post("/upsert", response_model=RagUpsertResponse)
async def upsert(req: RagUpsertRequest) -> RagUpsertResponse:
    if not req.documents:
        raise HTTPException(400, "documents 不能为空")
    try:
        n = get_store().add_documents(
            collection=req.collection,
            documents=req.documents,
            metadatas=req.metadatas,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    except Exception as e:
        logger.exception("[admin/rag] upsert 失败")
        raise HTTPException(500, f"upsert 失败: {e}") from e
    return RagUpsertResponse(collection=req.collection, upserted=n)


@router.post("/seed", response_model=RagSeedResponse, status_code=status.HTTP_200_OK)
async def seed(req: RagSeedRequest) -> RagSeedResponse:
    """从 seed 目录批量导入 3 类文档。

    默认使用 `app/rag/seed/`。rubric.md 全文作为一条；exemplar/gold_case 按 jsonl 行。
    """
    default_seed = Path(__file__).resolve().parent.parent / "rag" / "seed"
    seed_dir = Path(req.seed_dir).expanduser() if req.seed_dir else default_seed
    if not seed_dir.exists():
        raise HTTPException(404, f"seed 目录不存在: {seed_dir}")

    store = get_store()
    if req.reset:
        try:
            store.reset()
        except Exception as e:
            logger.warning(f"[admin/rag] reset 失败（忽略）: {e}")

    stats: Dict[str, int] = {}
    try:
        # rubric.md
        rubric_file = seed_dir / "rubric.md"
        if rubric_file.exists():
            text = rubric_file.read_text(encoding="utf-8")
            # 按章节粗切，避免单条太长
            chunks = [c.strip() for c in text.split("\n## ") if c.strip()]
            docs = [chunks[0]] + [f"## {c}" for c in chunks[1:]] if chunks else []
            metas = [{"kind": "rubric"} for _ in docs]
            stats["rubric"] = store.add_documents("rubric", docs, metas)

        for fname, coll in (("exemplar.jsonl", "exemplar"), ("gold_case.jsonl", "gold_case")):
            f = seed_dir / fname
            if not f.exists():
                stats[coll] = 0
                continue
            docs: List[str] = []
            metas: List[dict] = []
            for line in f.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(f"[admin/rag] 跳过非 JSON 行 {fname}: {e}")
                    continue
                content = obj.get("content") or obj.get("text") or json.dumps(obj, ensure_ascii=False)
                meta = {k: v for k, v in obj.items() if k not in ("content", "text")}
                docs.append(str(content))
                metas.append(meta)
            stats[coll] = store.add_documents(coll, docs, metas)
    except Exception as e:
        logger.exception("[admin/rag] seed 失败")
        raise HTTPException(500, f"seed 失败: {e}") from e

    return RagSeedResponse(seeded=stats, seed_dir=str(seed_dir))
