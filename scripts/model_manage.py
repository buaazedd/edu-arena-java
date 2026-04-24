#!/usr/bin/env python3
"""
Edu-Arena 模型自动化管理脚本

==================== 子命令一览 ====================
默认（无参数）：执行下架 + 批量填充流程
  python3 scripts/model_manage.py

add-list：自定义新增模式（先做图片多模态测试，通过才调用平台接口添加）
  python3 scripts/model_manage.py add-list                    # 使用脚本内 EXTRA_MODEL_IDS
  python3 scripts/model_manage.py add-list <id1> <id2> ...    # 命令行直接传入 model_id 列表（覆盖 EXTRA_MODEL_IDS）

帮助：
  python3 scripts/model_manage.py help

==================== 默认流程步骤 ====================
 1. 登录获取 token
 2. 下架表现不佳的 active 模型（图片超时 / 不识别图片）
 3. 遍历候选新模型清单（CANDIDATE_MODELS），逐个：
    - 通过 /api/admin/models 添加
    - 立刻用本地图片 curl AiHubMix chat/completions 测试
    - 测试成功 → 保留，失败 → 通过 toggle 下架为 inactive
 4. 直到 active 模型数量达到目标（TARGET_ACTIVE_COUNT，默认 30）
 5. 输出汇总报告

==================== add-list 流程步骤 ====================
 1. 登录获取 token、加载本地测试图片
 2. 拉取现有模型 id 集合（已存在的直接跳过，不重复测试也不重复添加）
 3. 对列表中的每个 model_id：
    - 先调用 AiHubMix 做图片多模态测试
    - 测试通过 → 调用 /api/admin/models 添加；接口失败也单独记录
    - 测试失败 → 不添加，仅记录原因
 4. 输出 5 类汇总：候选数 / 已存在跳过 / 测试通过添加成功 / 测试通过添加失败 / 测试失败
"""
import json
import urllib.request
import urllib.error
import time
import base64
import os
import sys

try:
    import pymysql
    HAS_PYMYSQL = True
except ImportError:
    HAS_PYMYSQL = False

# ========== 配置 ==========
SERVER_BASE = "http://8.219.130.23:5001"
ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

AIHUBMIX_KEY = "sk-LEc0CxRia23Ti4NqA1Ee05Be8c1a41E09c25DbEa30Db080e"
AIHUBMIX_URL = "https://api.aihubmix.com/v1/chat/completions"

# MySQL（用于直接删除失败模型，因为平台没有 DELETE 接口）
MYSQL_CONF = dict(host='180.76.229.245', port=3306, user='root',
                  password='zyd123', database='edu_arena', charset='utf8mb4')

# 测试图片
TEST_IMAGE = "/Users/trentzhao/Documents/edu-arena-java/agent-review-service/resource/picture/chinese/0018.jpg"

# 超时设置
IMG_TIMEOUT = 90       # 图片测试超时 90s（平衡速度与容忍度）
TEXT_TIMEOUT = 30

TARGET_ACTIVE_COUNT = 30   # 目标 active 模型数量

# ========== 已确认不合格的 active 模型（下架） ==========
MODELS_TO_DEACTIVATE = {
    "gpt-5.4-pro":     "图片请求超时（120s+）",
    "gpt-5.2-high":    "图片请求超时（120s+）",
    "qwen3-235b-a22b": "成功但未识别图片（不支持 base64 图片输入）",
    "mimo-v2-pro":     "成功但未识别图片（不支持 base64 图片输入）",
}

# ========== 候选新模型清单（基于 AiHubMix 实际可用模型） ==========
# 按优先级排序，都是已知主流多模态模型
CANDIDATE_MODELS = [
    # === OpenAI 系 ===
    {"model_id": "gpt-4o",                    "name": "GPT-4o",                    "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,tools", "context_length": 128000,  "max_output": 16384},
    {"model_id": "gpt-4o-2024-11-20",         "name": "GPT-4o (2024-11-20)",       "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,tools", "context_length": 128000,  "max_output": 16384},
    {"model_id": "gpt-4o-mini",               "name": "GPT-4o mini",               "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,tools", "context_length": 128000,  "max_output": 16384},
    {"model_id": "gpt-4.1",                   "name": "GPT-4.1",                   "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,tools", "context_length": 1000000, "max_output": 32768},
    {"model_id": "gpt-4.1-mini",              "name": "GPT-4.1 mini",              "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,tools", "context_length": 1000000, "max_output": 32768},
    {"model_id": "gpt-5",                     "name": "GPT-5",                     "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,thinking", "context_length": 400000,  "max_output": 128000},
    {"model_id": "gpt-5-mini",                "name": "GPT-5 mini",                "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,thinking", "context_length": 400000,  "max_output": 128000},
    {"model_id": "gpt-5.1",                   "name": "GPT-5.1",                   "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,thinking", "context_length": 400000,  "max_output": 128000},
    {"model_id": "gpt-5.2",                   "name": "GPT-5.2",                   "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,thinking", "context_length": 400000,  "max_output": 128000},
    {"model_id": "gpt-5.4-mini",              "name": "GPT-5.4 mini",              "company": "OpenAI",   "input_modalities": "text,image", "features": "vision,thinking", "context_length": 400000,  "max_output": 128000},

    # === Anthropic 系 ===
    {"model_id": "claude-opus-4-7",           "name": "Claude Opus 4.7",           "company": "Anthropic", "input_modalities": "text,image", "features": "vision,thinking,tools", "context_length": 200000, "max_output": 32000},
    {"model_id": "claude-sonnet-4-0",         "name": "Claude Sonnet 4.0",         "company": "Anthropic", "input_modalities": "text,image", "features": "vision,tools",          "context_length": 200000, "max_output": 8192},
    {"model_id": "claude-opus-4-0",           "name": "Claude Opus 4.0",           "company": "Anthropic", "input_modalities": "text,image", "features": "vision,tools",          "context_length": 200000, "max_output": 8192},
    {"model_id": "claude-opus-4-1",           "name": "Claude Opus 4.1",           "company": "Anthropic", "input_modalities": "text,image", "features": "vision,tools",          "context_length": 200000, "max_output": 8192},
    {"model_id": "claude-3-5-sonnet-20240620", "name": "Claude 3.5 Sonnet",        "company": "Anthropic", "input_modalities": "text,image", "features": "vision,tools",          "context_length": 200000, "max_output": 8192},

    # === Google Gemini 系 ===
    {"model_id": "gemini-2.0-flash",          "name": "Gemini 2.0 Flash",          "company": "Google",   "input_modalities": "text,image,video", "features": "vision,tools",  "context_length": 1000000, "max_output": 8192},
    {"model_id": "gemini-2.5-flash-lite",     "name": "Gemini 2.5 Flash Lite",     "company": "Google",   "input_modalities": "text,image",       "features": "vision",        "context_length": 1000000, "max_output": 8192},
    {"model_id": "gemini-3-flash-preview",    "name": "Gemini 3 Flash Preview",    "company": "Google",   "input_modalities": "text,image,video", "features": "vision,thinking", "context_length": 1000000, "max_output": 8192},

    # === xAI 系 ===
    {"model_id": "grok-4-fast-reasoning",     "name": "Grok 4 Fast Reasoning",     "company": "xAI",      "input_modalities": "text,image", "features": "vision,thinking",       "context_length": 256000, "max_output": 8192},
    {"model_id": "grok-4-fast-non-reasoning", "name": "Grok 4 Fast",               "company": "xAI",      "input_modalities": "text,image", "features": "vision",                "context_length": 256000, "max_output": 8192},

    # === Qwen VL 系（多模态专用） ===
    {"model_id": "qwen3-vl-plus",             "name": "Qwen3 VL Plus",             "company": "Alibaba",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-flash",            "name": "Qwen3 VL Flash",            "company": "Alibaba",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-235b-a22b-instruct", "name": "Qwen3 VL 235B Instruct",  "company": "Alibaba",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-235b-a22b-thinking", "name": "Qwen3 VL 235B Thinking",  "company": "Alibaba",  "input_modalities": "text,image", "features": "vision,thinking", "context_length": 128000, "max_output": 8192},
    {"model_id": "qwen3-vl-30b-a3b-instruct", "name": "Qwen3 VL 30B Instruct",     "company": "Alibaba",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "Qwen/Qwen2.5-VL-72B-Instruct", "name": "Qwen2.5 VL 72B",         "company": "Alibaba",  "input_modalities": "text,image", "features": "vision",       "context_length": 32000,  "max_output": 8192},
    {"model_id": "Qwen/Qwen2.5-VL-32B-Instruct", "name": "Qwen2.5 VL 32B",         "company": "Alibaba",  "input_modalities": "text,image", "features": "vision",       "context_length": 32000,  "max_output": 8192},

    # === 智谱 GLM ===
    {"model_id": "cc-glm-5",                  "name": "GLM-5",                     "company": "Zhipu",    "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "cc-glm-5.1",                "name": "GLM-5.1",                   "company": "Zhipu",    "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "zai-glm-5-turbo",           "name": "GLM-5 Turbo",               "company": "Zhipu",    "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},

    # === 字节 Doubao ===
    # 注意：doubao-seed-2-0-pro/doubao-seed-1-8 纯文本OK图片也OK，只是之前被放 inactive
    # 这里我们倾向直接用 toggle 激活已有的而不是重新加

    # === 百度 ERNIE ===
    {"model_id": "ernie-4.5-turbo-vl",        "name": "ERNIE 4.5 Turbo VL",        "company": "Baidu",    "input_modalities": "text,image", "features": "vision",       "context_length": 32000,  "max_output": 8192},

    # === Kimi ===
    {"model_id": "Kimi-K2-0905",              "name": "Kimi K2 (0905)",            "company": "Moonshot", "input_modalities": "text,image", "features": "vision",       "context_length": 200000, "max_output": 8192},
    {"model_id": "kimi-k2-instruct",          "name": "Kimi K2 Instruct",          "company": "Moonshot", "input_modalities": "text,image", "features": "vision",       "context_length": 200000, "max_output": 8192},

    # === MiniMax ===
    {"model_id": "cc-minimax-m2",             "name": "MiniMax M2",                "company": "MiniMax",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
    {"model_id": "cc-minimax-m2.5",           "name": "MiniMax M2.5",              "company": "MiniMax",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},

    # === Step ===
    {"model_id": "step-3.5-flash",            "name": "Step 3.5 Flash",            "company": "StepFun",  "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},

    # === 小米 Mimo ===
    {"model_id": "xiaomi-mimo-v2.5-pro",      "name": "Mimo V2.5 Pro",             "company": "Xiaomi",   "input_modalities": "text,image", "features": "vision",       "context_length": 128000, "max_output": 8192},
]

# ========== 用户自定义新增清单（add-list 子命令使用） ==========
# 在这里维护要新增的模型 id 列表，逐个先做图片测试，OK 才会调用平台接口添加
# 元素可以是字符串（仅 model_id），也可以是完整 dict（带 name/company 等元数据）
EXTRA_MODEL_IDS = [
    # 示例：
    # "claude-haiku-4-5",
    # {"model_id": "gpt-4.1-nano", "name": "GPT-4.1 nano", "company": "OpenAI",
    #  "input_modalities": "text,image", "features": "vision", "context_length": 1000000, "max_output": 32768},
]

# ========== HTTP 工具 ==========
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
            body = {"raw": ""}
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

# ========== Platform API ==========
def login():
    code, body = http_post(f"{SERVER_BASE}/api/login",
                           {"username": ADMIN_USER, "password": ADMIN_PASS})
    if code != 200 or body.get("code") != 200:
        raise RuntimeError(f"登录失败: {body}")
    token = body["data"]["token"]
    print(f"✅ 登录成功")
    return token

def get_all_models(token):
    code, body = http_get(f"{SERVER_BASE}/api/admin/models",
                          {"Authorization": f"Bearer {token}"})
    if code != 200 or body.get("code") != 200:
        raise RuntimeError(f"获取模型失败: {body}")
    return body["data"]

def add_model(token, m):
    # Jackson 全局 SNAKE_CASE，因此入参字段使用 snake_case
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
    code, body = http_post(f"{SERVER_BASE}/api/admin/models",
                           payload,
                           {"Authorization": f"Bearer {token}"})
    return code, body

def toggle_model(token, model_db_id):
    """toggle 会在 active <-> inactive 之间切换"""
    code, body = http_post(f"{SERVER_BASE}/api/admin/models/{model_db_id}/toggle",
                           {},
                           {"Authorization": f"Bearer {token}"})
    return code, body


def delete_model_from_db(model_db_id):
    """直接从 MySQL 删除模型（平台无 DELETE 接口）"""
    if not HAS_PYMYSQL:
        return False, "pymysql 未安装"
    try:
        conn = pymysql.connect(**MYSQL_CONF)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM models WHERE id = %s", (model_db_id,))
        conn.commit()
        rows = cursor.rowcount
        cursor.close()
        conn.close()
        return rows > 0, f"deleted {rows} rows"
    except Exception as e:
        return False, str(e)

# ========== AiHubMix 图片测试 ==========
def test_model_with_image(model_id, image_b64):
    """直接 curl AiHubMix 接口用图片测试模型"""
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
        if isinstance(err, dict):
            err_msg = f"HTTP {code}: {err.get('message', str(err))[:150]}"
        else:
            err_msg = f"HTTP {code}: {str(err)[:150]}"
        return {"ok": False, "elapsed": elapsed, "error": err_msg, "content": ""}

    choices = body.get("choices", [])
    if not choices:
        return {"ok": False, "elapsed": elapsed, "error": "no choices", "content": ""}

    msg = choices[0].get("message", {})
    content = msg.get("content", "") or ""
    reasoning = msg.get("reasoning_content", "") or msg.get("reasoning", "") or ""

    # 判断图片识别是否真的有效
    effective = content or reasoning
    # 检查是否模型明确表示"没看到图片"
    not_recognized_keywords = [
        "未上传图片", "没有上传图片", "未提供图片", "没有图片",
        "没有看到图片", "不支持查看图片", "无法查看图片", "无法识别图片",
        "没有包含作文的图片", "未收到图片",
    ]
    lowered = (content + " " + reasoning)[:400]
    not_recognized = any(k in lowered for k in not_recognized_keywords)

    return {
        "ok": (not not_recognized) and bool(effective),
        "elapsed": elapsed,
        "error": "模型未识别到图片" if not_recognized else ("返回内容为空" if not effective else ""),
        "content": effective[:100],
    }

# ========== 主流程 ==========
def main():
    print("=" * 110)
    print("Edu-Arena 模型自动化管理")
    print("=" * 110)

    # 1) 登录
    token = login()
    auth_header = {"Authorization": f"Bearer {token}"}

    # 2) 加载测试图片
    print(f"\n📷 加载测试图片: {TEST_IMAGE}")
    with open(TEST_IMAGE, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    size_mb = os.path.getsize(TEST_IMAGE) / 1024 / 1024
    print(f"   大小: {size_mb:.1f} MB, base64 长度: {len(image_b64)}")

    # 3) 查询现有模型
    models = get_all_models(token)
    model_by_modelid = {m["model_id"]: m for m in models}
    active_count = sum(1 for m in models if m["status"] == "active")
    print(f"\n📋 当前模型: 总数 {len(models)}, active {active_count}, inactive {len(models) - active_count}")

    # 4) 下架表现不佳的 active 模型
    print("\n" + "=" * 110)
    print("🔻 第一阶段: 下架表现不佳的 active 模型")
    print("=" * 110)
    deactivated = []
    for mid, reason in MODELS_TO_DEACTIVATE.items():
        if mid not in model_by_modelid:
            print(f"  ⚠️  {mid} 不存在，跳过")
            continue
        m = model_by_modelid[mid]
        if m["status"] != "active":
            print(f"  ℹ️  {mid} 已是 inactive，跳过")
            continue
        code, body = toggle_model(token, m["id"])
        if code == 200 and body.get("code") == 200:
            print(f"  ✅ 下架 {mid} (id={m['id']}) — 原因: {reason}")
            deactivated.append(mid)
        else:
            print(f"  ❌ 下架失败 {mid}: {body}")

    # 5) 刷新现有模型信息
    models = get_all_models(token)
    model_by_modelid = {m["model_id"]: m for m in models}
    active_count = sum(1 for m in models if m["status"] == "active")
    print(f"\n📋 下架后: 总数 {len(models)}, active {active_count}")

    # 6) 逐个添加 & 测试新模型
    print("\n" + "=" * 110)
    print(f"➕ 第二阶段: 添加并测试新候选模型 (目标 active = {TARGET_ACTIVE_COUNT})")
    print("=" * 110)

    added_success = []   # [(model_id, elapsed, content_preview)]
    added_failed = []    # [(model_id, reason)]
    skipped_exists = []  # 已存在

    for i, cand in enumerate(CANDIDATE_MODELS, 1):
        mid = cand["model_id"]

        # 检查当前 active 数量
        if active_count >= TARGET_ACTIVE_COUNT:
            print(f"\n🎯 已达到目标 active 数量 {TARGET_ACTIVE_COUNT}，停止添加")
            break

        print(f"\n[{i:02d}/{len(CANDIDATE_MODELS)}] 处理 {mid} (当前 active={active_count})")

        # 如果已存在
        if mid in model_by_modelid:
            existing = model_by_modelid[mid]
            print(f"  ℹ️  已存在于数据库 (id={existing['id']}, status={existing['status']})")
            if existing["status"] == "inactive":
                # 先做图片测试决定是否激活
                print(f"  🔬 图片测试中...")
                result = test_model_with_image(mid, image_b64)
                if result["ok"]:
                    # 激活
                    code, body = toggle_model(token, existing["id"])
                    if code == 200 and body.get("code") == 200:
                        print(f"  ✅ 图片OK ({result['elapsed']:.1f}s)，已重新激活")
                        added_success.append((mid, result["elapsed"], result["content"]))
                        active_count += 1
                    else:
                        print(f"  ⚠️  激活失败: {body}")
                else:
                    print(f"  ❌ 图片测试失败: {result['error']}")
                    added_failed.append((mid, result["error"]))
            else:
                skipped_exists.append(mid)
            continue

        # 步骤1：添加模型
        code, body = add_model(token, cand)
        if code != 200 or body.get("code") != 200:
            err = body.get("message") if isinstance(body, dict) else str(body)
            print(f"  ❌ 添加失败: {err}")
            added_failed.append((mid, f"添加失败: {err}"))
            continue
        print(f"  ✅ 已添加")

        # 刷新获取新加入模型的 id
        new_models = get_all_models(token)
        new_model = next((m for m in new_models if m["model_id"] == mid), None)
        if not new_model:
            print(f"  ⚠️  添加后找不到，跳过")
            added_failed.append((mid, "添加后查不到"))
            continue

        # 步骤2：图片测试
        print(f"  🔬 图片测试中 (timeout={IMG_TIMEOUT}s)...")
        result = test_model_with_image(mid, image_b64)

        if result["ok"]:
            preview = result["content"].replace("\n", " ")[:60]
            print(f"  ✅ 测试通过 ({result['elapsed']:.1f}s) -> {preview}")
            added_success.append((mid, result["elapsed"], result["content"]))
            active_count += 1   # 默认 active
        else:
            # 测试失败 → 直接从 MySQL 删除（保持数据库干净）
            print(f"  ❌ 测试失败: {result['error']}")
            ok, msg = delete_model_from_db(new_model["id"])
            if ok:
                print(f"     🗑️  已从数据库删除")
            else:
                # 删除失败则降级为 toggle inactive
                toggle_model(token, new_model["id"])
                print(f"     🔻 已下架为 inactive (MySQL删除失败: {msg})")
            added_failed.append((mid, result["error"]))

        # 防止频率过快
        time.sleep(0.5)

    # 7) 最终汇总
    final_models = get_all_models(token)
    final_active = [m for m in final_models if m["status"] == "active"]
    final_inactive = [m for m in final_models if m["status"] == "inactive"]

    print("\n" + "=" * 110)
    print("📊 最终汇总")
    print("=" * 110)
    print(f"\n  模型总数: {len(final_models)}")
    print(f"  Active:   {len(final_active)} ✅")
    print(f"  Inactive: {len(final_inactive)}")
    print(f"\n  第一阶段下架: {len(deactivated)} 个")
    for mid in deactivated:
        print(f"    - {mid}")

    print(f"\n  新增成功（已 active）: {len(added_success)} 个")
    for mid, elapsed, preview in added_success:
        p = preview.replace("\n", " ")[:50]
        print(f"    ✅ {mid:<42} {elapsed:>6.1f}s  -> {p}")

    print(f"\n  新增失败: {len(added_failed)} 个")
    for mid, reason in added_failed:
        print(f"    ❌ {mid:<42} {reason[:100]}")

    if skipped_exists:
        print(f"\n  已存在跳过: {len(skipped_exists)} 个")
        for mid in skipped_exists:
            print(f"    - {mid}")

    print(f"\n  最终 active 模型列表 ({len(final_active)}):")
    for m in sorted(final_active, key=lambda x: x["id"]):
        print(f"    [{m['id']:>3}] {m['model_id']:<42} ({m.get('company','') or '-'})")

    if len(final_active) >= TARGET_ACTIVE_COUNT:
        print(f"\n🎉 目标达成: active 模型 = {len(final_active)} >= {TARGET_ACTIVE_COUNT}")
    else:
        print(f"\n⚠️  未达目标: active 模型 = {len(final_active)} < {TARGET_ACTIVE_COUNT}，候选池已耗尽")


# ========== 子命令：按指定 id 列表新增（先测试图片→OK 才添加） ==========
def _normalize_extra_item(item):
    """把字符串或部分 dict 标准化为 add_model 需要的完整 dict。"""
    if isinstance(item, str):
        return {
            "model_id": item,
            "name": item,
            "company": "",
            "input_modalities": "text,image",
            "features": "vision",
            "context_length": None,
            "max_output": None,
        }
    if isinstance(item, dict) and "model_id" in item:
        d = dict(item)
        d.setdefault("name", d["model_id"])
        d.setdefault("company", "")
        d.setdefault("input_modalities", "text,image")
        d.setdefault("features", "vision")
        d.setdefault("context_length", None)
        d.setdefault("max_output", None)
        return d
    raise ValueError(f"无法识别的 EXTRA 模型项: {item!r}")


def run_add_from_list(extra_list):
    """
    专用流程：对外部传入的模型 id 列表
      1) 跳过已存在于数据库的 model_id；
      2) 直接用 AiHubMix 做图片多模态测试；
      3) 测试通过 → 调用 /api/admin/models 添加；测试失败 → 不添加；
      4) 添加后再次确认存在；
      5) 输出汇总报告。
    """
    print("=" * 110)
    print("Edu-Arena 模型自动化管理 — 自定义新增模式 (add-list)")
    print("=" * 110)

    if not extra_list:
        print("⚠️  EXTRA 列表为空，请在 EXTRA_MODEL_IDS 或命令行参数中提供 model_id")
        return

    # 标准化输入
    candidates = []
    for raw in extra_list:
        try:
            candidates.append(_normalize_extra_item(raw))
        except ValueError as e:
            print(f"  ⚠️  忽略非法项: {e}")

    print(f"\n📋 计划新增 {len(candidates)} 个模型: {[c['model_id'] for c in candidates]}")

    # 1) 登录
    token = login()

    # 2) 加载测试图片
    print(f"\n📷 加载测试图片: {TEST_IMAGE}")
    with open(TEST_IMAGE, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")
    size_mb = os.path.getsize(TEST_IMAGE) / 1024 / 1024
    print(f"   大小: {size_mb:.1f} MB, base64 长度: {len(image_b64)}")

    # 3) 现有模型快照，用于"已存在"判断
    existing_models = get_all_models(token)
    existing_ids = {m["model_id"] for m in existing_models}
    print(f"\n📋 当前数据库已有 {len(existing_models)} 个模型")

    # 4) 逐个处理
    print("\n" + "=" * 110)
    print(f"🔬 逐个先测试图片，通过才添加")
    print("=" * 110)

    test_passed_added = []   # [(mid, elapsed, preview)]
    test_passed_add_failed = []  # [(mid, err)]    测试通过但添加接口失败
    test_failed = []         # [(mid, err)]
    skipped_exists = []      # [mid]

    for i, cand in enumerate(candidates, 1):
        mid = cand["model_id"]
        print(f"\n[{i:02d}/{len(candidates)}] {mid}")

        # a) 已存在则跳过（不重复添加，也不重复测试）
        if mid in existing_ids:
            print(f"  ℹ️  已存在于数据库，跳过")
            skipped_exists.append(mid)
            continue

        # b) 先做图片测试
        print(f"  🔬 图片测试中 (timeout={IMG_TIMEOUT}s)...")
        result = test_model_with_image(mid, image_b64)

        if not result["ok"]:
            print(f"  ❌ 图片测试不通过: {result['error']}  (耗时 {result['elapsed']:.1f}s)")
            test_failed.append((mid, result["error"]))
            continue

        preview = result["content"].replace("\n", " ")[:60]
        print(f"  ✅ 图片测试通过 ({result['elapsed']:.1f}s) -> {preview}")

        # c) 调用平台接口添加
        code, body = add_model(token, cand)
        if code != 200 or body.get("code") != 200:
            err = body.get("message") if isinstance(body, dict) else str(body)
            print(f"  ⚠️  测试通过但平台添加失败: {err}")
            test_passed_add_failed.append((mid, str(err)[:120]))
            continue

        print(f"  ✅ 已通过平台接口添加")
        test_passed_added.append((mid, result["elapsed"], result["content"]))
        existing_ids.add(mid)

        # 防止频率过快
        time.sleep(0.5)

    # 5) 汇总
    final_models = get_all_models(token)
    final_active = [m for m in final_models if m["status"] == "active"]

    print("\n" + "=" * 110)
    print("📊 add-list 汇总")
    print("=" * 110)
    print(f"  输入候选:       {len(candidates)}")
    print(f"  已存在跳过:     {len(skipped_exists)}")
    print(f"  图片测试通过:   {len(test_passed_added) + len(test_passed_add_failed)}")
    print(f"    └─ 添加成功: {len(test_passed_added)} ✅")
    print(f"    └─ 添加失败: {len(test_passed_add_failed)}")
    print(f"  图片测试失败:   {len(test_failed)} ❌")
    print(f"  当前数据库 active 总数: {len(final_active)}")

    if test_passed_added:
        print(f"\n  ✅ 新增成功 ({len(test_passed_added)}):")
        for mid, elapsed, preview in test_passed_added:
            p = preview.replace("\n", " ")[:50]
            print(f"     {mid:<42} {elapsed:>6.1f}s  -> {p}")

    if test_passed_add_failed:
        print(f"\n  ⚠️  测试通过但添加失败 ({len(test_passed_add_failed)}):")
        for mid, err in test_passed_add_failed:
            print(f"     {mid:<42} {err}")

    if test_failed:
        print(f"\n  ❌ 图片测试失败 ({len(test_failed)}):")
        for mid, err in test_failed:
            print(f"     {mid:<42} {err[:100]}")

    if skipped_exists:
        print(f"\n  ℹ️  已存在跳过 ({len(skipped_exists)}):")
        for mid in skipped_exists:
            print(f"     {mid}")


def _print_usage():
    print("""用法:
  python3 scripts/model_manage.py                      # 默认主流程：下架问题模型 + 用 CANDIDATE_MODELS 填充到目标 active 数
  python3 scripts/model_manage.py add-list             # 使用脚本中 EXTRA_MODEL_IDS 列表，先测试图片→通过才添加
  python3 scripts/model_manage.py add-list <id1> <id2> # 直接命令行传 model_id（覆盖 EXTRA_MODEL_IDS）
  python3 scripts/model_manage.py help                 # 打印用法
""")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        main()
    elif args[0] in ("help", "-h", "--help"):
        _print_usage()
    elif args[0] == "add-list":
        cli_ids = args[1:]
        run_add_from_list(cli_ids if cli_ids else EXTRA_MODEL_IDS)
    else:
        print(f"⚠️  未知子命令: {args[0]}")
        _print_usage()
        sys.exit(1)
