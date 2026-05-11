"""
本地直连 MySQL 导出偏好数据集（替代服务器侧 `/api/export` 接口）。

背景
----
服务器端 ExportServiceImpl 走的链路：
    MySQL(国内, ~200ms RTT) ──► Java(新加坡) ──► 浏览器回传(跨境又一次)
数据跨境 2 次，且每次 MySQL 查询都吃 200ms RTT。

本地直连后的链路：
    MySQL(国内, ~8ms RTT) ──► 本地直接写 zip
延迟 25x 改善，而且只跨境 1 次。实测 800MB images_json 下整体耗时可从
30+ 分钟降到 5 分钟量级。

输出格式与 ExportServiceImpl.exportZip 保持一致（schema_version=1.0），
目录/JSON 字段命名完全对齐，消费方脚本无感切换。

用法
----
    # 导出所有 voted battle（含图片）
    python3 scripts/export_dataset_local.py -o out.zip

    # 按时间范围 + 不含图片
    python3 scripts/export_dataset_local.py -o out.zip \\
        --start-date 2026-04-01 --end-date 2026-05-11 --no-images

    # 只导某一场
    python3 scripts/export_dataset_local.py -o out.zip --battle-id 123

    # 限量（调试用）
    python3 scripts/export_dataset_local.py -o out.zip --limit 10

    # 保留脏数据（默认会过滤 agent 调用失败被兜底为 tie 的 vote）
    python3 scripts/export_dataset_local.py -o out.zip --keep-dirty

脏数据过滤
----------
agent-review-service 在 LLM 调用失败时，会走 `_fallback_score` 产生一条 winner=tie
且 reason 前缀为 "LLM 评审失败，降级为 tie" 的兜底 vote 回写到数据库（实测样本：
403 鉴权失败、401 quota 耗尽等）。这类 vote 的偏好信号不可信，训练集用不得，
默认过滤掉（battle 记录也一并跳过）。`--keep-dirty` 可保留以做审计。

依赖
----
pymysql（系统默认通常已安装；缺失请：pip3 install pymysql）
"""

import argparse
import base64
import io
import json
import os
import sys
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError:
    sys.stderr.write("缺少依赖 pymysql，请执行: pip3 install pymysql\n")
    sys.exit(1)


SCHEMA_VERSION = "1.0"
# 读 images_json 的并发度。本地 RTT 8ms，开 8 路对数据库压力不大，
# 主要瓶颈其实是跨境拉 800MB 数据的带宽，并发主要用来重叠 MySQL 单查询的处理时间。
IMAGE_FETCH_CONCURRENCY = 8
# MySQL 默认 max_allowed_packet 16MB，部分 images_json 单行可能几 MB，
# 客户端这边显式不限制收包上限（pymysql 默认已放宽）。

# -------------------------- 命令行参数 --------------------------

def build_parser():
    p = argparse.ArgumentParser(description="本地直连 MySQL 导出偏好数据集 zip")
    p.add_argument("-o", "--output", default=f"edu_arena_dataset_{datetime.now():%Y%m%d_%H%M%S}.zip",
                   help="输出 zip 文件路径，默认按时间戳生成")
    # 数据过滤（与 ExportQuery 对齐）
    p.add_argument("--battle-id", type=int, help="只导出单场对战")
    p.add_argument("--winner", choices=["A", "B", "tie"], help="按胜方过滤")
    p.add_argument("--model-id", help="按模型过滤：可传主键 id 或 model_id 字符串")
    p.add_argument("--start-date", help="创建时间起（含），格式 YYYY-MM-DD")
    p.add_argument("--end-date", help="创建时间止（含），格式 YYYY-MM-DD")
    p.add_argument("--limit", type=int, help="最多导出多少条 battle（0/不传=不限）")
    p.add_argument("--no-images", action="store_true", help="不导出图片，仅 data.jsonl + manifest")
    p.add_argument("--keep-dirty", action="store_true",
                   help="保留 agent 调用失败被兜底为 tie 的脏数据（默认过滤）")
    p.add_argument("--progress-every", type=int, default=100,
                   help="battle 级进度打印粒度，默认每 100 条一行")
    p.add_argument("--image-concurrency", type=int, default=IMAGE_FETCH_CONCURRENCY,
                   help=f"图片拉取并发度（默认 {IMAGE_FETCH_CONCURRENCY}，跨境瓶颈在带宽，可调到 16-32）")

    # DB 连接（默认读 application.yml，也支持命令行覆盖 / 环境变量）
    p.add_argument("--db-host", default=os.environ.get("EA_DB_HOST", "180.76.229.245"))
    p.add_argument("--db-port", type=int, default=int(os.environ.get("EA_DB_PORT", "3306")))
    p.add_argument("--db-user", default=os.environ.get("EA_DB_USER", "root"))
    p.add_argument("--db-password", default=os.environ.get("EA_DB_PASSWORD", "zyd123"))
    p.add_argument("--db-name", default=os.environ.get("EA_DB_NAME", "edu_arena"))
    return p


# -------------------------- DB 连接池（单连接 + 并发连接） --------------------------

def new_conn(args):
    return pymysql.connect(
        host=args.db_host, port=args.db_port,
        user=args.db_user, password=args.db_password,
        database=args.db_name,
        charset="utf8mb4",
        connect_timeout=10,
        read_timeout=600,
        cursorclass=DictCursor,
        autocommit=True,
    )


# -------------------------- 脏数据识别 --------------------------

# agent-review-service `app/review/nodes/dimension_agent.py::_fallback_score` 的固定前缀。
# 当该服务调用 LLM 失败（403/401/超时等）时，会保守打上 winner=tie，
# reason 形如 "LLM 评审失败，降级为 tie。原因：..."。这类 vote 偏好信号不可信。
_DIRTY_REASON_MARKERS = (
    "LLM 评审失败，降级为 tie",
    "LLM 评审失败",  # 兜个底，防止将来文案微调
)

_REASON_FIELDS = (
    "dim_theme_reason",
    "dim_imagination_reason",
    "dim_logic_reason",
    "dim_language_reason",
    "dim_writing_reason",
    "dim_overall_reason",
)


def is_dirty_vote(vote):
    """判定一条 vote 是否是 agent 调用失败兜底产生的脏数据。

    规则：6 个维度 reason 字段中**任意一个**命中已知降级文案前缀即算脏。
    实测中这类 vote 通常 6 维 reason 都带该前缀（整条评审流水线一起崩），
    但保守起见用 OR 而不是 AND。
    """
    if not vote:
        return False
    for f in _REASON_FIELDS:
        val = vote.get(f)
        if not val:
            continue
        for marker in _DIRTY_REASON_MARKERS:
            if marker in val:
                return True
    return False


# -------------------------- 过滤条件 --------------------------

def resolve_model_pk(conn, raw):
    """入参可能是主键 id 数字串，也可能是 model_id 字符串。返回主键 id。"""
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM models WHERE model_id=%s LIMIT 1", (raw,))
        r = cur.fetchone()
        return r["id"] if r else None


def build_battle_where(args, conn):
    """返回 (where_sql, params, summary_dict)。始终约束 status='voted'。

    注意：调用方是一个 battles b LEFT JOIN tasks t 的语句，tasks/battles 都有
    id、created_at 等同名列，所有引用都必须显式加 `b.` 前缀，否则会 1052 ambiguous。
    """
    where = ["b.status='voted'"]
    params = []
    summary = {"status": "voted"}

    if args.battle_id is not None:
        where.append("b.id=%s"); params.append(args.battle_id)
        summary["battle_id"] = args.battle_id
    if args.winner:
        where.append("b.winner=%s"); params.append(args.winner)
        summary["winner"] = args.winner
    if args.model_id:
        pk = resolve_model_pk(conn, args.model_id)
        if pk is None:
            # 跟 ExportServiceImpl 行为一致：找不到就强制空集
            where.append("b.id=-1")
        else:
            where.append("(b.model_a_id=%s OR b.model_b_id=%s)")
            params.extend([pk, pk])
        summary["model_id"] = args.model_id
    if args.start_date:
        where.append("b.created_at>=%s")
        params.append(datetime.strptime(args.start_date, "%Y-%m-%d"))
        summary["start_date"] = args.start_date
    if args.end_date:
        # [end_date, end_date+1day) 与 Java 端一致（含当天）
        end_dt = datetime.strptime(args.end_date, "%Y-%m-%d") + timedelta(days=1)
        where.append("b.created_at<%s"); params.append(end_dt)
        summary["end_date"] = args.end_date

    summary["include_images"] = not args.no_images
    summary["limit"] = args.limit
    return " AND ".join(where), params, summary


# -------------------------- 一次性批量拉数据（SQL JOIN 把 RTT 压到 1） --------------------------

def load_all(conn, where_sql, params, limit):
    """
    与 ExportServiceImpl 分页不同：本地 RTT 8ms，不需要分页避免超时；
    一次性 JOIN 拉出所有 battle + task(轻字段) + vote，图片单独第二遍拉。
    """
    t0 = time.time()
    limit_sql = f" LIMIT {int(limit)}" if limit and limit > 0 else ""
    sql = f"""
        SELECT
            b.id            AS battle_id,
            b.task_id       AS task_id,
            b.model_a_id    AS model_a_id,
            b.model_b_id    AS model_b_id,
            b.display_order AS display_order,
            b.status        AS status,
            b.match_type    AS match_type,
            b.response_a    AS response_a,
            b.response_b    AS response_b,
            b.winner        AS winner,
            b.error_message AS error_message,
            b.created_at    AS created_at,
            t.id            AS t_id,
            t.user_id       AS t_user_id,
            t.essay_title   AS t_essay_title,
            t.essay_content AS t_essay_content,
            t.grade_level   AS t_grade_level,
            t.requirements  AS t_requirements,
            t.has_images    AS t_has_images,
            t.image_count   AS t_image_count,
            t.created_at    AS t_created_at
        FROM battles b
        LEFT JOIN tasks t ON t.id = b.task_id
        WHERE {where_sql}
        ORDER BY b.id ASC
        {limit_sql}
    """
    with conn.cursor() as cur:
        cur.execute(sql, params)
        battles = cur.fetchall()
    print(f"[导出] battles+tasks 一次 JOIN 拉回 {len(battles)} 行 ({int((time.time()-t0)*1000)}ms)")

    if not battles:
        return battles, {}, {}

    battle_ids = [b["battle_id"] for b in battles]
    model_ids = {b["model_a_id"] for b in battles} | {b["model_b_id"] for b in battles}
    model_ids.discard(None)

    # votes：跟 Java 版本语义一致，一场 battle 取 id 最小的那条
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute(
            f"SELECT * FROM votes WHERE battle_id IN ({','.join(['%s']*len(battle_ids))}) ORDER BY id ASC",
            battle_ids,
        )
        votes = cur.fetchall()
    vote_map = {}
    for v in votes:
        vote_map.setdefault(v["battle_id"], v)
    print(f"[导出] votes 拉回 {len(votes)} 条，匹配 {len(vote_map)} 场 ({int((time.time()-t0)*1000)}ms)")

    # models
    t0 = time.time()
    model_map = {}
    if model_ids:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, model_id, name, company FROM models WHERE id IN ({','.join(['%s']*len(model_ids))})",
                list(model_ids),
            )
            for m in cur.fetchall():
                model_map[m["id"]] = m
    print(f"[导出] models 拉回 {len(model_map)} 条 ({int((time.time()-t0)*1000)}ms)")

    return battles, vote_map, model_map


# -------------------------- 图片 base64 解码 / 写 zip --------------------------

def strip_base64_prefix(b64: str) -> str:
    if b64.startswith("data:"):
        comma = b64.find(",")
        if comma > 0:
            return b64[comma + 1:]
    return b64


def detect_image_ext(b64: str) -> str:
    if b64.startswith("data:image/png"):  return "png"
    if b64.startswith("data:image/webp"): return "webp"
    if b64.startswith("data:image/gif"):  return "gif"
    pure = strip_base64_prefix(b64)
    if pure.startswith("/9j/"):   return "jpg"
    if pure.startswith("iVBOR"):  return "png"
    if pure.startswith("UklGR"):  return "webp"
    if pure.startswith("R0lGOD"): return "gif"
    return "jpg"


def fetch_images_json(args, task_id):
    """单线程从独立连接拉某个 task 的 images_json。"""
    conn = new_conn(args)
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT images_json FROM tasks WHERE id=%s", (task_id,))
            r = cur.fetchone()
            return r["images_json"] if r else None
    finally:
        conn.close()


def parse_images_json(s):
    if not s:
        return []
    try:
        arr = json.loads(s)
        return [x for x in arr if isinstance(x, str) and x.strip()]
    except Exception as e:
        print(f"[WARN] 解析 images_json 失败: {e}", file=sys.stderr)
        return []


# -------------------------- JSON 组装（字段顺序对齐 Java 版） --------------------------

def iso(dt):
    """与 Jackson JavaTimeModule 默认 LocalDateTime 序列化对齐（ISO-8601 无时区）。"""
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def model_brief(m):
    if m is None:
        return {}
    return {"id": m["id"], "model_id": m["model_id"], "name": m["name"], "company": m["company"]}


def dim(winner, reason):
    return {"winner": winner, "reason": reason}


def vote_brief(v):
    if v is None:
        return None
    return {
        "vote_id": v["id"],
        "voter_user_id": v["user_id"],
        "winner": v["winner"],
        "dimensions": {
            "theme":       dim(v["dim_theme"],       v["dim_theme_reason"]),
            "imagination": dim(v["dim_imagination"], v["dim_imagination_reason"]),
            "logic":       dim(v["dim_logic"],       v["dim_logic_reason"]),
            "language":    dim(v["dim_language"],    v["dim_language_reason"]),
            "writing":     dim(v["dim_writing"],     v["dim_writing_reason"]),
            "overall":     dim(v["dim_overall"],     v["dim_overall_reason"]),
        },
        "vote_time_seconds": float(v["vote_time"]) if v["vote_time"] is not None else None,
        "elo": {
            "a_before": float(v["elo_a_before"]) if v["elo_a_before"] is not None else None,
            "a_after":  float(v["elo_a_after"])  if v["elo_a_after"]  is not None else None,
            "b_before": float(v["elo_b_before"]) if v["elo_b_before"] is not None else None,
            "b_after":  float(v["elo_b_after"])  if v["elo_b_after"]  is not None else None,
        },
        "created_at": iso(v["created_at"]),
    }


def build_item(row, vote, model_a, model_b, image_rel_paths):
    task = None
    if row.get("t_id") is not None:
        task = {
            "task_id": row["t_id"],
            "essay_title": row["t_essay_title"],
            "essay_content": row["t_essay_content"],
            "grade_level": row["t_grade_level"],
            "requirements": row["t_requirements"],
            "has_images": bool(row["t_has_images"]) if row["t_has_images"] is not None else None,
            "image_count": row["t_image_count"],
            "essay_images": image_rel_paths,
        }
    else:
        task = {"essay_images": image_rel_paths}

    return {
        "schema_version": SCHEMA_VERSION,
        "battle": {
            "battle_id": row["battle_id"],
            "status": row["status"],
            "match_type": row["match_type"],
            "display_order": row["display_order"],
            "created_at": iso(row["created_at"]),
            "winner": row["winner"],
            "error_message": row["error_message"],
        },
        "task": task,
        "model_a": model_brief(model_a),
        "model_b": model_brief(model_b),
        "responses": {
            "response_a": row["response_a"],
            "response_b": row["response_b"],
        },
        "vote": vote_brief(vote),
    }


# -------------------------- 主流程 --------------------------

def main():
    args = build_parser().parse_args()
    t_start = time.time()
    include_images = not args.no_images

    conn = new_conn(args)
    try:
        where_sql, params, filter_summary = build_battle_where(args, conn)
        battles, vote_map, model_map = load_all(conn, where_sql, params, args.limit)
    finally:
        conn.close()

    # 第一遍：写 data.jsonl（用临时 bytes buffer，规模通常只有十几 MB）+ 收集带图 task_id
    t0 = time.time()
    jsonl_buf = io.BytesIO()
    task_ids_with_images = []  # 保持顺序
    seen_task = set()
    written_battles = 0
    dropped_dirty = 0  # 因脏数据（agent 调用失败降级 tie）被过滤的 battle 数
    dropped_dirty_samples = []  # 最多记录 5 条样本进 manifest，便于审计
    drop_dirty = not args.keep_dirty
    total = len(battles)
    progress_every = max(1, args.progress_every)

    for idx, row in enumerate(battles, start=1):
        battle_id = row["battle_id"]
        vote = vote_map.get(battle_id)

        # 脏数据过滤：agent-review-service LLM 调用失败时会写入 winner=tie + reason
        # 以 "LLM 评审失败，降级为 tie" 开头的兜底 vote，偏好信号不可信，训练集用不得。
        if drop_dirty and is_dirty_vote(vote):
            dropped_dirty += 1
            if len(dropped_dirty_samples) < 5:
                # 记录一个能定位到具体错因的样本：battle_id + 一段 reason 片段
                sample_reason = ""
                for f in _REASON_FIELDS:
                    v = vote.get(f) if vote else None
                    if v and any(m in v for m in _DIRTY_REASON_MARKERS):
                        sample_reason = v[:120]
                        break
                dropped_dirty_samples.append({
                    "battle_id": battle_id,
                    "vote_id": vote["id"] if vote else None,
                    "reason_excerpt": sample_reason,
                })
            if idx % progress_every == 0 or idx == total:
                elapsed = time.time() - t0
                print(f"  [jsonl] {idx}/{total} kept={written_battles} dirty={dropped_dirty} "
                      f"elapsed={elapsed:.1f}s", flush=True)
            continue

        # 计算 essay_images 相对路径（与 Java 版 computeImageRelPathsByCount 一致：统一用 .jpg，
        # 真实后缀在第二遍解码时按魔数覆写；jsonl 里的后缀不强求精确，消费方按 task_%d/%02d.* 匹配）
        n = row.get("t_image_count") or 0
        has = bool(row.get("t_has_images"))
        task_id = row.get("t_id")
        if has and n > 0 and task_id is not None:
            image_rel_paths = [f"images/task_{task_id}/{i+1:02d}.jpg" for i in range(n)]
            if include_images and task_id not in seen_task:
                task_ids_with_images.append(task_id)
                seen_task.add(task_id)
        else:
            image_rel_paths = []

        item = build_item(row, vote,
                          model_map.get(row["model_a_id"]),
                          model_map.get(row["model_b_id"]),
                          image_rel_paths)
        jsonl_buf.write((json.dumps(item, ensure_ascii=False) + "\n").encode("utf-8"))
        written_battles += 1

        if idx % progress_every == 0 or idx == total:
            elapsed = time.time() - t0
            rate = idx / elapsed if elapsed > 0 else 0
            eta = (total - idx) / rate if rate > 0 else 0
            print(f"  [jsonl] {idx}/{total} kept={written_battles} dirty={dropped_dirty} "
                  f"elapsed={elapsed:.1f}s ETA={eta:.1f}s", flush=True)

    jsonl_bytes = jsonl_buf.getvalue()
    print(f"[导出] data.jsonl 构建完成 battles_kept={written_battles} dropped_dirty={dropped_dirty} "
          f"bytes={len(jsonl_bytes)} taskWithImages={len(task_ids_with_images)} "
          f"耗时={int((time.time()-t0)*1000)}ms")

    # 第二遍：并发拉 images_json，主线程按顺序解码+写 zip
    total_images = 0
    out_path = args.output
    os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)

    # ZIP_STORED：jar/已压缩图片再压缩没收益，还省 CPU
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
        zf.writestr("data.jsonl", jsonl_bytes)

        if include_images and task_ids_with_images:
            img_conc = max(1, args.image_concurrency)
            print(f"[导出] 开始并发拉取 {len(task_ids_with_images)} 个 task 的 images_json "
                  f"concurrency={img_conc} ...")
            t_img = time.time()
            done_cnt = 0
            with ThreadPoolExecutor(max_workers=img_conc,
                                    thread_name_prefix="img-fetch") as pool:
                futures = [pool.submit(fetch_images_json, args, tid)
                           for tid in task_ids_with_images]
                for idx, fut in enumerate(futures):
                    task_id = task_ids_with_images[idx]
                    try:
                        images_json = fut.result()
                    except Exception as e:
                        print(f"[WARN] 拉 task={task_id} images_json 失败: {e}", file=sys.stderr)
                        continue
                    b64_list = parse_images_json(images_json)
                    for i, b64 in enumerate(b64_list):
                        try:
                            bin_data = base64.b64decode(strip_base64_prefix(b64))
                        except Exception as e:
                            print(f"[WARN] base64 decode 失败 task={task_id} idx={i+1}: {e}",
                                  file=sys.stderr)
                            continue
                        name = f"images/task_{task_id}/{i+1:02d}.{detect_image_ext(b64)}"
                        zf.writestr(name, bin_data)
                        total_images += 1
                    done_cnt += 1
                    if done_cnt % 20 == 0 or done_cnt == len(futures):
                        elapsed = time.time() - t_img
                        rate = done_cnt / elapsed if elapsed > 0 else 0
                        eta = (len(futures) - done_cnt) / rate if rate > 0 else 0
                        print(f"  [images] {done_cnt}/{len(futures)} "
                              f"images_written={total_images} "
                              f"elapsed={elapsed:.1f}s ETA={eta:.1f}s", flush=True)
            print(f"[导出] 图片阶段完成 images={total_images} 耗时={int((time.time()-t_img))}s")

        manifest = {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "total_battles": written_battles,
            "total_images": total_images,
            "include_images": include_images,
            "filter": filter_summary,
            "source": "local_direct_mysql",  # 标记是本地直连导出（与服务器导出做区分）
            # 脏数据过滤审计信息
            "dirty_filter": {
                "enabled": drop_dirty,
                "rule": "drop vote whose dim_*_reason contains 'LLM 评审失败，降级为 tie' "
                        "(agent-review-service fallback on LLM failure)",
                "dropped_battles": dropped_dirty,
                "raw_battles_before_filter": len(battles),
                "samples": dropped_dirty_samples,
            },
        }
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

    size_mb = os.path.getsize(out_path) / 1024 / 1024
    total_s = time.time() - t_start
    print(f"\n[导出] ✅ 完成: {out_path}")
    print(f"       raw={len(battles)} kept={written_battles} dropped_dirty={dropped_dirty} "
          f"images={total_images} size={size_mb:.1f}MB 总耗时={total_s:.1f}s")


if __name__ == "__main__":
    main()
