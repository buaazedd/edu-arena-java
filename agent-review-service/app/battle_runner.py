from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from pathlib import Path

from app.arena_client import ArenaClient
from app.multi_agent_adapter import MultiAgentAdapter
from app.runner_config import runner_settings
from app.review_contract import ReviewCase
from app.task_store_mysql import TaskStoreMySQL
from app.test_cases_loader import load_test_cases
from app.writing_dataset import JsonWritingSample, to_create_battle_request
from app.writing_loader import load_writing_samples


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _task_key_from_json_sample(s: JsonWritingSample) -> str:
    raw = f"json|{s.sample_id}|{s.essay_title}|{runner_settings.prompt_version}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def run_batch() -> None:
    run_id = f"run_{uuid.uuid4().hex[:8]}"
    logger.info("[RUN] %s start", run_id)

    store = TaskStoreMySQL()
    client = ArenaClient()
    reviewer = MultiAgentAdapter()

    login_data = client.login()
    logger.info("[AUTH] login ok, role=%s", login_data.role)

    if runner_settings.writing_json_file:
        samples = load_test_cases(runner_settings.writing_json_file)[: runner_settings.batch_limit]
    else:
        samples = load_writing_samples(limit=runner_settings.batch_limit)

    logger.info("[TASK] samples=%s", len(samples))

    for s in samples:
        image_paths = list(s.image_paths or [])
        if runner_settings.writing_json_file:
            store.upsert_pending(
                task_key=_task_key_from_json_sample(s),
                sample_id=s.sample_id,
                source_file=runner_settings.writing_json_file,
                essay_title=s.essay_title,
                essay_content=s.essay_content,
                grade_level=s.grade_level,
                requirements=s.requirements,
                image_paths_json=json.dumps(image_paths, ensure_ascii=False),
            )
        else:
            store.upsert_pending(
                task_key=s.task_key,
                sample_id=s.sample_id,
                source_file=s.source_file,
                essay_title=s.essay_title,
                essay_content=s.essay_content,
                grade_level=s.grade_level,
                requirements=s.requirements,
                image_paths_json=json.dumps(image_paths, ensure_ascii=False),
            )

    tasks = store.fetch_runnable(limit=runner_settings.batch_limit)
    logger.info("[TASK] runnable=%s", len(tasks))

    for t in tasks:
        try:
            image_paths = json.loads(t.image_paths_json or "[]")
            sample = JsonWritingSample(
                sample_id=t.sample_id,
                essay_title=t.essay_title,
                essay_content=t.essay_content,
                grade_level=t.grade_level,
                requirements=t.requirements,
                image_paths=image_paths,
            )
            if runner_settings.writing_json_file:
                req = to_create_battle_request(sample, json_file=runner_settings.writing_json_file)
            else:
                label_base = str((Path(__file__).resolve().parents[2] / "writing" / "label_cn.txt").resolve())
                req = to_create_battle_request(sample, json_file=label_base)

            battle_id = client.create_battle(req)
            store.mark_created(t.task_key, battle_id)
            logger.info("[CREATE] sample=%s battle=%s", t.sample_id, battle_id)

            battle = client.generate_battle(battle_id)
            store.mark_generated(t.task_key, battle_id)

            case = ReviewCase(
                sample_id=t.sample_id,
                essay_title=battle.essay_title or t.essay_title,
                essay_content=battle.essay_content or t.essay_content,
                image_paths=image_paths,
                left_text=battle.response_left or "",
                right_text=battle.response_right or "",
                model_left=(battle.model_left.name if battle.model_left else None),
                model_right=(battle.model_right.name if battle.model_right else None),
                battle_id=battle_id,
            )
            agent_vote = reviewer.review(case)

            vote_req = client.map_agent_vote_to_arena_vote(agent_vote)
            vote_resp = client.vote(battle_id, vote_req)

            review_payload = {
                "battle_id": battle_id,
                "agent_winner": agent_vote.overall_winner,
                "review_payload": agent_vote.to_dict(),
                "vote_response": vote_resp,
            }
            store.mark_voted(t.task_key, review_payload)
            logger.info(
                "[VOTE] sample=%s battle=%s ok agent_winner=%s review=%s",
                t.sample_id,
                battle_id,
                agent_vote.overall_winner,
                agent_vote.to_dict(),
            )

            time.sleep(0.2)

        except Exception as ex:
            store.mark_failed(t.task_key, str(ex))
            logger.exception("[FAIL] sample=%s err=%s", t.sample_id, ex)

    logger.info("[RUN] %s done", run_id)


if __name__ == "__main__":
    run_batch()
