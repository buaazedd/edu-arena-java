from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import requests


@dataclass(frozen=True)
class ReviewResult:
    raw: Dict[str, Any]


def review_run(
    agent_base_url: str,
    battle_id: int,
    essay_title: str,
    grade_level: str,
    requirements: str | None,
    essay_text: str,
    images_b64: list[str],
    model_a_id: str,
    model_a_content: str,
    model_b_id: str,
    model_b_content: str,
    timeout_s: int = 300,
) -> ReviewResult:
    url = f"{agent_base_url.rstrip('/')}/review/run"
    payload = {
        "battleId": int(battle_id),
        "taskMeta": {
            "essayTitle": essay_title,
            "gradeLevel": grade_level,
            "requirements": requirements,
        },
        "input": {
            "essayText": essay_text,
            "images": images_b64,
        },
        "outputs": {
            "modelA": {"modelId": model_a_id, "content": model_a_content},
            "modelB": {"modelId": model_b_id, "content": model_b_content},
        },
        "rubricConfig": {
            "version": "rubric_v1",
            "dimensions": ["theme", "imagination", "logic", "language", "writing"],
        },
    }
    resp = requests.post(url, json=payload, timeout=timeout_s)
    resp.raise_for_status()
    return ReviewResult(raw=resp.json())

