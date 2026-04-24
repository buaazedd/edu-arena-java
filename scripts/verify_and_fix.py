#!/usr/bin/env python3
"""
验证 active 模型的图片能力 + 补充替换失败模型
- 对上次脚本跳过的 6 个模型（已存在 active）做图片测试
- 测试失败 → 从数据库删除
- 不足 30 → 从备用池继续补充
"""
import json
import urllib.request
import urllib.error
import time
import base64
import os
import pymysql

SERVER_BASE = "http://8.219.130.23:5001"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
AIHUBMIX_KEY = "sk-LEc0CxRia23Ti4NqA1Ee05Be8c1a41E09c25DbEa30Db080e"
AIHUBMIX_URL = "https://api.aihubmix.com/v1/chat/completions"
TEST_IMAGE = "/Users/trentzhao/Documents/edu-arena-java/agent-review-service/resource/picture/chinese/0018.jpg"
IMG_TIMEOUT = 90
TARGET = 30
MYSQL_CONF = dict(host='180.76.229.245', port=3306, user='root',
                  password='zyd123', database='edu_arena', charset='utf8mb4')

# 需要补测的模型（上次脚本识别为"已存在跳过"的）
MODELS_TO_VERIFY = [
    "gpt-4o", "gpt-4o-2024-11-20", "gpt-4o-mini",
    "gpt-4.1", "gpt-4.1-mini", "gpt-5",
]

# 备用候选池（如果有模型测试失败，从这里补充）
BACKUP_POOL = [
    {"model_id": "qwen3-vl-plus",                "name": "Qwen3 VL Plus",         "company": "Alibaba",  "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-flash",               "name": "Qwen3 VL Flash",        "company": "Alibaba",  "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-235b-a22b-instruct",  "name": "Qwen3 VL 235B",         "company": "Alibaba",  "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-235b-a22b-thinking",  "name": "Qwen3 VL 235B Thinking","company": "Alibaba",  "input_modalities": "text,image", "features": "vision,thinking", "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-30b-a3b-instruct",    "name": "Qwen3 VL 30B",          "company": "Alibaba",  "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "Qwen/Qwen2.5-VL-72B-Instruct", "name": "Qwen2.5 VL 72B",        "company": "Alibaba",  "input_modalities": "text,image", "features": "vision", "context_length": 32000,  "max_output": 8192},
    {"model_id": "Qwen/Qwen2.5-VL-32B-Instruct", "name": "Qwen2.5 VL 32B",        "company": "Alibaba",  "input_modalities": "text,image", "features": "vision", "context_length": 32000,  "max_output": 8192},
    {"model_id": "cc-glm-5",                     "name": "GLM-5",                 "company": "Zhipu",    "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "cc-glm-5.1",                   "name": "GLM-5.1",               "company": "Zhipu",    "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "zai-glm-5-turbo",              "name": "GLM-5 Turbo",           "company": "Zhipu",    "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "ernie-4.5-turbo-vl",           "name": "ERNIE 4.5 Turbo VL",    "company": "Baidu",    "input_modalities": "text,image", "features": "vision", "context_length": 32000,  "max_output": 8192},
    {"model_id": "step-3.5-flash",               "name": "Step 3.5 Flash",        "company": "StepFun",  "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "xiaomi-mimo-v2.5-pro",         "name": "Mimo V2.5 Pro",         "company": "Xiaomi",   "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "cc-minimax-m2.5",              "name": "MiniMax M2.5",          "company": "MiniMax",  "input_modalities": "text,image", "features": "vision", "context_length": 128000, "max_output": 8192},
    {"model_id": "Kimi-K2-0905",                 "name": "Kimi K2 0905",          "company": "Moonshot", "input_modalities": "text,image", "features": "vision", "context_length": 200000, "max_output": 8192},
    {"model_id": "grok-4-fast-non-reasoning",    "name": "Grok 4 Fast",           "company": "xAI",      "input_modalities": "text,image", "features": "vision", "context_length": 256000, "max_output": 8192},
]


def http_post(url, body, headers=None, timeout=30):
    data = json.dumps(body).encode("utf-8")
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8"))
        except:
            body = {}
        return e.code, body
    except Exception as e:
        return 0, {"error": f"{type(e).__name__}: {e}"}


def http_get(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        return 0, {"error": str(e)}


def login():
    code, body = http_post(f"{SERVER_BASE}/api/login",
                           {"username": ADMIN_USER, "password": ADMIN_PASS})
    return body["data"]["token"]


def get_models(token):
    code, body = http_get(f"{SERVER_BASE}/api/admin/models",
                          {"Authorization": f"Bearer {token}"})
    return body["data"]


def add_model(token, m):
    payload = {
        "model_id": m["model_id"],
        "name": m.get("name", m["model_id"]),
        "company": m.get("company", ""),
        "description": m.get("description", ""),
        "input_modalities": m.get("input_modalities", "text,image"),
        "features": m.get("features", ""),
        "context_length": m.get("context_length"),
        "max_output": m.get("max_output"),
    }
    return http_post(f"{SERVER_BASE}/api/admin/models",
                     payload,
                     {"Authorization": f"Bearer {token}"})


def delete_model_from_db(model_db_id):
    try:
        conn = pymysql.connect(**MYSQL_CONF)
        cur = conn.cursor()
        cur.execute("DELETE FROM models WHERE id = %s", (model_db_id,))
        conn.commit()
        r = cur.rowcount
        cur.close()
        conn.close()
        return r > 0
    except Exception as e:
        print(f"   MySQL 删除异常: {e}")
        return False


def test_image(model_id, image_b64):
    payload = {
        "model": model_id,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": "你是中考语文阅卷专家。请识别图片中的手写作文内容并用1-2句话简要评价。"},
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
            ]
        }]
    }
    start = time.time()
    code, body = http_post(AIHUBMIX_URL, payload,
                           {"Authorization": f"Bearer {AIHUBMIX_KEY}"},
                           timeout=IMG_TIMEOUT)
    elapsed = time.time() - start

    if code != 200:
        err = body.get("error", body) if isinstance(body, dict) else body
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {"ok": False, "elapsed": elapsed, "error": f"HTTP {code}: {msg[:120]}", "content": ""}

    choices = body.get("choices", [])
    if not choices:
        return {"ok": False, "elapsed": elapsed, "error": "no choices", "content": ""}
    msg = choices[0].get("message", {})
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or msg.get("reasoning", "") or ""
    effective = content or reasoning

    not_recognized_keys = [
        "未上传图片", "没有上传图片", "未提供图片", "没有图片", "没有看到图片",
        "不支持查看图片", "无法查看图片", "无法识别图片", "没有包含作文的图片",
        "未收到图片", "抱歉，我无法", "I cannot see", "没有收到图片",
    ]
    scope = (content + " " + reasoning)[:500]
    not_recognized = any(k in scope for k in not_recognized_keys)

    return {
        "ok": (not not_recognized) and bool(effective),
        "elapsed": elapsed,
        "error": "未识别图片" if not_recognized else ("返回空" if not effective else ""),
        "content": effective[:100],
    }


def main():
    print("=" * 100)
    print("验证 + 补充 Phase")
    print("=" * 100)

    token = login()
    print("✅ 登录")

    # 加载图片
    with open(TEST_IMAGE, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    print(f"📷 图片加载完成 ({os.path.getsize(TEST_IMAGE)/1024/1024:.1f}MB)")

    models = get_models(token)
    model_map = {m["model_id"]: m for m in models}
    active_count = sum(1 for m in models if m["status"] == "active")
    print(f"📋 初始: 总数 {len(models)}, active {active_count}\n")

    # === 阶段 1: 补测 6 个模型 ===
    print("=" * 100)
    print("🔬 阶段1: 补测未经图片验证的模型")
    print("=" * 100)
    failed_models = []
    for mid in MODELS_TO_VERIFY:
        if mid not in model_map:
            print(f"  ⚠️  {mid} 不在数据库，跳过")
            continue
        m = model_map[mid]
        if m["status"] != "active":
            print(f"  ℹ️  {mid} 已非 active，跳过")
            continue
        print(f"  🔬 测试 {mid} (id={m['id']}) ...", end=" ", flush=True)
        r = test_image(mid, image_b64)
        if r["ok"]:
            preview = r["content"].replace("\n", " ")[:50]
            print(f"✅ {r['elapsed']:.1f}s -> {preview}")
        else:
            print(f"❌ {r['elapsed']:.1f}s {r['error']}")
            # 删除
            if delete_model_from_db(m["id"]):
                print(f"     🗑️  已删除 (id={m['id']})")
                failed_models.append(mid)
                active_count -= 1
            else:
                print(f"     ⚠️  删除失败")

    print(f"\n  当前 active: {active_count}")
    print(f"  需补充: {max(0, TARGET - active_count)} 个")

    # === 阶段 2: 补充模型到 30 ===
    if active_count < TARGET:
        print("\n" + "=" * 100)
        print(f"➕ 阶段2: 从备用池补充模型 (目标 {TARGET})")
        print("=" * 100)

        # 刷新模型列表
        models = get_models(token)
        existing = {m["model_id"] for m in models}

        added_success = []
        added_failed = []

        for cand in BACKUP_POOL:
            if active_count >= TARGET:
                break
            mid = cand["model_id"]

            if mid in existing:
                print(f"  ℹ️  {mid} 已存在，跳过")
                continue

            print(f"  ➕ 尝试 {mid}")
            code, body = add_model(token, cand)
            if code != 200 or body.get("code") != 200:
                err = body.get("message") if isinstance(body, dict) else body
                print(f"     ❌ 添加失败: {err}")
                added_failed.append((mid, f"添加失败: {err}"))
                continue

            # 查找新添加的模型 id
            new_models = get_models(token)
            new_m = next((x for x in new_models if x["model_id"] == mid), None)
            if not new_m:
                print(f"     ⚠️  找不到新增模型")
                continue

            # 图片测试
            print(f"     🔬 图片测试中...", end=" ", flush=True)
            r = test_image(mid, image_b64)
            if r["ok"]:
                preview = r["content"].replace("\n", " ")[:50]
                print(f"✅ {r['elapsed']:.1f}s -> {preview}")
                added_success.append((mid, r["elapsed"]))
                active_count += 1
            else:
                print(f"❌ {r['elapsed']:.1f}s {r['error']}")
                if delete_model_from_db(new_m["id"]):
                    print(f"        🗑️  已删除")
                added_failed.append((mid, r["error"]))
            time.sleep(0.3)

    # === 最终汇总 ===
    models = get_models(token)
    active = [m for m in models if m["status"] == "active"]
    inactive = [m for m in models if m["status"] == "inactive"]

    print("\n" + "=" * 100)
    print("📊 最终状态")
    print("=" * 100)
    print(f"\n  模型总数: {len(models)}")
    print(f"  Active:   {len(active)}")
    print(f"  Inactive: {len(inactive)}")

    if failed_models:
        print(f"\n  补测中下架/删除: {len(failed_models)}")
        for m in failed_models:
            print(f"    - {m}")

    print(f"\n  最终 Active 列表 ({len(active)}):")
    by_company = {}
    for m in active:
        c = m.get("company") or "(未分类)"
        by_company.setdefault(c, []).append(m["model_id"])
    for c in sorted(by_company.keys()):
        print(f"    [{c}] ({len(by_company[c])})")
        for mid in by_company[c]:
            print(f"      - {mid}")

    print(f"\n{'🎉' if len(active)>=TARGET else '⚠️'} 最终 active 模型 = {len(active)} / 目标 {TARGET}")


if __name__ == "__main__":
    main()
