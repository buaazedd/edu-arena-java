# agent-review-service

> 面向 `edu-arena-java` 对战平台的 **Multi-Agent 作文批改评审服务** + **离线批量处理系统**。
> 独立 Python 子项目，默认端口 **8100**；不修改 Java 代码，仅通过 REST API 与对战平台交互。

## 一、项目定位

| 系统 | 作用 | 入口 |
| --- | --- | --- |
| 多智能体评审服务 | 代替人类专家，对两份 AI 批改做 6 维度评分 + 仲裁 + 投票映射 | FastAPI `http://localhost:8100` |
| 离线批量处理系统 | 读 JSONL 清单 → 创建对战 → 生成 → 调评审服务 → 投票 | `python -m batch.cli run` |

两个系统通过 `app/contracts/` 共享 Pydantic DTO，字段 snake_case 严格对齐 Java 端 `JacksonConfig`。

## 二、技术栈

| 类别 | 选型 |
| --- | --- |
| 运行时 | Python 3.11+ |
| Web 框架 | FastAPI + Uvicorn |
| Agent 编排 | LangGraph（DAG + `Send` API 并行 fan-out） |
| LLM | openai SDK（AiHubMix OpenAI 兼容网关） |
| RAG | ChromaDB（本地持久化）+ OpenAI Embedding（可降级为 hash 伪向量） |
| 数据建模 | Pydantic v2 |
| HTTP 客户端 | httpx（异步）+ tenacity（指数退避） |
| 任务状态 | SQLite（默认，零依赖） |
| 日志 | loguru（按天轮转 + 敏感字段脱敏） |

## 三、架构总览

```mermaid
flowchart LR
    subgraph Offline[离线批量 batch/]
      A[JSONL 清单] --> B[JsonlDatasetLoader]
      B --> C[BatchOrchestrator<br/>asyncio + Semaphore]
      C --> D[ArenaClient<br/>对战平台 HTTP]
      C --> E[ReviewClient]
      C --> G[SqliteTaskStore<br/>断点续跑]
    end

    D -->|login/create/generate/detail/vote| JAVA[(Java Arena :5001)]
    E -->|POST /api/review| REVIEW

    subgraph REVIEW[评审服务 FastAPI :8100]
      R0[/api/review] --> R1[LangGraph StateGraph]
      R1 --> P[preprocess 节点<br/>LLM要点抽取 + Skill + RAG]
      P --> DIM[6×dimension_agent<br/>并行 fan-out]
      DIM --> ARB[arbitrator 节点]
      ARB --> DEC[VoteMapper<br/>A/B → left/right]
      P -. retrieve .-> RAG[(ChromaDB<br/>rubric/exemplar/gold_case)]
      DIM -. tool_call .-> SKILL[Skill Registry<br/>6 个工具]
      DIM & ARB -. call .-> LLM[AiHubMix]
    end
```

### 六维度评分键

| 维度 | 键 | 作用 |
| --- | --- | --- |
| 主旨 | `theme` | 是否紧扣题意 |
| 想象 | `imagination` | 创意表现 |
| 逻辑 | `logic` | 结构与条理 |
| 语言 | `language` | 语言表达 |
| 书写 | `writing` | 书写规范 |
| 整体评价 | `overall` | **决定最终 winner** |

## 四、目录结构

```
agent-review-service/
├── app/
│   ├── main.py                    # FastAPI 入口
│   ├── settings.py                # pydantic-settings
│   ├── contracts/                 # 两系统共享契约（Pydantic）
│   │   ├── arena_dto.py           # 对战平台 5 个接口 DTO
│   │   ├── review_dto.py          # 评审服务对外 DTO (ReviewRequest/Response/VotePayload)
│   │   ├── review_models.py       # 内部领域模型 (DimensionScore/ReviewReport)
│   │   └── dataset_dto.py         # 离线清单 DatasetItem
│   ├── review/                    # 多智能体核心
│   │   ├── graph.py               # LangGraph 装配
│   │   ├── state.py               # GraphState TypedDict
│   │   ├── llm.py                 # OpenAI 兼容客户端（JSON mode + 多模态）
│   │   ├── prompts.py             # 各节点 prompt 模板
│   │   ├── decision.py            # VoteMapper (A/B→left/right)
│   │   ├── service.py             # ReviewService 外观
│   │   └── nodes/
│   │       ├── preprocess.py      # LLM 要点抽取 + Skill + RAG
│   │       ├── dispatch.py        # 6 路 Send fan-out
│   │       ├── dimension_agent.py # 单维度评审
│   │       └── arbitrator.py      # 仲裁 + 强约束
│   ├── rag/                       # ChromaDB 三集合
│   │   ├── store.py / retriever.py / embedding.py
│   │   └── seed/{rubric.md,exemplar.jsonl,gold_case.jsonl}
│   ├── skills/                    # 6 个本地工具 (BaseSkill + 注册表)
│   │   ├── text_stats / grammar_check / duplicate_detect
│   │   └── feedback_compare / coverage_analyzer / hallucination_check
│   ├── api/
│   │   ├── review_router.py       # /api/review, /api/health
│   │   └── admin_router.py        # /api/rag/seed, /rag/upsert, /rag/stats
│   └── common/                    # logger / exceptions / retry
├── batch/                         # 离线批量系统
│   ├── cli.py                     # `python -m batch.cli run`
│   ├── orchestrator.py            # 并发 + 断点续跑编排
│   ├── dataset_loader.py          # JSONL 加载
│   ├── image_encoder.py           # 本地/URL/base64 → 压缩 base64
│   ├── arena_client.py            # Java 平台 5 个接口封装
│   ├── review_client.py           # 调评审服务
│   ├── task_store.py              # SqliteTaskStore
│   └── vote_builder.py            # VotePayload → ArenaVoteRequest
├── scripts/
│   ├── init_rag.py                # 种子导入 RAG
│   ├── gen_dataset.py             # txt + 图片 → JSONL 清单生成
│   └── run_batch.sh               # 启评审服务 + 跑批一键脚本
├── resource/                      # 作文描述 txt 文件（人工评分 + 评语）
├── picture/                       # 作文原图（0001.jpg, 0002.jpg...）
├── tests/                         # pytest 骨架
├── data/
│   ├── sample_dataset.jsonl       # 示例清单
│   └── images/                    # 图片占位
├── requirements.txt
├── pyproject.toml
└── .env.example
```

## 五、快速开始

### 5.1 环境准备

```bash
cd agent-review-service

# 创建虚拟环境（推荐 Python 3.11）
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 按需修改：AI_API_KEY / ARENA_BASE_URL / ARENA_USERNAME / ARENA_PASSWORD
```

### 5.2 （可选）初始化 RAG

```bash
python scripts/init_rag.py --reset
```

或启动服务后调管理接口：`curl -X POST http://localhost:8100/api/rag/seed -d '{"reset":true}' -H 'Content-Type: application/json'`。

### 5.3 启动评审服务

```bash
python -m app.main
# 访问 http://localhost:8100/docs 查看 Swagger UI
curl http://localhost:8100/api/health
```

### 5.4 准备批量数据

批量评审需要两样输入：**作文图片**（放在 `picture/` 目录下）和**描述文件**（放在 `resource/` 目录下的 `.txt` 文件）。

#### 目录结构

```
agent-review-service/
├── picture/              # 作文图片（以序号命名）
│   ├── 0001.jpg
│   ├── 0002.jpg
│   └── ...
├── resource/             # 描述文件
│   └── essays.txt        # 每行一条：图片名 + 题目 + 评分 + 评语
└── data/
    └── dataset.jsonl     # ← 由脚本自动生成
```

#### txt 描述文件格式

每行一条记录，格式为：

```
<图片文件名> <作文题目/要求全文> <主旨分> <想象分> <逻辑分> <语言分> <书写分> <总分> <人工评语>
```

示例：

```
0001.jpg 读下面的材料，然后作文。一只蜗牛... 8 6 8 8 3 33 这篇作文以"生命的意义在于奔跑"为主题...
0002.jpg 请以"原来，我也很______"为题... 8 7 8 8 3 34 这篇记叙文以"泰山登顶"为载体...
```

> **解析规则**：脚本通过正则匹配连续 6 个数字来拆分题目、评分和评语。
> 评分对应六维度：theme(主旨) / imagination(想象) / logic(逻辑) / language(语言) / writing(书写) / total(总分)。

#### 生成 JSONL 清单

```bash
# 默认：自动扫描 resource/*.txt + picture/ → data/dataset.jsonl
python scripts/gen_dataset.py

# 指定文件和路径
python scripts/gen_dataset.py \
  --txt resource/essays.txt \
  --pictures picture/ \
  --output data/dataset.jsonl \
  --grade 初中

# 多个 txt 文件合并
python scripts/gen_dataset.py \
  --txt resource/batch1.txt resource/batch2.txt \
  --output data/all_essays.jsonl
```

脚本会自动：
1. 从 txt 每行提取图片文件名、作文题目、6 维评分、人工评语
2. 智能提取短标题（识别书名号 `《》`、`"以...为题"` 等模式）
3. 关联 `picture/` 下的图片（支持直接放文件或按 item_id 子目录组织）
4. 将人工评分写入 `metadata.human_scores`，人工评语写入 `metadata.human_comment`
5. 输出完全兼容 `DatasetItem` 格式的 JSONL

生成的 JSONL 示例：

```json
{
  "item_id": "essay-0001",
  "essay_title": "原来，我也很______",
  "images": [{"kind": "local", "path": "/path/to/picture/0001.jpg"}],
  "grade_level": "初中",
  "requirements": "阅读下面文字，按要求作文...",
  "metadata": {
    "source": "txt-import",
    "image_filename": "0001.jpg",
    "human_scores": {"theme": 8, "imagination": 7, "logic": 8, "language": 8, "writing": 3, "total": 34},
    "human_comment": "这篇记叙文以..."
  }
}
```

### 5.5 启动批量评审

批量评审系统需要 **两个进程协作**：评审服务（Multi-Agent LangGraph）+ 批量编排器（CLI）。

#### 方式一：手动分步启动（推荐调试时使用）

```bash
# ---- 终端 1：启动 Multi-Agent 评审服务 ----
cd agent-review-service
source .venv/bin/activate
python -m app.main
# 等待看到 "Uvicorn running on http://0.0.0.0:8100" 即就绪
# 可访问 http://localhost:8100/docs 查看 Swagger UI
# 健康检查：curl http://localhost:8100/api/health

# ---- 终端 2：运行批量编排器 ----
cd agent-review-service
source .venv/bin/activate

# 1) 准备清单文件（JSONL 格式，每行一条作文）
#    参考 data/sample_dataset.jsonl

# 2) 将作文图片放入对应目录
#    data/images/<item_id>/page1.jpg, page2.jpg ...

# 3) 先 dry-run 试跑（只创建对战 + 生成 + 评审，不投票）
python -m batch.cli run -i data/sample_dataset.jsonl --dry-run

# 4) 正式运行（评审 + 自动投票）
python -m batch.cli run -i data/sample_dataset.jsonl -c 3

# 5) 查看任务执行状态
python -m batch.cli status
```

#### 方式二：一键脚本启动（生产推荐）

```bash
# 自动启动评审服务(后台) → 等待健康检查通过 → 执行批量任务 → 退出时自动清理
./scripts/run_batch.sh -i data/sample_dataset.jsonl -c 3

# dry-run 模式
./scripts/run_batch.sh -i data/sample_dataset.jsonl -c 3 --dry-run

# 脚本会自动：
#   1) 后台启动 python -m app.main（日志写入 logs/review_server.out）
#   2) 轮询 /api/health 最多等 30s 直到评审服务就绪
#   3) 执行 python -m batch.cli run ...
#   4) 退出时（含 Ctrl+C）自动 kill 评审服务进程
```

#### CLI 完整参数

```bash
python -m batch.cli run \
  -i data/sample_dataset.jsonl \  # 必需：JSONL 清单文件路径
  -c 3 \                          # 可选：并发数（默认取 BATCH_CONCURRENCY 环境变量，兜底 3）
  --dry-run \                     # 可选：只评审不投票
  --store ./data/tasks.sqlite \   # 可选：自定义 SQLite 状态库路径（默认 BATCH_STORE_PATH）
  -o ./data/results.jsonl          # 可选：结果输出到 JSONL 文件

python -m batch.cli status \
  --store ./data/tasks.sqlite      # 可选：查看指定库的任务统计
```

#### 批量处理流程（每条作文的阶段）

```
pending → created → generated → reviewed → voted → done
                                                  ↘ failed
```

| 阶段 | 操作 | 对应接口 |
| --- | --- | --- |
| `pending→created` | 编码图片 + 调对战平台创建对战 | `POST /api/battle/create` |
| `created→generated` | 触发 AI 生成两份批改（支持超时轮询降级） | `GET /api/battle/{id}/generate` |
| `generated→reviewed` | 调 Multi-Agent 评审服务做 6 维度评分 + 仲裁 | `POST /api/review`（本服务） |
| `reviewed→voted` | 将评审结果映射为投票并提交（dry-run 跳过） | `POST /api/battle/{id}/vote` |
| `voted→done` | 标记完成，记录耗时 | - |

**断点续跑**：SQLite 记录每条作文的当前阶段，进程中断后重启会自动从最后成功阶段继续，不会重复创建对战或投票。

**幂等保护**：
- 创建阶段：若 TaskStore 已有 `battle_id` 则跳过
- 生成阶段：若对战已为 `ready/voted` 状态则跳过
- 投票阶段：Java 端 `UNIQUE(battle_id, user_id)` 约束；若返回 `409/"已投票"` 视为成功

#### JSONL 清单格式

每行一个 JSON 对象，字段说明：

```json
{
  "item_id": "essay-001",
  "essay_title": "记一次难忘的秋游",
  "images": [
    {"kind": "local", "path": "./data/images/essay-001/page1.jpg"},
    {"kind": "url",   "path": "https://example.com/page2.jpg"},
    {"kind": "base64","data": "iVBORw0KGgo..."}
  ],
  "essay_content": "（可选）原作文文本或 OCR 转写",
  "grade_level": "初中",
  "requirements": "（可选）重点关注主旨与逻辑",
  "metadata": {"source": "dataset-v1"}
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `item_id` | ✅ | 唯一 ID，用于断点续跑去重 |
| `essay_title` | ✅ | 作文题目 |
| `images` | ✅ | 作文图片，至少一张；支持 `local`/`url`/`base64` 三种来源 |
| `essay_content` | ❌ | 原作文正文（有则提升评审质量） |
| `grade_level` | ❌ | 年级，默认 `"初中"` |
| `requirements` | ❌ | 批改特殊要求 |
| `metadata` | ❌ | 自定义元数据（透传，不影响评审） |

#### 前置条件检查清单

| 检查项 | 说明 |
| --- | --- |
| `.env` 中 `AI_API_KEY` 已配置 | Multi-Agent 评审需要调用 LLM |
| `.env` 中 `ARENA_BASE_URL` 可达 | 批量系统需要调对战平台创建/生成/投票 |
| `.env` 中 `ARENA_USERNAME/PASSWORD` 正确 | 批量系统需要登录对战平台 |
| Java 对战平台已启动（默认 `:5001`） | 批量系统的 create/generate/vote 依赖它 |
| 作文图片已就位 | `images` 中的 `local` 路径必须存在 |
| （可选）RAG 已初始化 | 有评分标准知识库可提升评审质量 |

## 六、核心接口

### 6.1 `POST /api/review`

**请求体** (`ReviewRequest`)：

```json
{
  "battle_id": 42,
  "essay_title": "记一次难忘的秋游",
  "response_a": "...批改A全文...",
  "response_b": "...批改B全文...",
  "essay_content": "原作文（可选）",
  "grade_level": "初中",
  "requirements": "重点关注主旨与逻辑"
}
```

**响应体** (`ReviewResponse`)：

```json
{
  "report": {
    "battle_id": 42,
    "dimensions": [
      {"dim": "theme", "score_a": 4.0, "score_b": 3.2, "winner": "A",
       "reason": "...", "evidence": ["..."], "confidence": 0.82},
      "..."
    ],
    "final_winner": "A",
    "overall_confidence": 0.78,
    "review_version": "v1"
  },
  "vote_payload": {
    "dim_theme": "left",        "dim_theme_reason": "...",
    "dim_imagination": "tie",   "dim_imagination_reason": "...",
    "dim_logic": "right",       "dim_logic_reason": "...",
    "dim_language": "left",     "dim_language_reason": "...",
    "dim_writing": "tie",       "dim_writing_reason": "...",
    "dim_overall": "left",      "dim_overall_reason": "..."
  },
  "latency_ms": 6842,
  "model_trace": {"preprocess": "done", "latency_ms": 6842}
}
```

`vote_payload` 可直接作为 `POST /api/battle/{id}/vote` 的请求体。

### 6.2 其他接口

| 接口 | 作用 |
| --- | --- |
| `GET /api/health` | 健康检查 |
| `GET /api/rag/stats` | 查看 3 个集合文档数 |
| `POST /api/rag/seed` | 从 `app/rag/seed/` 导入（可 `reset=true`） |
| `POST /api/rag/upsert` | 追加单条知识 |

## 七、关键设计

1. **LangGraph DAG**：`START → preprocess → dispatch (fan-out) → 6×dimension_agent → arbitrator → END`；6 个维度并行执行，通过 `Annotated[List, operator.add]` 合并结果。
2. **仲裁强约束**：`final_winner` 必须等于 `OVERALL.winner`；LLM 若冲突则强制回退到 OVERALL。
3. **Skill 而非 MCP**：所有工具是 Python 内部纯函数，通过 `SkillRegistry` 单例暴露，零部署成本。
4. **投票映射**：由于 Java 端 `displayOrder` 固定 `normal`，内部 A/B 与展示 left/right 一一对应，`VoteMapper.to_vote_payload` 做 A→left / B→right / tie→tie 映射；子维度按分差阈值强制 tie（默认 `0.5`）。
5. **断点续跑**：SQLite 以 `item_id` 为主键记录阶段 `pending/created/generated/reviewed/voted/done/failed`，重启从最后成功阶段续跑。
6. **敏感信息脱敏**：logger 把 base64 图片压成 `前12字符...<base64len=N>`，`api_key/token/password` 替换为 `***`。

## 八、测试

```bash
# 运行全部测试（146 个用例）
pytest tests/ -v

# 带覆盖率报告
pytest tests/ --cov=app --cov=batch --cov-report=term-missing

# 只跑某个模块
pytest tests/test_batch.py -v
pytest tests/test_graph_smoke.py -v
```

| 测试文件 | 测试数 | 覆盖模块 |
| --- | --- | --- |
| `test_contracts.py` | 6 | Pydantic DTO 字段/snake_case/Java 对齐 |
| `test_decision.py` | 16 | VoteMapper A/B→left/right 映射/阈值/兜底 |
| `test_vote_mapper.py` | 4 | 分差阈值 / tie 兜底 / 理由截断 |
| `test_skills.py` | 7 | 6 个 Skill 注册与输入输出 |
| `test_rag.py` | 16 | Embedding fallback / ChromaStore CRUD / Retriever 缓存 |
| `test_llm_client.py` | 10 | OpenAI 兼容客户端 JSON 解析/重试/异常 |
| `test_review_nodes.py` | 14 | preprocess/dimension_agent/dispatch/arbitrator 节点 |
| `test_service.py` | 10 | ReviewService 外观 / 维度合并 / 边界条件 |
| `test_graph_smoke.py` | 3 | A 赢/B 赢/tie 三种端到端冒烟 |
| `test_batch.py` | 21 | task_store/image_encoder/dataset_loader/orchestrator 全链路 |
| `test_api.py` | 12 | FastAPI 路由：health/review/RAG 管理接口 |

## 九、环境变量

参考 `.env.example`：

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `AI_API_KEY` | - | OpenAI 兼容 API Key |
| `AI_BASE_URL` | `https://api.aihubmix.com/v1` | 网关地址 |
| `AI_REVIEW_MODEL` | `gpt-4o-mini` | 维度 Agent 模型 |
| `AI_ARBITRATOR_MODEL` | `gpt-4o` | 仲裁模型 |
| `ARENA_BASE_URL` | `http://localhost:5001` | Java 平台地址 |
| `ARENA_USERNAME/PASSWORD` | `admin/admin123` | 登录凭据 |
| `REVIEW_PORT` | `8100` | FastAPI 端口 |
| `REVIEW_URL` | `http://localhost:8100` | 批量客户端调用地址 |
| `CHROMA_DIR` | `./data/chroma` | 向量库持久化目录 |
| `EMBEDDING_PROVIDER` | `openai` | `openai` 或 `fallback`（hash） |
| `BATCH_STORE_PATH` | `./data/batch_tasks.sqlite` | 任务状态库 |
| `BATCH_CONCURRENCY` | `3` | 并发对战数 |
| `DIM_SCORE_TIE_THRESHOLD` | `0.5` | 子维度分差强制 tie 阈值 |

## 十、与 Java 平台的对齐要点

- **投票值**：Java `VoteRequest` 的 `@Pattern(^(left|right|tie)$)` 强校验，**不接受 A/B**，已由 `VoteMapper` 转换。
- **创建请求**：`images` 必传、为纯 base64（不带 `data:image` 前缀），`ImageEncoder` 已自动剥离前缀并 Pillow 压缩至 ≤2MB/张。
- **生成接口**：`GET /api/battle/{id}/generate`（**非 POST**）；若请求超时，`orchestrator` 会自动降级为轮询 `/api/battle/{id}` 直到 `status != "generating"`。
- **对战返回**：只返回 `response_left/right`，不含 `response_a/b`；本服务约定 `left==A、right==B`。
- **幂等**：`UNIQUE(battle_id,user_id)` 保护重复投票；若遇 `409/"已投票"`，客户端视为成功。
