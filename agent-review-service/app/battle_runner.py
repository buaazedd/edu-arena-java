from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path

from app.arena_client import ArenaClient
from app.arena_dto import ArenaCreateBattleRequest
from app.runner_config import runner_settings
from app.simple_agent_reviewer import SimpleAgentReviewer
from app.task_store_mysql import TaskStoreMySQL
from app.writing_dataset import JsonWritingSample, load_samples_from_json, to_create_battle_request
from app.writing_loader import load_writing_samples


def _task_key_from_json_sample(s: JsonWritingSample) -> str:
    raw = f"json|{s.sample_id}|{s.essay_title}|{runner_settings.prompt_version}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def run_batch() -> None:
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    print(f"[RUN] {run_id} start")

    store = TaskStoreMySQL()
    client = ArenaClient()
    reviewer = SimpleAgentReviewer()

    login_data = client.login()
    print(f"[AUTH] login ok, role={login_data.role}")

    if runner_settings.writing_json_file:
        json_file = runner_settings.writing_json_file
        samples = load_samples_from_json(json_file)[: runner_settings.batch_limit]
        for s in samples:
            store.upsert_pending(
                task_key=_task_key_from_json_sample(s),
                sample_id=s.sample_id,
                source_file=json_file,
                essay_title=s.essay_title,
                essay_content=s.essay_content,
                grade_level=s.grade_level,
                requirements=s.requirements,
                image_paths_json=json.dumps(s.image_paths, ensure_ascii=False),
            )
    else:
        # 兼容旧模式（label_cn.txt）
        samples = load_writing_samples(limit=runner_settings.batch_limit)
        for s in samples:
            store.upsert_pending(
                task_key=s.task_key,
                sample_id=s.sample_id,
                source_file=s.source_file,
                essay_title=s.essay_title,
                essay_content=s.essay_content,
                grade_level=s.grade_level,
                requirements=s.requirements,
                image_paths_json=json.dumps(s.image_paths or [], ensure_ascii=False),
            )

    tasks = store.fetch_runnable(limit=runner_settings.batch_limit)
    print(f"[TASK] runnable={len(tasks)}")

    for t in tasks:
        try:
            # 1) create battle
            image_paths = json.loads(t.image_paths_json or "[]")
            req = ArenaCreateBattleRequest(
                essay_title=t.essay_title,
                essay_content=t.essay_content,
                grade_level=t.grade_level,
                requirements=t.requirements,
                images=[],
            )
            if runner_settings.writing_json_file:
                sample = JsonWritingSample(
                    sample_id=t.sample_id,
                    essay_title=t.essay_title,
                    essay_content=t.essay_content,
                    grade_level=t.grade_level,
                    requirements=t.requirements,
                    image_paths=image_paths,
                )
                req = to_create_battle_request(sample, json_file=runner_settings.writing_json_file)
            elif image_paths:
                # 旧模式：label_cn.txt 路径相对于项目根目录（edu-arena-java）
                sample = JsonWritingSample(
                    sample_id=t.sample_id,
                    essay_title=t.essay_title,
                    essay_content=t.essay_content,
                    grade_level=t.grade_level,
                    requirements=t.requirements,
                    image_paths=image_paths,
                )
                label_base = str((Path(__file__).resolve().parents[2] / "writing" / "label_cn.txt").resolve())
                req = to_create_battle_request(sample, json_file=label_base)

            battle_id = client.create_battle(req)
            store.mark_created(t.task_key, battle_id)
            print(f"[CREATE] sample={t.sample_id}, battle={battle_id}")

            # 2) generate
            battle = client.generate_battle(battle_id)
            store.mark_generated(t.task_key, battle_id)

            left = battle.response_left or ""
            right = battle.response_right or ""

            # 3) agent review
            agent_vote = reviewer.review(
                essay_title=battle.essay_title or t.essay_title,
                essay_content=battle.essay_content or t.essay_content or "",
                left_text=left,
                right_text=right,
            )

            # 4) submit vote
            vote_req = client.map_agent_vote_to_arena_vote(agent_vote)
            vote_resp = client.vote(battle_id, vote_req)

            # 5) mark done
            store.mark_voted(
                t.task_key,
                {
                    "battle_id": battle_id,
                    "agent_vote": agent_vote.model_dump(),
                    "vote_response": vote_resp,
                },
            )
            print(f"[VOTE] sample={t.sample_id}, battle={battle_id}, ok")

            time.sleep(0.2)

        except Exception as ex:
            store.mark_failed(t.task_key, str(ex))
            print(f"[FAIL] sample={t.sample_id}, err={ex}")

    print(f"[RUN] {run_id} done")


if __name__ == "__main__":
    run_batch()
