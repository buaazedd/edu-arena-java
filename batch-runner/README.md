# batch-runner

批量读取 `../writing/label_cn.txt`、`../writing/label_en.txt` 与对应图片，自动执行：

- 调 Java：创建对战 `POST /api/battle/create`
- 监听 SSE：`GET /api/battle/{id}/stream` 收集 A/B 输出
- 调评审：`agent-review-service` 的 `POST /review/run`
- 结果落盘：`../batch-output/`

## 安装

```bash
python -m venv .venv
.venv\\Scripts\\pip install -r requirements.txt
```

## 运行

```bash
set JAVA_BASE_URL=http://localhost:5001
set JAVA_SERVICE_SECRET=your-secret
set AGENT_REVIEW_URL=http://localhost:8000

.venv\\Scripts\\python batch-runner\\main.py --limit 2
```

