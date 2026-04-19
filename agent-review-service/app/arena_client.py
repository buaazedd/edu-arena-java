from __future__ import annotations

from typing import Any

import requests

from app.arena_dto import (
    AgentVoteResult,
    ArenaBattleData,
    ArenaCreateBattleRequest,
    ArenaLoginData,
    ArenaLoginRequest,
    ArenaResult,
    ArenaVoteRequest,
)
from app.runner_config import runner_settings


class ArenaApiError(RuntimeError):
    pass


class ArenaClient:
    def __init__(self) -> None:
        self.base_url = runner_settings.arena_base_url.rstrip("/")
        self.timeout = runner_settings.request_timeout_seconds
        self.session = requests.Session()
        self._token: str | None = None

    def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        resp = self.session.request(method, url, headers=headers, timeout=self.timeout, **kwargs)
        resp.raise_for_status()
        payload = ArenaResult.model_validate(resp.json())
        if payload.code != 200:
            raise ArenaApiError(f"{path} failed: {payload.code} {payload.message}")
        return payload.data

    def login(self) -> ArenaLoginData:
        body = ArenaLoginRequest(
            username=runner_settings.arena_username,
            password=runner_settings.arena_password,
        )
        data = self._request("POST", "/api/login", json=body.model_dump())
        login_data = ArenaLoginData.model_validate(data)
        self._token = login_data.token
        return login_data

    def create_battle(self, req: ArenaCreateBattleRequest) -> int:
        data = self._request("POST", "/api/battle/create", json=req.model_dump())
        return int(data)

    def generate_battle(self, battle_id: int) -> ArenaBattleData:
        data = self._request("GET", f"/api/battle/{battle_id}/generate")
        return ArenaBattleData.model_validate(data)

    def vote(self, battle_id: int, vote: ArenaVoteRequest) -> dict[str, Any]:
        data = self._request("POST", f"/api/battle/{battle_id}/vote", json=vote.model_dump())
        return data if isinstance(data, dict) else {"data": data}

    @staticmethod
    def map_agent_vote_to_arena_vote(agent_vote: AgentVoteResult) -> ArenaVoteRequest:
        def map_side(winner: str) -> str:
            if winner == "A":
                return "left"
            if winner == "B":
                return "right"
            return "tie"

        return ArenaVoteRequest(
            dim_theme=map_side(agent_vote.dim_theme.winner),
            dim_imagination=map_side(agent_vote.dim_imagination.winner),
            dim_logic=map_side(agent_vote.dim_logic.winner),
            dim_language=map_side(agent_vote.dim_language.winner),
            dim_writing=map_side(agent_vote.dim_writing.winner),
            dim_theme_reason=agent_vote.dim_theme.reason,
            dim_imagination_reason=agent_vote.dim_imagination.reason,
            dim_logic_reason=agent_vote.dim_logic.reason,
            dim_language_reason=agent_vote.dim_language.reason,
            dim_writing_reason=agent_vote.dim_writing.reason,
            vote_time=5.0,
        )
