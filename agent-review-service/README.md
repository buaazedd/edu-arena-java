# Agent Review Service

Run locally:

```bash
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8100 --reload
```

Environment:

```bash
cp .env.example .env
```

## 0) 推荐配置（你给的模型）

本项目已支持：

- Embedding: `gemini-embedding-001`
- Reranker: `qwen3-reranker-4b`

只需在 `.env` 里配置：

```bash
EMBEDDING_PROVIDER=api
AIHUBMIX_API_KEY=sk-xxx
EMBEDDING_API_MODEL=gemini-embedding-001
RERANK_ENABLED=true
RERANK_MODEL=qwen3-reranker-4b
RERANK_API_KEY=sk-xxx
```

说明：

- 如果 `EMBEDDING_API_KEY` 为空，会自动回退用 `AIHUBMIX_API_KEY`
- 如果 `RERANK_API_KEY` 为空，也会自动回退用 `AIHUBMIX_API_KEY`

---

## 1) 你本地还没装任何前置依赖时，怎么启动

推荐三档模式（从易到难）：

### A. 零门槛联调模式（先跑起来）

- 使用 `EMBEDDING_PROVIDER=local`
- 保持 `EMBEDDING_LITE_FALLBACK_ENABLED=true`
- 不需要本地模型，不需要 embedding API key

特点：能跑通 RAG 流程与接口，但检索语义质量仅用于联调。

### B. API 模式（你当前最适合）

- `EMBEDDING_PROVIDER=api`
- 配置 `AIHUBMIX_API_KEY`
- 默认 embedding 用 `gemini-embedding-001`
- 默认 rerank 用 `qwen3-reranker-4b`

特点：不需要下载本地 embedding 模型，质量和效果更稳定。

### C. 离线本地模型模式（推荐生产内网）

1. 先把模型下载到本机目录（例如 `D:/models/bge-small-zh-v1.5`）
2. `.env` 设置：
   - `EMBEDDING_PROVIDER=local`
   - `EMBEDDING_MODEL=D:/models/bge-small-zh-v1.5`

特点：不依赖外网，语义质量可用。

---

## 2) RAG 检索如何使用

### 2.1 导入四类数据（向量化入库）

- `rubric`: 评分规则
- `exemplar`: 范文片段
- `gold_case`: 历史高一致案例
- `error_pattern`: 常见风险模式

通过接口写入：`POST /rag/upsert`

示例：

```json
{
  "index": "rubric",
  "documents": [
    {
      "id": "rubric_theme_v1_1",
      "text": "主旨维度：紧扣题意，中心明确，有深化。",
      "metadata": {"dimension": "theme", "version": "rubric_v1", "id": "rubric_theme_v1_1"}
    }
  ]
}
```

### 2.2 召回 + 重排序测试

接口：`POST /rag/search`

```json
{
  "index": "rubric",
  "query": "主旨评分标准 初三 记叙文",
  "topK": 3,
  "where": {"dimension": "theme"}
}
```

流程：

1. Chroma 向量召回候选（`topK * RERANK_CANDIDATE_MULTIPLIER`）
2. 调用 `/v1/rerank` 用 `qwen3-reranker-4b` 重排
3. 返回最终 topK

---

## 3) 在图中什么时候检索

- `preprocess` 节点：召回 rubric（全局标准）
- `dimension_eval_parallel` 节点：每个维度召回 exemplar + gold_case + error_pattern
- 结果会写入 `retrievalUsed`，用于审计

---

## 4) 可视化与调试

### 4.1 图结构可视化

- `GET /graph/ascii`
- 返回 LangGraph 的 ASCII DAG

### 4.2 节点输出可视化

- `POST /review/run` 或异步任务结果中包含：
  - `nodeOutputs`: 每个节点摘要输出
  - `retrievalUsed`: 每个维度检索命中详情

---

## 5) 核心 API

- `GET /health`
- `GET /graph/ascii`
- `POST /rag/upsert`
- `POST /rag/search`
- `POST /review/jobs` (async create)
- `GET /review/jobs/{jobId}` (status)
- `GET /review/jobs/{jobId}/result` (result)
- `POST /review/run` (sync run)
