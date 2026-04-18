from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from agent_client import review_run
from java_client import (
    collect_battle_outputs,
    create_battle,
    get_battle_meta,
    image_to_base64_no_prefix,
    service_login,
)
from parse_labels import load_all_samples


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def run_one(
    writing_dir: Path,
    out_dir: Path,
    java_base_url: str,
    java_secret: str,
    agent_base_url: str,
    sample_lang: str,
    sample_image: str,
    essay_title: str,
    grade_level: str,
    requirements: str | None,
    timeout_sse: int,
) -> Dict[str, Any]:
    token = service_login(java_base_url, java_secret)

    # 兼容 writing/ 下的子目录结构：chinese/ english/
    # 优先在子目录中找，其次再回退到 writing/ 根目录
    subdir = "chinese" if sample_lang == "cn" else "english"
    image_path = writing_dir / subdir / sample_image
    if not image_path.exists():
        image_path = writing_dir / sample_image
    images_b64 = [image_to_base64_no_prefix(image_path)]

    battle_id = create_battle(
        java_base_url=java_base_url,
        token=token,
        essay_title=essay_title[:200],
        images_b64=images_b64,
        grade_level=grade_level,
        requirements=requirements,
    )

    status, content_a, content_b = collect_battle_outputs(java_base_url, token, battle_id, timeout_s=timeout_sse)
    # 注意：Java侧可能在生成失败时切换模型并更新battle模型绑定，因此meta必须在生成后再取
    meta = get_battle_meta(java_base_url, token, battle_id)

    review = review_run(
        agent_base_url=agent_base_url,
        battle_id=battle_id,
        essay_title=essay_title[:200],
        grade_level=grade_level,
        requirements=requirements,
        essay_text="",
        images_b64=images_b64,
        model_a_id=str(meta.model_a.get("model_id") or "modelA"),
        model_a_content=content_a,
        model_b_id=str(meta.model_b.get("model_id") or "modelB"),
        model_b_content=content_b,
    )

    record = {
        "sampleId": sample_image,
        "battleId": battle_id,
        "battleStatus": status,
        "essayTitle": essay_title,
        "gradeLevel": grade_level,
        "requirements": requirements,
        "java": {
            "matchType": meta.match_type,
            "displayOrder": meta.display_order,
            "modelA": meta.model_a,
            "modelB": meta.model_b,
        },
        "outputs": {"A": content_a, "B": content_b},
        "reviewResult": review.raw,
        "createdAt": _now_iso(),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    # 每条样本单独落盘，避免中途失败导致整体丢失
    (out_dir / f"{sample_image}.json").write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--writing-dir", default=str(Path(__file__).resolve().parents[1] / "writing"))
    ap.add_argument("--out-dir", default=str(Path(__file__).resolve().parents[1] / "batch-output"))
    ap.add_argument("--java-base-url", default=os.getenv("JAVA_BASE_URL", "http://localhost:5001"))
    ap.add_argument("--java-service-secret", default=os.getenv("JAVA_SERVICE_SECRET", ""))
    ap.add_argument("--agent-base-url", default=os.getenv("AGENT_REVIEW_URL", "http://localhost:8000"))
    ap.add_argument("--grade-level", default="高中")
    ap.add_argument("--timeout-sse", type=int, default=190)
    ap.add_argument("--limit", type=int, default=0, help="只跑前N条，0表示全量")
    ap.add_argument("--concurrency", type=int, default=1, help="并发数(建议1-5)")
    args = ap.parse_args()

    if not args.java_service_secret:
        raise SystemExit("missing --java-service-secret (or env JAVA_SERVICE_SECRET)")

    writing_dir = Path(args.writing_dir)
    out_dir = Path(args.out_dir)

    samples = load_all_samples(writing_dir)
    if args.limit and args.limit > 0:
        samples = samples[: args.limit]

    summary_path = out_dir / "summary.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)

    def _task(sample):
        try:
            record = run_one(
                writing_dir=writing_dir,
                out_dir=out_dir / sample.lang,
                java_base_url=args.java_base_url,
                java_secret=args.java_service_secret,
                agent_base_url=args.agent_base_url,
                sample_lang=sample.lang,
                sample_image=sample.image_file,
                essay_title=sample.essay_title,
                grade_level=args.grade_level,
                requirements=None,
                timeout_sse=args.timeout_sse,
            )
            return {"ok": True, "sampleId": sample.image_file, "lang": sample.lang, "battleId": record["battleId"]}
        except Exception as e:
            return {"ok": False, "sampleId": sample.image_file, "lang": sample.lang, "error": str(e)}

    concurrency = max(1, int(args.concurrency))
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(_task, s) for s in samples]
        for fut in concurrent.futures.as_completed(futures):
            item = fut.result()
            with summary_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

