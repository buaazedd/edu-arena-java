from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Literal, Optional, Tuple

import requests


EventType = Literal["A", "B", "D", "E"]


@dataclass(frozen=True)
class BattleMeta:
    battle_id: int
    status: str
    match_type: str | None
    display_order: str | None
    model_a: dict
    model_b: dict


def image_to_base64_no_prefix(image_path: Path) -> str:
    data = image_path.read_bytes()
    return base64.b64encode(data).decode("ascii")


def service_login(java_base_url: str, secret: str, timeout_s: int = 20) -> str:
    url = f"{java_base_url.rstrip('/')}/api/service-login"
    resp = requests.post(url, json={"secret": secret}, timeout=timeout_s)
    try:
        payload = resp.json()
    except Exception:
        payload = {"_raw": resp.text}

    if resp.status_code >= 400:
        raise RuntimeError(f"service-login http={resp.status_code} body={payload}")
    if payload.get("code") != 200:
        raise RuntimeError(f"service-login failed: {payload}")
    token = (payload.get("data") or {}).get("token")
    if not token:
        raise RuntimeError(f"service-login missing token: {payload}")
    return token


def create_battle(
    java_base_url: str,
    token: str,
    essay_title: str,
    images_b64: list[str],
    grade_level: str = "高中",
    requirements: str | None = None,
    essay_content: str | None = None,
    timeout_s: int = 60,
) -> int:
    url = f"{java_base_url.rstrip('/')}/api/battle/create"
    headers = {"Authorization": f"Bearer {token}"}
    body: Dict[str, Any] = {
        # 服务端 Jackson 配置为 snake_case
        "essay_title": essay_title,
        "essay_content": essay_content,
        "grade_level": grade_level,
        "requirements": requirements,
        "images": images_b64,
    }
    resp = requests.post(url, headers=headers, json=body, timeout=timeout_s)
    try:
        payload = resp.json()
    except Exception:
        payload = {"_raw": resp.text}

    if resp.status_code >= 400:
        raise RuntimeError(f"create-battle http={resp.status_code} body={payload}")
    if payload.get("code") != 200:
        raise RuntimeError(f"create-battle failed: {payload}")
    battle_id = payload.get("data")
    if not isinstance(battle_id, int):
        raise RuntimeError(f"create-battle invalid battleId: {payload}")
    return battle_id


def get_battle_meta(java_base_url: str, token: str, battle_id: int, timeout_s: int = 20) -> BattleMeta:
    url = f"{java_base_url.rstrip('/')}/api/battle/{battle_id}/meta"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=timeout_s)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 200:
        raise RuntimeError(f"battle-meta failed: {payload}")
    data = payload.get("data") or {}
    return BattleMeta(
        battle_id=int(data.get("battle_id")),
        status=str(data.get("status")),
        match_type=data.get("match_type"),
        display_order=data.get("display_order"),
        model_a=data.get("model_a") or {},
        model_b=data.get("model_b") or {},
    )


def iter_sse_events(java_base_url: str, token: str, battle_id: int, timeout_s: int = 190) -> Iterator[dict]:
    """
    解析Java SSE接口，产出形如 {"t":"A|B|D|E","c":"..."} 的事件dict。
    """
    url = f"{java_base_url.rstrip('/')}/api/battle/{battle_id}/stream"
    headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

    with requests.get(url, headers=headers, stream=True, timeout=timeout_s) as resp:
        resp.raise_for_status()
        buffer = ""
        for chunk in resp.iter_content(chunk_size=4096, decode_unicode=True):
            if not chunk:
                continue
            buffer += chunk
            while "\n\n" in buffer:
                raw_event, buffer = buffer.split("\n\n", 1)
                for line in raw_event.splitlines():
                    line = line.strip()
                    if not line.startswith("data:"):
                        continue
                    data_str = line[5:].strip()
                    if not data_str:
                        continue
                    try:
                        yield json.loads(data_str)
                    except Exception:
                        # 容错：忽略无法解析的事件
                        continue


def collect_battle_outputs(
    java_base_url: str, token: str, battle_id: int, timeout_s: int = 190
) -> tuple[str, str, str]:
    """
    返回 (status, contentA, contentB)
    status: done/partial_failed/unknown
    """
    content_a: list[str] = []
    content_b: list[str] = []
    final_status = "unknown"

    for ev in iter_sse_events(java_base_url, token, battle_id, timeout_s=timeout_s):
        t = ev.get("t")
        c = ev.get("c", "")
        if t == "A":
            content_a.append(c)
        elif t == "B":
            content_b.append(c)
        elif t == "D":
            final_status = "done"
            break
        elif t == "E":
            final_status = "partial_failed"
            # 不一定会再发D，遇到E就结束
            break

    return final_status, "".join(content_a), "".join(content_b)

