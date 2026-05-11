#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
清理 agent-review-service 因 LLM 调用失败（如 401 `this key is not enabled` / 限流 /
超时等）触发 `dimension_agent._fallback_score` 兜底而产生的"假 tie"评审记录。

覆盖的所有表 & 缓存（按依赖顺序）：
  1. quality_logs    —— 外键 vote_id，先删
  2. elo_history     —— 外键 battle_id，删对应 battle 的全部 elo 条目（1 场对战 = 2 条）
  3. votes           —— 删命中的假 tie 投票
  4. battles         —— 无残留投票的 battle 回退到 ready、清空 winner（保留 response_a/b）
  5. models          —— 按 elo_history 剩余最新一条回滚 elo_score（无历史则 1500.00）
                       同步基于 votes 实时重算 total_matches / win_count / lose_count / tie_count
  6. Redis           —— 同步清理与上述变化相关的所有缓存键，并把 total_votes 计数器按实际
                       删除数 DECRBY 回去

essay_images / tasks 不触碰（多 battle 共享一个 task，数据污染范围与它们无关）。

默认 dry-run（事务最后 rollback）；加 `--apply` 才真正写库。

典型用法：
    # 只看统计
    python3 scripts/cleanup_failed_reviews.py --stats-only

    # dry-run（不写库，不动 Redis）
    python3 scripts/cleanup_failed_reviews.py

    # 真实清理
    python3 scripts/cleanup_failed_reviews.py --apply

可选参数：
    --pattern "xxx"          自定义额外匹配的 reason 片段（可多次传）
    --battle-status-to ready|failed   battle 回退后的目标状态（默认 ready）
    --keep-battles           只删 votes/elo_history/quality_logs，不回退 battles 状态
    --no-recompute-elo       不回滚 models.elo_score / 计数字段
    --no-redis               不清理 Redis 缓存
"""
from __future__ import annotations

import argparse
import sys
from decimal import Decimal
from typing import Iterable

import pymysql
from pymysql.cursors import DictCursor

# --- 数据库 & Redis 连接配置（与线上 application.yml 保持一致）-----------------
DB_CONFIG = dict(
    host="180.76.229.245",
    port=3306,
    user="root",
    password="zyd123",
    database="edu_arena",
    charset="utf8mb4",
    autocommit=False,
    cursorclass=DictCursor,
)

REDIS_CONFIG = dict(
    host="180.76.229.245",
    port=6379,
    password="zyd123",
    db=0,
)

# 默认识别的降级/失败文案片段（来自 dimension_agent._fallback_score 与常见错误）
DEFAULT_PATTERNS = [
    "LLM 评审失败，降级为 tie",
    "LLM评审失败，降级为tie",
    "this key is not enabled",
    "quota exhausted",
    "rate limit",
    "Connection error",
    "降级为tie",
    "降级为 tie",
]

# votes 表中所有带 reason 的维度
DIM_REASON_COLUMNS = [
    "dim_theme_reason",
    "dim_imagination_reason",
    "dim_logic_reason",
    "dim_language_reason",
    "dim_writing_reason",
    "dim_overall_reason",
]

DEFAULT_ELO = Decimal("1500.00")

# =============================================================================


def build_like_clause(patterns: list[str]) -> tuple[str, list[str]]:
    """构造 (SQL where 子句, 参数列表)，跨所有 dim_*_reason OR 任一命中。"""
    ors: list[str] = []
    params: list[str] = []
    for col in DIM_REASON_COLUMNS:
        for p in patterns:
            ors.append(f"{col} LIKE %s")
            params.append(f"%{p}%")
    return "(" + " OR ".join(ors) + ")", params


def fetch_hit_votes(cur, where_clause: str, params: list[str]) -> list[dict]:
    cur.execute(
        f"SELECT id, battle_id FROM votes WHERE {where_clause}",
        params,
    )
    return cur.fetchall()


def print_stats(cur, where_clause: str, params: list[str]) -> None:
    cur.execute(f"SELECT COUNT(*) AS n FROM votes WHERE {where_clause}", params)
    hit_votes = cur.fetchone()["n"]

    cur.execute(
        f"SELECT COUNT(DISTINCT battle_id) AS n FROM votes WHERE {where_clause}",
        params,
    )
    hit_battles = cur.fetchone()["n"]

    cur.execute("SELECT COUNT(*) AS n FROM votes")
    total_votes = cur.fetchone()["n"]

    cur.execute("SELECT status, COUNT(*) AS n FROM battles GROUP BY status")
    battle_status = {r["status"]: r["n"] for r in cur.fetchall()}

    print("=" * 60)
    print("  命中的假 tie 投票数  :", hit_votes)
    print("  涉及的 battle 数    :", hit_battles)
    print("  votes 总数           :", total_votes)
    print("  battles 状态分布     :", battle_status)
    print("=" * 60)


def recompute_model_stats(cur, model_ids: Iterable[int]) -> dict[int, tuple[Decimal, int, int, int, int]]:
    """按剩余 votes + elo_history 重算 models 表的 elo_score / 胜负计数，返回新值。"""
    result: dict[int, tuple[Decimal, int, int, int, int]] = {}
    for mid in model_ids:
        # 剩余 elo_history 最新一条
        cur.execute(
            "SELECT elo_score FROM elo_history WHERE model_id=%s "
            "ORDER BY recorded_at DESC, id DESC LIMIT 1",
            (mid,),
        )
        row = cur.fetchone()
        elo = row["elo_score"] if row else DEFAULT_ELO

        # 基于 votes 实时重算胜负计数
        # 某个 battle 里这个模型是 A 还是 B，决定 winner='A'/'B' 对它来说是 win 还是 lose
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN (b.model_a_id=%s AND v.winner='A')
                        OR (b.model_b_id=%s AND v.winner='B') THEN 1 ELSE 0 END) AS wins,
              SUM(CASE WHEN (b.model_a_id=%s AND v.winner='B')
                        OR (b.model_b_id=%s AND v.winner='A') THEN 1 ELSE 0 END) AS loses,
              SUM(CASE WHEN v.winner='tie' THEN 1 ELSE 0 END) AS ties,
              COUNT(*) AS total
            FROM votes v JOIN battles b ON v.battle_id=b.id
            WHERE b.model_a_id=%s OR b.model_b_id=%s
            """,
            (mid, mid, mid, mid, mid, mid),
        )
        s = cur.fetchone()
        wins = int(s["wins"] or 0)
        loses = int(s["loses"] or 0)
        ties = int(s["ties"] or 0)
        total = int(s["total"] or 0)

        cur.execute(
            "UPDATE models SET elo_score=%s, total_matches=%s, win_count=%s, "
            "lose_count=%s, tie_count=%s WHERE id=%s",
            (elo, total, wins, loses, ties, mid),
        )
        result[mid] = (elo, total, wins, loses, ties)
    return result


def clean_redis(redis_client, battle_ids: list[int], model_ids: list[int],
                deleted_votes: int) -> None:
    """清理与本次变更相关的所有 Redis 键。"""
    # 前缀与常量保持与 CacheService.java 一致
    LEADERBOARD_KEY = "edu_arena:leaderboard:all"
    ELO_HISTORY_KEY = "edu_arena:leaderboard:elo_history"
    ACTIVE_MODELS_KEY = "edu_arena:models:active"
    BATTLE_KEY_PREFIX = "edu_arena:battle:"
    MODEL_DETAIL_KEY_PREFIX = "edu_arena:model:detail:"
    API_MODEL_INFO_KEY_PREFIX = "edu_arena:api:model_info:"
    STATS_TOTAL_VOTES = "edu_arena:stats:total_votes"
    BATTLE_FALLBACK_PREFIX = "edu_arena:battle:fallback:"  # BattleServiceImpl 里用到

    keys: list[str] = [LEADERBOARD_KEY, ELO_HISTORY_KEY, ACTIVE_MODELS_KEY]

    for bid in battle_ids:
        keys.append(f"{BATTLE_KEY_PREFIX}{bid}")
        keys.append(f"{BATTLE_FALLBACK_PREFIX}{bid}")
    for mid in model_ids:
        keys.append(f"{MODEL_DETAIL_KEY_PREFIX}{mid}")
        keys.append(f"{API_MODEL_INFO_KEY_PREFIX}{mid}")

    removed = 0
    # 分批 delete，避免超大 pipeline
    CHUNK = 500
    for i in range(0, len(keys), CHUNK):
        batch = keys[i:i + CHUNK]
        removed += redis_client.delete(*batch)

    # 永久计数器：按实际删除投票数递减
    if deleted_votes > 0:
        try:
            redis_client.decrby(STATS_TOTAL_VOTES, deleted_votes)
        except Exception as e:
            print(f"[WARN] DECRBY {STATS_TOTAL_VOTES} 失败（忽略）: {e}")

    print(f"[redis] DELETE 命中键数 = {removed} / 发送键数 = {len(keys)}; "
          f"DECRBY {STATS_TOTAL_VOTES} -{deleted_votes}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true",
                        help="真实写库 & 清缓存；未指定则 dry-run（事务 rollback）")
    parser.add_argument("--stats-only", action="store_true",
                        help="只统计不做任何修改（即使加了 --apply 也不执行）")
    parser.add_argument("--pattern", action="append", default=[],
                        help="追加自定义识别文案（可多次）")
    parser.add_argument("--battle-status-to", default="ready",
                        choices=["ready", "failed"],
                        help="battle 回退后的目标状态，默认 ready")
    parser.add_argument("--keep-battles", action="store_true",
                        help="不回退 battles 状态")
    parser.add_argument("--no-recompute-elo", action="store_true",
                        help="不回滚 models 的 elo_score / 胜负计数")
    parser.add_argument("--no-redis", action="store_true",
                        help="不清理 Redis 缓存")
    args = parser.parse_args()

    patterns = list(DEFAULT_PATTERNS) + list(args.pattern)
    print(f"[config] patterns = {patterns}")
    print(f"[config] apply={args.apply} stats_only={args.stats_only} "
          f"battle_status_to={args.battle_status_to} keep_battles={args.keep_battles} "
          f"recompute_elo={not args.no_recompute_elo} redis={not args.no_redis}")

    conn = pymysql.connect(**DB_CONFIG)
    try:
        where_clause, params = build_like_clause(patterns)

        with conn.cursor() as cur:
            print_stats(cur, where_clause, params)
            if args.stats_only:
                return 0

            hit_votes = fetch_hit_votes(cur, where_clause, params)
            if not hit_votes:
                print("没有命中任何假 tie，直接退出。")
                return 0

            vote_ids = [r["id"] for r in hit_votes]
            battle_ids = sorted({r["battle_id"] for r in hit_votes})

            # 相关模型（用于事后回滚 elo / 重算计数 / 清缓存）
            cur.execute(
                f"SELECT DISTINCT model_a_id, model_b_id FROM battles "
                f"WHERE id IN ({','.join(['%s'] * len(battle_ids))})",
                battle_ids,
            )
            model_ids: set[int] = set()
            for r in cur.fetchall():
                model_ids.add(r["model_a_id"])
                model_ids.add(r["model_b_id"])

            # 1. quality_logs（外键 vote_id）
            cur.execute(
                f"DELETE FROM quality_logs WHERE vote_id IN "
                f"({','.join(['%s'] * len(vote_ids))})",
                vote_ids,
            )
            qlog_deleted = cur.rowcount

            # 2. elo_history（按 battle）
            cur.execute(
                f"DELETE FROM elo_history WHERE battle_id IN "
                f"({','.join(['%s'] * len(battle_ids))})",
                battle_ids,
            )
            elo_deleted = cur.rowcount

            # 3. votes
            cur.execute(
                f"DELETE FROM votes WHERE id IN "
                f"({','.join(['%s'] * len(vote_ids))})",
                vote_ids,
            )
            votes_deleted = cur.rowcount

            # 4. battles 回退（仅对删除投票后已无残留 vote 的 battle 回退）
            battle_status_changed = 0
            if not args.keep_battles:
                # 过滤出仍有残留 vote 的 battle（不动它们）
                cur.execute(
                    f"SELECT DISTINCT battle_id FROM votes WHERE battle_id IN "
                    f"({','.join(['%s'] * len(battle_ids))})",
                    battle_ids,
                )
                still_have_votes = {r["battle_id"] for r in cur.fetchall()}
                rollback_battles = [b for b in battle_ids if b not in still_have_votes]

                if rollback_battles:
                    cur.execute(
                        f"UPDATE battles SET status=%s, winner=NULL "
                        f"WHERE id IN ({','.join(['%s'] * len(rollback_battles))})",
                        [args.battle_status_to] + rollback_battles,
                    )
                    battle_status_changed = cur.rowcount

            # 5. models（ELO 回滚 + 计数重算）
            model_updates: dict[int, tuple] = {}
            if not args.no_recompute_elo and model_ids:
                model_updates = recompute_model_stats(cur, model_ids)

            # ---- 打印变更摘要 ----
            print()
            print("----- 变更摘要 -----")
            print(f"  quality_logs 删除   : {qlog_deleted}")
            print(f"  elo_history  删除   : {elo_deleted}")
            print(f"  votes        删除   : {votes_deleted}")
            print(f"  battles 状态回退    : {battle_status_changed} "
                  f"-> {args.battle_status_to}")
            print(f"  models 重算数       : {len(model_updates)}")
            if model_updates:
                for mid, (elo, tot, w, l, t) in list(model_updates.items())[:10]:
                    print(f"    model#{mid}: elo={elo} matches={tot} W/L/T={w}/{l}/{t}")
                if len(model_updates) > 10:
                    print(f"    ... 其余 {len(model_updates) - 10} 个省略")

            if args.apply:
                conn.commit()
                print("[db] COMMIT ✅")
            else:
                conn.rollback()
                print("[db] ROLLBACK（dry-run；加 --apply 才会真实写入）")
                return 0

        # ---- 清 Redis（仅在 --apply 成功 commit 后执行）----
        if not args.no_redis:
            try:
                import redis  # 延迟导入，dry-run 下不需要依赖
            except ImportError:
                print("[WARN] 未安装 redis 包，跳过缓存清理。可执行： pip install redis")
                return 0
            try:
                r = redis.Redis(**REDIS_CONFIG)
                r.ping()
                clean_redis(r, battle_ids, sorted(model_ids), votes_deleted)
            except Exception as e:
                print(f"[WARN] Redis 清理失败（DB 已提交，不影响数据一致性）: {e}")

        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
