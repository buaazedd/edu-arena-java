"""对战平台 (edu-arena-java) REST 客户端：封装 5 个核心接口。

严格对齐 Java 端：
- 登录：POST /api/login          -> Result<ArenaLoginVO>
- 创建：POST /api/battle/create  -> Result<Long>   （data 即 battle_id）
- 生成：GET  /api/battle/{id}/generate -> Result<BattleVO>
- 详情：GET  /api/battle/{id}    -> Result<BattleVO>
- 投票：POST /api/battle/{id}/vote -> Result<VoteResultVO>

所有 JSON 为 snake_case（与 JacksonConfig 一致）。
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

import httpx

from app.common.exceptions import ArenaApiError
from app.common.logger import logger
from app.common.retry import aretry_http
from app.contracts.arena_dto import (
    ArenaBattleVO,
    ArenaCreateBattleRequest,
    ArenaLoginRequest,
    ArenaLoginVO,
    ArenaResult,
    ArenaVoteRequest,
    ArenaVoteResultVO,
)
from app.settings import get_settings


def _unwrap(result_json: Dict[str, Any], typ):
    """从 `{code,message,data}` 中提取 data 并用指定类型校验。"""
    code = result_json.get("code")
    if code != 200:
        raise ArenaApiError(
            f"Arena 业务错误 code={code} message={result_json.get('message')}",
            http_status=code if isinstance(code, int) else None,
            body=str(result_json)[:500],
        )
    data = result_json.get("data")
    if typ is None:
        return data
    if isinstance(typ, type) and issubclass(typ, object) and hasattr(typ, "model_validate"):
        return typ.model_validate(data)
    return data


class ArenaClient:
    """对战平台异步客户端。"""

    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        timeout: float = 120.0,
    ) -> None:
        s = get_settings()
        self.base_url = (base_url or s.arena_base_url).rstrip("/")
        self.username = username or s.arena_username
        self.password = password or s.arena_password
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=timeout)
        self._token: Optional[str] = None
        self._login_lock = asyncio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "ArenaClient":
        return self

    async def __aexit__(self, *args) -> None:
        await self.close()

    # ------------------- 底层 HTTP -------------------

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict] = None,
        auth: bool = True,
    ) -> Dict[str, Any]:
        if auth and not self._token:
            await self.login()
        headers: Dict[str, str] = {}
        if auth and self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        async def _do() -> Dict[str, Any]:
            resp = await self._client.request(method, path, json=json_body, headers=headers)
            if resp.status_code == 401 and auth:
                # 令牌过期 → 重新登录 + 抛出让重试层重试
                logger.warning("[arena] 401 未授权，刷新 token 后重试")
                self._token = None
                await self.login()
                raise httpx.HTTPStatusError("401", request=resp.request, response=resp)
            if resp.status_code >= 500:
                raise httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
            if resp.status_code >= 400:
                raise ArenaApiError(
                    f"Arena HTTP {resp.status_code}",
                    http_status=resp.status_code,
                    body=resp.text[:500],
                )
            try:
                return resp.json()
            except Exception as e:
                raise ArenaApiError(f"Arena 响应非 JSON: {e}", body=resp.text[:500]) from e

        return await aretry_http(_do, max_attempts=3)

    # ------------------- 业务接口 -------------------

    async def login(self) -> str:
        async with self._login_lock:
            if self._token:
                return self._token
            body = ArenaLoginRequest(username=self.username, password=self.password).model_dump()
            raw = await self._request("POST", "/api/login", json_body=body, auth=False)
            vo: ArenaLoginVO = _unwrap(raw, ArenaLoginVO)
            self._token = vo.token
            logger.info(f"[arena] 登录成功 user={self.username} role={vo.role}")
            return self._token

    async def create_battle(self, req: ArenaCreateBattleRequest) -> int:
        raw = await self._request(
            "POST", "/api/battle/create", json_body=req.model_dump(exclude_none=True)
        )
        data = _unwrap(raw, None)
        if not isinstance(data, int):
            raise ArenaApiError(f"create 返回 data 非 int: {data}", body=str(raw)[:300])
        logger.info(f"[arena] create_battle -> battle_id={data}")
        return data

    async def generate(self, battle_id: int) -> ArenaBattleVO:
        raw = await self._request("GET", f"/api/battle/{battle_id}/generate")
        vo = _unwrap(raw, ArenaBattleVO)
        logger.info(f"[arena] generate battle_id={battle_id} status={vo.status}")
        return vo

    async def get_battle(self, battle_id: int) -> ArenaBattleVO:
        raw = await self._request("GET", f"/api/battle/{battle_id}")
        return _unwrap(raw, ArenaBattleVO)

    async def vote(self, battle_id: int, req: ArenaVoteRequest) -> ArenaVoteResultVO:
        body = req.model_dump(exclude_none=True)
        raw = await self._request("POST", f"/api/battle/{battle_id}/vote", json_body=body)
        vo = _unwrap(raw, ArenaVoteResultVO)
        logger.info(
            f"[arena] vote battle_id={battle_id} winner_side={vo.winner_side} overall={vo.overall_winner}"
        )
        return vo


__all__ = ["ArenaClient"]
