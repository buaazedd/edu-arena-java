# 📚 edu-arena-java 项目 Wiki

> **最后更新**: 2026-05-11 (v2.17.7: `scripts/export_dataset_local.py` 新增 `--image-concurrency N` 参数 —— 背景：用户跑全量导出反馈图片阶段慢（ETA ~2 小时），诊断：jsonl 阶段只有 22MB 跑完 <0.3s 符合预期，图片阶段瓶颈在**跨境家宽到国内百度云 MySQL 的下行带宽**，不是脚本本身。全库 `images_json` 列 ~844MB base64 文本，原 8 并发实测聚合带宽 ~950 KB/s，家宽上限还有剩余空间。把 `IMAGE_FETCH_CONCURRENCY=8` 从硬编码常量改为可通过 `--image-concurrency` 覆盖的 CLI 参数（默认仍 8 不变动现有行为），16 并发预计能缩到 1 小时左右，32 并发会被家宽 ISP 限速压住不再涨。另外确认跨境慢是常态：首步 `SELECT battles JOIN tasks` 拉 2 分钟 / 22MB 也是同一个跨境带宽瓶颈。没改核心数据流。使用：`python3 scripts/export_dataset_local.py -o out.zip --image-concurrency 16`。改动文件：`scripts/export_dataset_local.py`)  \n> **最后更新-上一版**: 2026-05-11 (v2.17.6: `scripts/export_dataset_local.py` 新增**终端实时进度**与**脏数据过滤**，并修复 pre-existing 的 SQL 歧义列 bug —— 背景：本地直连批量导出全量数据时肉眼看不到进度，且下游训练集发现一批可疑样本（6 维全 tie，reason 都是相同错误串），定位是 `agent-review-service` 在 LLM 调用失败（403 余额不足 / 401 鉴权过期等）时走 `app/review/nodes/dimension_agent.py::_fallback_score` 兜底路径，生成 `score_a=3/score_b=3/winner=tie/reason="LLM 评审失败，降级为 tie。原因：..."` 的假投票回写 DB，全库实测 8 条这类 battle。改动：① **脏数据识别**新增 `is_dirty_vote()`：遍历 `dim_theme_reason/dim_imagination_reason/dim_logic_reason/dim_language_reason/dim_writing_reason/dim_overall_reason` 6 个字段，命中 `_DIRTY_REASON_MARKERS=("LLM 评审失败，降级为 tie", "LLM 评审失败")` 任一 marker 即判脏（用 OR 而非 AND，因为 agent 通常整条流水线一起崩但保守起见要拦单维度失败）。② **默认过滤**在主循环 build_item 前执行，脏 battle 整条跳过（jsonl 里直接不出现），`--keep-dirty` 可关闭过滤（审计/对比用）。③ **审计字段** `manifest.json.dirty_filter` 含 `enabled/rule/dropped_battles/raw_battles_before_filter/samples[最多 5 条包含 battle_id+vote_id+reason_excerpt]`，便于下游追溯被过滤掉的具体原因（如 "Error code: 403 ... account balance is insufficient"）。④ **battle 级进度**：第一遍写 jsonl 每 `--progress-every`（默认 100）条打印 `[jsonl] idx/total kept=X dirty=Y elapsed=Ts ETA=Ts`，`flush=True` 确保立即刷新终端；图片阶段进度粒度从每 50 条改为每 20 条，统一前缀 `[images]`。⑤ **末尾总结**从 `battles=N` 改为 `raw=N kept=K dropped_dirty=D images=M size=X.XMB 总耗时=Ts` 一行展示过滤前后对比。⑥ **修 pre-existing SQL bug**：`build_battle_where` 在 `battles b LEFT JOIN tasks t` 场景下，原先 `where="status='voted'" / "id=%s" / "winner=%s" / "created_at>=%s" / "(model_a_id=... OR ...)"` 等都没加表别名，pymysql 报 `1052 Column 'id' in where clause is ambiguous`；所有引用统一加 `b.` 前缀。新增参数：`--keep-dirty`（默认关=过滤）、`--progress-every N`（默认 100）。实测 30 条 0.4s、单条脏 battle 识别命中率 100%。改动文件：`scripts/export_dataset_local.py`)  
> **最后更新-上一版**: 2026-05-11 (v2.17.5: 新增 `scripts/export_dataset_local.py` 本地直连 MySQL 的偏好数据集导出脚本 —— 背景：服务器侧 `/api/admin/export/dataset.zip` 走 `ExportServiceImpl`，数据路径是「国内 MySQL(180.76.229.245) ─跨境 200ms RTT→ Java(阿里云新加坡 8.219.130.23) ─跨境 HTTP→ 浏览器」，整条链路数据跨境 2 次，且每次 MySQL 查询都吃 ~200ms RTT。实测 voted battle=2438、全库 `images_json`≈844MB、`responses`≈13MB，服务器侧导出通常要 30+ 分钟。改用本地直连链路「国内 MySQL ─跨境 ~8ms RTT→ 本地 Python 直接写 zip」后 RTT 改善 25 倍，只跨境 1 次，预期几分钟完成。脚本与 Java 服务端导出**二进制兼容**：schema_version=1.0、zip 内部结构 `data.jsonl` + `images/task_%d/%02d.{jpg\|png\|webp\|gif}` + `manifest.json`、JSON 字段顺序与命名完全对齐，消费方脚本无感切换。实现要点：① 一次 SQL JOIN 把 `battles + tasks(不含 images_json 这个 LONGTEXT)` 全量拉回来（本地低 RTT，不需要分页），再两次 IN 拉 votes/models；② 图片 `images_json` 用 `ThreadPoolExecutor(max_workers=8)` 并发从独立连接逐 task 拉取，主线程按提交顺序 `future.result()` 写 zip，保证输出顺序稳定；③ 图片魔数探测后缀（jpg/png/webp/gif），base64 前缀 `data:image/xxx;base64,` 自动剥离；④ `ZIP_STORED` 不对已压缩图片做二次压缩，省 CPU；⑤ 每 50 个 task 打印进度 + ETA；⑥ DB 连接信息默认读 `application.yml` 里的线上配置（`180.76.229.245/root/zyd123/edu_arena`），可通过 `--db-host/user/password` 或环境变量 `EA_DB_*` 覆盖；⑦ 过滤参数 `--battle-id/--winner/--model-id(支持主键或 model_id 字符串)/--start-date/--end-date/--limit/--no-images` 语义与 Java `ExportQuery` 一一对齐；⑧ `manifest.json` 增加 `source=local_direct_mysql` 字段标记来源。使用：`python3 scripts/export_dataset_local.py -o out.zip [--limit N] [--no-images]`。依赖：`pymysql`（系统 Python3 通常已自带）。改动文件：新增 `scripts/export_dataset_local.py`)   —— 现象：之前的 `deploy.sh` 用 `scp -O` 上传 55MB JAR 跨境（本地 ↔ 阿里云新加坡 8.219.130.23）耗时数分钟且偶发中断，导致服务器侧 jar 损坏 `Zip 'Local File Header Record' not found`、进程拒绝启动。根因：① `-O` 强制走传统 SCP 单窗口协议（每 packet 等 ACK），跨境 RTT ~200ms 下单连接吞吐被卡到约 320KB/s（≈ 默认 64KB TCP 窗口 ÷ RTT），OpenSSH 9+ 默认的 SFTP 模式有异步 pipeline 吞吐高一个数量级；② 此前还误以为 `-C` 压缩能加速，但 JAR 本身是 zip 已不可压缩，反而 CPU 打满成为瓶颈；③ `ServerAliveInterval=15 ServerAliveCountMax=4` 在丢包链路上探测包丢失会被提前判定连接死亡。改动：① 移除 `-O` 让 scp 走默认 SFTP；② 移除 `-C` 与 `ServerAlive*`；③ 上传策略改为先传 `edu-arena-1.0.0.jar.new` → MD5 校验本地远端一致 → 远程 `mv -f` 原子替换，避免传输中断污染线上 jar；④ 校验失败立即 `exit 1` 不会继续重启服务。实测跨境 55MB 上传 5~10s 完成。改动文件：`deploy.sh`)  
> **更早一版**: 2026-05-11 (v2.17.3: 偏好数据集导出跨境慢的根因定位与修复 —— 现象：4 条 voted 数据导出耗时 ~11s。实测 app(8.219.130.23) ↔ MySQL(180.76.229.245) ping RTT=207ms，跨境跨云链路。`writeJsonl` 第一遍 `taskMapper.selectBatchIds(taskIds)` 默认 `select *` 会把 `tasks.images_json` 这个 LONGTEXT（每条最多 ~5MB base64）也跨境拉回来，第二遍 `selectById` 又拉一次，总共上百 MB 的 base64 走两遍跨境网络。改动 `ExportServiceImpl`：① **第一遍批量拉 task 改用 `LambdaQueryWrapper.select(...)` 显式排除 `images_json` 列**，jsonl 仅依赖 `image_count/has_images` 推断图片数量与文件名，把 LONGTEXT 网络传输彻底从第一遍剥掉；② 新增 `writeImagesParallel`：第二遍按 task_id 用固定线程池（`IMAGE_FETCH_CONCURRENCY=4`，daemon 线程）并发 `taskMapper.selectById` 拉单条 imagesJson，主线程按提交顺序 `future.get()` 串行写 ZIP，把串行 N×RTT 压成 ≈ N/4 × RTT；③ 新增 `computeImageRelPathsByCount`（按 `image_count` 推路径，统一标 .jpg；真实后缀在第二遍解码时由 `detectImageExt` 按魔数确定写入 ZIP，jsonl 后缀与 ZIP 后缀的轻微不一致是已知偏差，消费方按 `task_%d/%02d.*` 通配定位）；④ 不再使用 `taskImagesJson` 内存缓存（v2.17.2 引入），改回只缓存 `Set<Long> taskIdsWithImages`；⑤ 各阶段加细粒度耗时日志 `[导出] page=N 拉取耗时 battle=Xms task(noBlob)=Yms vote=Zms model=Wms` / `[导出] task=ID fetch=Ams decode+zip=Bms`，便于线上回溯。预期 4 条数据 11s → ~2s。改动文件：`src/main/java/com/edu/arena/service/impl/ExportServiceImpl.java`)  
> **更早一版**: 2026-05-11 (v2.17.2: 修复偏好数据集导出请求被双层超时拦截 —— 现象：前端点击导出后 nohup.out 出现 `AsyncRequestTimeoutException`、ZIP 下载中断；根因 ① `WebConfig.configureAsyncSupport` 把 Spring MVC 异步超时设为 5 分钟（300_000ms），`StreamingResponseBody` 跑超 5 分钟即被 Spring 自身终止 → 拉至 1_800_000ms 与事务/HikariCP 阈值对齐；② 线上 `/etc/nginx/conf.d/edu_arena.conf` 中 `location /api/` 仅设 `proxy_read_timeout 120s` 且未关闭 `proxy_buffering`，Nginx 在 120s 时即断开 upstream 并把 ZIP 全量缓冲再下发，**需在服务器同步将该 location 的 `proxy_read_timeout`/`proxy_send_timeout` 改为 1800s 并加 `proxy_buffering off; proxy_request_buffering off; proxy_cache off; proxy_set_header Authorization $http_authorization;` 后 `nginx -s reload`**。改动文件：`src/main/java/com/edu/arena/common/config/WebConfig.java`。v2.17.1: 修复 `ExportServiceImpl` 触发 HikariCP `Apparent connection leak detected` 告警 —— `exportZip` 增加 `@Transactional(readOnly=true, timeout=1800)` 让导出走单只读事务、复用同一 Connection；`application.yml` 中 `spring.datasource.hikari.leak-detection-threshold` 从 120000 放宽到 1800000，避免对长任务的噪声告警。v2.17: **偏好数据集导出接口重做** —— 旧 `/api/admin/export/preference` + `/api/admin/export/jsonl` 仅返回 5 个字段（battleId/modelA/modelB/result/createdAt）、模型仅给数据库主键、且一次性 `selectList(null)` 加载全表序列化为字符串再 `getBytes()` 返回，体量稍大就 OOM；现已**整体删除**，由全新主接口 `GET /api/admin/export/dataset.zip` 取代。新接口固定输出 ZIP 包：`data.jsonl`（每行一条 battle 完整数据：作文/题目/年级/A&B 完整批改/六维度评分+理由/ELO 前后快照/投票时长，模型信息以 `model_id` 字符串而非裸主键给出，预留 `schema_version=1.0`）+ `images/task_{id}/01.jpg|png|webp`（作文图片按 task 去重落地为文件，jsonl 内只引相对路径，base64 不再内嵌）+ `manifest.json`（导出时间/总条数/总图片数/过滤条件）；**强制只导 `status=voted`**，generating/ready/failed 全部过滤；分页 200 条/页 + 临时文件落 jsonl + 流式 `StreamingResponseBody` 写 ZIP，规避 OOM；图片 base64 不预先全量缓存到内存，第一遍仅收集 task_id 集合，第二遍按 task_id 单条查询 → 解码 → 写 ZIP；过滤参数 `winner / modelId(可传主键或 model_id 字符串) / startDate / endDate / battleId / includeImages / limit`；前端 admin.html 「数据导出」Tab 重做为下拉/日期/复选框筛选 + fetch+blob 携带 JWT 下载；新增 `dto/request/ExportQuery.java`、`service/ExportService.java`、`service/impl/ExportServiceImpl.java`，从 `ModelService/Impl` 移除 `exportPreferenceJson/Jsonl` 两个方法及残留 `cn.hutool.json` 导入)  
> **v2.16** (2026-05-11): `agent-review-service` 新增 **DeepSeek 单 Agent 评审链路** —— 旧 LangGraph 多 Agent 流程每场对战 9~10 次 LLM 调用，AiHubMix 网关侧多次因调用过密被风控/封禁；新增 `app/review/single_agent.py` 走 DeepSeek OpenAI 兼容端点（`base_url=https://api.deepseek.com`，默认 `model=deepseek-v4-flash`，可选 `deepseek-v4-pro`），1 次 LLM 调用按固定 5 步 CoT 直接产出 6 维评分 + final_winner（不引入 skills/RAG/作文图片，最大化降低成本与封禁概率）；① `app/settings.py` 与 `.env` 新增 `REVIEW_MODE` / `AI_API_KEY_SINGLE` / `AI_BASE_URL_SINGLE` / `AI_REVIEW_MODEL_SINGLE`，默认 `REVIEW_MODE=single`；② `app/review/prompts.py` 追加 `SINGLE_AGENT_SYSTEM` + `single_agent_user`，写明固定 5 步 CoT；③ `app/review/service.py` 改为按 `review_mode` 分支；④ 对外契约（`ReviewResponse`/`VotePayload`）零变更，Java 端无感；⑤ 旧 AiHubMix 配置项与 LangGraph 节点全部保留可随时切回 `REVIEW_MODE=multi`
> **v2.15.6** (2026-05-07): 重建 `scripts/cleanup_failed_reviews.py` 清理脚本 —— v2.15.3 条目里声称已存在但实际从未落盘，本次按真实 schema 重写；① 识别文案默认覆盖 `LLM 评审失败，降级为 tie` / `this key is not enabled` / `quota exhausted` / `rate limit` / `Connection error` 等常见兜底/失败片段，6 个 `dim_*_reason` 字段任一命中即算污染；② **按依赖顺序级联清理 5 张表**：`quality_logs`（外键 `vote_id`，先删）→ `elo_history`（按 `battle_id`，每场 2 条）→ `votes` → `battles`（无残留投票的回退到 `ready` 并清空 `winner`，保留 `response_a/b`）→ `models`（按剩余 `elo_history` 最新一条回滚 `elo_score`，无历史则 1500.00；同时基于 `votes JOIN battles` 实时重算 `total_matches / win_count / lose_count / tie_count`）；③ **Redis 缓存同步清理**（键名与 `CacheService.java` 常量对齐）：`edu_arena:leaderboard:all` / `edu_arena:leaderboard:elo_history` / `edu_arena:models:active` / `edu_arena:battle:{id}` / `edu_arena:battle:fallback:{id}` / `edu_arena:model:detail:{id}` / `edu_arena:api:model_info:{id}`，永久计数器 `edu_arena:stats:total_votes` 用 `DECRBY` 按实际删除数递减；④ `essay_images` / `tasks` 明确不触碰（多 battle 共享 task，清理会殃及未污染对战）；⑤ 默认 dry-run 事务 ROLLBACK，加 `--apply` 才真实 COMMIT；支持 `--stats-only` / `--pattern` / `--battle-status-to ready\|failed` / `--keep-battles` / `--no-recompute-elo` / `--no-redis`；⑥ 首次 dry-run 实测：命中 47 条假 tie / 47 个 battle / 94 条 elo_history / 28 个模型需重算 ELO)  \n> **v2.15.5** (2026-05-07): `deploy.sh` 上传环节加固 —— 慢链路（实测远端 8.219.130.23 上行仅 ~125 KB/s，55 MB JAR 需 ~8 分钟）下默认 `scp` 在 macOS Ventura+ 走 SFTP 协议且无 keepalive，容易被中间网关空闲掐断报 `Connection closed by 8.219.130.23 port 22 / scp: Connection closed`；① `scp` 加 `-O` 强制回退传统 SCP 协议，对慢链路兼容性更好；② 抽出公共 `SSH_OPTS` 增加 `ServerAliveInterval=15 ServerAliveCountMax=4 ConnectTimeout=15`，连接 60s 无流量自动发心跳保活；③ 上传封装为 `upload()` 函数，第一次失败自动 sleep 5s 重试一次；④ 同时清理原脚本里冗余的 `scp ... 2>/dev/null \|\| scp ...` 兜底语句)  
> **v2.15.4** (2026-05-07): AiHubMix API Key 全量轮换 —— 旧 key `sk-LEc0Cx...0e`（`agent-review-service/.env::AI_API_KEY`，评审用）与 `sk-OyTz84ZS...8a`（Java 主服务在线生成用）经 `curl /v1/chat/completions` 验证均返回 401 `this key is not enabled`，即 AiHubmix 网关侧已禁用，是导致 v2.15.3 中 795 条假投票的根因；新 key `sk-u9ycJy...Fd` 实测 `/v1/models` 返回 200 且 `gpt-5-mini` 实际推理 200，已统一替换 4 处：`agent-review-service/.env::AI_API_KEY`、`src/main/resources/application.yml::ai.api-key`、`scripts/model_manage.py::AIHUBMIX_KEY`、`scripts/verify_and_fix.py::AIHUBMIX_KEY`；后续重启 Java 主服务和 `agent-review-service` 后即可对清理脚本回退的 795 个 `ready` 状态对战重跑评审)  
> **v2.15.3** (2026-05-07，设计记录，脚本实际未落盘 —— 已由 v2.15.6 按真实 schema 重建): 原计划新增 `scripts/cleanup_failed_reviews.py` 清理脚本（用途见 v2.15.6）。注：本条原描述中"实测清理 795 条"为设计预估，未真实发生；以 v2.15.6 的 dry-run 实测数据（47 条）为准  
> **v2.15.2** (2026-05-05): `BattleServiceImpl` 长事务拆分重构 —— ① `createBattle` 将图片压缩阶段（`compressImagesInPlace`）完全剥离出事务，仅保留 DB 读写在新的短事务方法 `doCreateBattleTx` 内；② `generateBattle` **彻底移除方法级 `@Transactional`**，拆为三段：读事务 `loadGenerateContextTx(readOnly=true)` → **无事务的并行 LLM 调用** → 写事务 `persistGenerateResultTx`，LLM 调用期间不占用任何 JDBC 连接；③ 通过 `@Autowired @Lazy BattleServiceImpl self` 自注入代理，解决内部 this 调用不走事务代理的问题；④ 新增 `private record GenerateContext` 作为读阶段上下文快照；⑤ `persistGenerateResultTx` 增加 `status != generating` 的幂等保护，避免并发重试覆盖已完成结果；⑥ 模型并行调用线程池扩容：核心 4→8、最大 20→40、队列 100→200；⑦ 清理死代码 `MAX_SLOT_RETRY` 常量和未使用的 `saveBattleResult` 私有方法；⑧ 效果：批量评审 -c 10 并发下，HikariCP 连接峰值占用从 "并发数 × LLM 时长" 降到 "并发数 × 毫秒级事务"，彻底解决 `SQLTransientConnectionException: Connection is not available` 问题
> **v2.15.1** (2026-05-05): HikariCP 连接池扩容 —— ① `application.yml` `spring.datasource.hikari.maximum-pool-size` 20→80、`minimum-idle` 5→10；② 新增 `leak-detection-threshold=120000` 连接泄漏检测、`validation-timeout=5000`、`keepalive-time=300000` 保活探测；③ 背景：批量评审（`agent-review-service` `-c 10`）触发 `SQLTransientConnectionException: Connection is not available, request timed out after 30000ms` —— `BattleServiceImpl.createBattle/generateBattle` 的 `@Transactional` 内嵌同步 LLM 调用导致连接被长时间占用，原 20 连接池瞬间被打满；④ WIKI「八、配置说明」补充连接池参数与已知瓶颈说明  
> **v2.15** (2026-05-04): 新增泰安市高二期末作文批量评审数据集支持 —— ① 新增脚本 `agent-review-service/scripts/gen_dataset_taian.py`，针对"姓名-学号-正面/背面.jpg"命名规范按学号聚合生成 `DatasetItem`，兼容"仅正面 / 仅背面 / 正背齐全"；② 固化英雄与选择作文题到脚本 `ESSAY_TITLE` 常量；③ 输出 `data/dataset_taian_hero.jsonl`（11559 条）；④ 新增使用说明 `agent-review-service/泰安作文使用说明.md`，覆盖清单生成 / 一键批量 / 分步手动 / 断点续跑 / 失败重跑 / 结果统计全流程
> **v2.14.1** (2026-04-25): 修复 v2.14 两处隐性缺陷 —— ① `BattleMapper.selectHistoryPage` 原用 `MAX(v.user_id)+MAX(u.username)+MAX(u.display_name)` 聚合，一场对战有多条投票时三字段可能来自不同行造成"身份串号"，改为子查询 `MIN(v2.id)` 定位主投票行后 LEFT JOIN；② `BattleController.getBattle` 脱敏前对 `BattleVoteVO` 做浅拷贝，避免修改缓存命中持有的 VO 对象跨角色/跨请求污染  
> **v2.14** (2026-04-25): 投票人追溯 —— 对战历史列表新增「投票人」列、详情弹窗修复并展示投票人，后台管理新增「投票记录」Tab；身份口径统一 `displayName→username`，服务端按角色脱敏（admin 全量；teacher 仅自己真名，其他显示「匿名」）；新增 `AdminVoteController` + `VoteQueryService` + `BattleVoteVO`/`AdminVoteItemVO`/`AdminVoteQuery`；`BattleMapper.selectHistoryPage` 与 `VoteMapper.selectVotePage` 相应扩展  
> **v2.13** (2026-04-25): `agent-review-service/README.md` 全面重写——新增「多智能体架构」专章详解 preprocess / dispatch / dimension_agent / arbitrator / VoteMapper 各节点职责与归约机制；拆分并扩充「启动说明」为服务启动（3 种方式）+ 批量数据准备 + 跑批（一键/手动）四段式端到端指南；修订默认 LLM 模型为 `gpt-5-mini`/`gpt-5`，补全环境变量表  
> **用途**: 供大模型快速了解项目全貌，辅助代码生成与修改  

---

## 一、项目概览

| 属性 | 值 |
|------|------|
| **项目名称** | edu-arena（教育大模型众包式对战评测平台） |
| **业务场景** | 面向中学作文批改场景，通过匿名 A/B 对战和教师投票，构建高质量教育大模型人类偏好数据集，并用 ELO 积分对各 AI 模型排名 |
| **技术栈** | Spring Boot 3.2.3 + Java 17 + MyBatis-Plus + MySQL + Redis + Thymeleaf + JWT + OkHttp(SSE) |
| **运行端口** | `5001` |
| **数据库** | MySQL 8.x（库名 `edu_arena`） |
| **缓存** | Redis（用于排行榜缓存、对战限流、统计计数） |
| **前端** | Thymeleaf 模板引擎 + Bootstrap 5 + Chart.js（前后端一体，无独立前端工程） |
| **AI 调用** | 统一通过 OpenAI 兼容接口（配置 `ai.base-url`），使用 AiHubMix 聚合网关 |
| **子项目** | `agent-review-service/`（Python，LangGraph 多 Agent 评审服务 + 离线批量处理系统，FastAPI 端口 8100，独立运行） |

---

## 二、核心业务流程

```
教师用户                                         系统
  │                                              │
  ├─ 1. 注册/登录 ──────────────────────────────►│ AuthController → AuthService → JWT
  │                                              │
  ├─ 2. 提交作文(题目+图片,图片必传) ──────────►│ BattleController.create
  │                                              │  ├─ 验证图片必传 + 图片压缩(ImageCompressUtils)
  │                                              │  ├─ 创建 Task 记录
  │                                              │  ├─ ELO 匹配选 2 个模型(EloMatchService)
  │                                              │  └─ 创建 Battle(status=generating)
  │                                              │
  ├─ 3. 请求生成批改结果 ──────────────────────►│ BattleController.generate
  │                                              │  ├─ 并行调用 2 个 AI 模型(AiClient + 线程池)
  │                                              │  ├─ 模型故障自动 Fallback
  │                                              │  └─ 保存 responseA/B, status=ready
  │                                              │
  │◄─ 4. 返回匿名左右两个批改结果 ──────────────│ BattleVO(匿名化:不返回模型名,可能 swap 顺序)
  │                                              │
  ├─ 5. 教师对 6 个维度投票(含理由) ───────────►│ BattleController.vote
  │                                              │  ├─ 转换 left/right → A/B(考虑 displayOrder)
  │                                              │  ├─ 胜负判定: 直接取"整体评价"维度值
  │                                              │  ├─ ELO 积分更新(EloCalculator, K=32)
  │                                              │  ├─ 保存 Vote + EloHistory
  │                                              │  └─ 清除排行榜缓存
  │                                              │
  │◄─ 6. 返回投票结果 + ELO 变化 ───────────────│ VoteResultVO
  │                                              │
  ├─ 7. 查看排行榜 ────────────────────────────►│ LeaderboardController → Redis 缓存
  └─ 8. 查看对战历史 ──────────────────────────►│ BattleController → 分页查询
```

### 投票六维度

| 维度 | 字段名 | 说明 | 备注 |
|------|--------|------|------|
| 主旨 | `dim_theme` | 是否紧扣题意、中心明确 | 参考维度 |
| 想象 | `dim_imagination` | 创意与想象力 | 参考维度 |
| 逻辑 | `dim_logic` | 结构与逻辑性 | 参考维度 |
| 语言 | `dim_language` | 语言表达能力 | 参考维度 |
| 书写 | `dim_writing` | 书写规范性 | 参考维度 |
| **整体评价** | **`dim_overall`** | **综合来看哪个批改更好** | **⭐ 决定最终胜负** |

前 5 个维度值为 `left`/`right`/`tie`，后端转换为 `A`/`B`/`tie`，仅作参考。**整体评价 (`dim_overall`) 直接决定 winner**，不再基于子维度多数决。

---

## 三、目录结构

```
edu-arena-java/
├── pom.xml                                          # Maven 配置
├── WIKI.md                                          # 本文件
├── agent-review-service/                            # Python 子项目(Multi-Agent 评审 + 离线批量)
│   ├── README.md                                    # 架构图/启动/接口示例
│   ├── requirements.txt
│   ├── .env.example
│   ├── pyproject.toml
│   ├── app/
│   │   ├── main.py                                  # FastAPI 入口(端口 8100)
│   │   ├── settings.py                              # pydantic-settings
│   │   ├── contracts/                               # 两系统共享 Pydantic 契约(snake_case 对齐 Java)
│   │   │   ├── arena_dto.py                         # Java 5 接口 DTO(Login/Create/Battle/Vote/Result)
│   │   │   ├── review_dto.py                        # ReviewRequest/ReviewResponse/VotePayload
│   │   │   ├── review_models.py                     # DimensionKey/DimensionScore/ReviewReport
│   │   │   └── dataset_dto.py                       # DatasetItem 离线清单条目
│   │   ├── review/                                  # 多智能体核心 + 单 Agent 评审（v2.16）
│   │   │   ├── graph.py                             # LangGraph StateGraph 装配（multi 模式）
│   │   │   ├── state.py                             # GraphState TypedDict (Annotated[List,add] 并行合并)
│   │   │   ├── llm.py                               # AsyncOpenAI 封装(JSON mode + 多模态)，OpenAI 兼容协议复用于 DeepSeek
│   │   │   ├── prompts.py                           # preprocess/dim/arbitrator + SINGLE_AGENT_SYSTEM(5 步 CoT)
│   │   │   ├── decision.py                          # VoteMapper (A/B → left/right)
│   │   │   ├── single_agent.py                      # 【v2.16 新增】DeepSeek 单 Agent，1 次 LLM 产出 6 维 + final_winner
│   │   │   ├── service.py                           # ReviewService 外观类，按 REVIEW_MODE=single/multi 分支
│   │   │   └── nodes/                               # preprocess/dispatch/dimension_agent/arbitrator（仅 multi 模式使用）
│   │   ├── rag/                                     # ChromaDB 三集合
│   │   │   ├── store.py / retriever.py / embedding.py
│   │   │   └── seed/{rubric.md,exemplar.jsonl,gold_case.jsonl}
│   │   ├── skills/                                  # 6 个本地工具(BaseSkill + SkillRegistry)
│   │   │   ├── text_stats.py / grammar_check.py / duplicate_detect.py
│   │   │   └── feedback_compare.py / coverage_analyzer.py / hallucination_check.py
│   │   ├── api/                                     # FastAPI 路由
│   │   │   ├── review_router.py                     # /api/review, /api/health
│   │   │   └── admin_router.py                      # /api/rag/seed|upsert|stats
│   │   └── common/                                  # logger(loguru脱敏) / exceptions / retry(tenacity)
│   ├── batch/                                       # 离线批量处理系统
│   │   ├── cli.py                                   # `python -m batch.cli run`
│   │   ├── orchestrator.py                          # 并发 + 断点续跑编排
│   │   ├── dataset_loader.py                        # JsonlDatasetLoader
│   │   ├── image_encoder.py                         # 本地/URL/base64 → 压缩 base64
│   │   ├── arena_client.py                          # Java 5 接口异步封装(JWT 自动注入)
│   │   ├── review_client.py                         # 调 /api/review
│   │   ├── task_store.py                            # SqliteTaskStore 任务状态
│   │   ├── vote_builder.py                          # VotePayload → ArenaVoteRequest
│   │   └── models.py                                # BatchJob / StageStatus
│   ├── scripts/                                     # init_rag.py / gen_dataset.py / gen_dataset_taian.py / run_batch.sh
│   ├── 泰安作文使用说明.md                          # 泰安市高二期末作文批量评审完整操作手册（v2.15）
│   ├── resource/                                    # 作文描述 txt（人工评分+评语）
│   ├── picture/                                     # 作文原图（0001.jpg, 0002.jpg... / 泰安市高二年级期末考试/*）
│   ├── tests/                                       # pytest 146 个测试
│   └── data/                                        # sample_dataset.jsonl 样例 / dataset_taian_hero.jsonl(11559 条) / images/
│
└── src/
    ├── main/
    │   ├── java/com/edu/arena/
    │   │   ├── EduArenaApplication.java             # Spring Boot 启动类(@EnableScheduling)
    │   │   │
    │   │   ├── aiclient/
    │   │   │   └── AiClient.java                    # AI 模型调用客户端(30KB,核心)
    │   │   │
    │   │   ├── controller/                          # 6 个控制器
    │   │   │   ├── AuthController.java              # 登录注册
    │   │   │   ├── BattleController.java            # 对战核心(创建/生成/投票/历史/返回前按角色脱敏投票人)
    │   │   │   ├── LeaderboardController.java       # 排行榜 + ELO 历史
    │   │   │   ├── AdminController.java             # 管理后台(模型管理/数据导出/探测)
    │   │   │   ├── AdminVoteController.java         # 管理后台-投票记录 Tab 数据接口(GET /api/admin/votes)
    │   │   │   └── PageController.java              # Thymeleaf 页面路由
    │   │   │
    │   │   ├── service/                             # 6 个服务接口 + 6 个实现
    │   │   │   ├── AuthService.java                 # 接口
    │   │   │   ├── BattleService.java               # 接口
    │   │   │   ├── EloMatchService.java             # 接口
    │   │   │   ├── LeaderboardService.java          # 接口
    │   │   │   ├── ModelService.java                 # 接口
    │   │   │   ├── VoteQueryService.java            # 接口(后台投票记录分页查询，admin 视角)
    │   │   │   └── impl/
    │   │   │       ├── AuthServiceImpl.java         # 注册/登录/BCrypt
    │   │   │       ├── BattleServiceImpl.java       # 对战核心逻辑(26KB,最大文件) + buildBattleVO 注入投票人
    │   │   │       ├── EloMatchServiceImpl.java     # ELO 匹配策略
    │   │   │       ├── LeaderboardServiceImpl.java  # 排行榜 + ELO 历史
    │   │   │       ├── ModelServiceImpl.java        # 模型 CRUD + 探测 + 数据导出
    │   │   │       └── VoteQueryServiceImpl.java    # 分页参数规整 → VoteMapper.selectVotePage
    │   │   │
    │   │   ├── entity/                              # 7 个数据库实体
    │   │   │   ├── User.java
    │   │   │   ├── Model.java
    │   │   │   ├── Task.java
    │   │   │   ├── Battle.java
    │   │   │   ├── Vote.java
    │   │   │   ├── EloHistory.java
    │   │   │   └── EssayImage.java
    │   │   │
    │   │   ├── mapper/                              # 7 个 MyBatis Mapper
    │   │   │   ├── UserMapper.java
    │   │   │   ├── ModelMapper.java                 # 含自定义 SQL(updateEloAndStats等)
    │   │   │   ├── TaskMapper.java
    │   │   │   ├── BattleMapper.java                # 含自定义 SQL(历史分页/近期对手)
    │   │   │   ├── VoteMapper.java
    │   │   │   ├── EloHistoryMapper.java
    │   │   │   └── EssayImageMapper.java
    │   │   │
    │   │   ├── dto/
    │   │   │   ├── request/                         # 8 个请求 DTO
    │   │   │   │   ├── LoginRequest.java
    │   │   │   │   ├── RegisterRequest.java
    │   │   │   │   ├── CreateBattleRequest.java
    │   │   │   │   ├── VoteRequest.java
    │   │   │   │   ├── AddModelRequest.java
    │   │   │   │   ├── ExportQuery.java             # 【v2.17】偏好数据集导出过滤参数
    │   │   │   │   ├── MessageContentItem.java      # 多模态消息构建
    │   │   │   │   └── AdminVoteQuery.java          # 后台投票记录筛选(page/size/userId/keyword/battleId/startDate/endDate)
    │   │   │   └── response/                        # 13 个响应 VO
    │   │   │       ├── LoginVO.java
    │   │   │       ├── UserVO.java
    │   │   │       ├── BattleVO.java                # 已投对战带 vote(BattleVoteVO)
    │   │   │       ├── BattleHistoryVO.java        # 新增 voter / voter_user_id 字段(controller 层脱敏后下发)
    │   │   │       ├── BattleVoteVO.java           # 对战详情里的投票子对象(6维度+理由+voter)
    │   │   │       ├── VoteResultVO.java            # 投票成功返回体，附 voter/voter_user_id
    │   │   │       ├── AdminVoteItemVO.java         # 后台投票记录条目(admin 视角，无脱敏)
    │   │   │       ├── LeaderboardVO.java
    │   │   │       ├── EloHistoryVO.java
    │   │   │       ├── MatchResultVO.java
    │   │   │       ├── ModelInfoVO.java
    │   │   │       ├── ModelProbeResultVO.java
    │   │   │       └── ModelSimpleVO.java
    │   │   │
    │   │   └── common/
    │   │       ├── cache/
    │   │       │   └── CacheService.java            # 统一 Redis 缓存(TTL/限流/统计)
    │   │       ├── config/
    │   │       │   ├── AsyncConfig.java             # 异步线程池(10核心/50最大)
    │   │       │   ├── AuthInterceptor.java         # JWT 认证拦截器
    │   │       │   ├── JacksonConfig.java           # JSON snake_case + 时间格式
    │   │       │   ├── MybatisConfig.java           # 分页插件 + 自动填充
    │   │       │   ├── PasswordConfig.java          # BCrypt
    │   │       │   ├── RedisConfig.java             # Redis JSON 序列化
    │   │       │   └── WebConfig.java               # CORS + 拦截器注册
    │   │       ├── exception/
    │   │       │   ├── BusinessException.java       # 自定义业务异常
    │   │       │   └── GlobalExceptionHandler.java  # 全局异常处理
    │   │       ├── result/
    │   │       │   └── Result.java                  # 统一响应 {code, message, data}
    │   │       └── utils/
    │   │           ├── EloCalculator.java            # ELO 积分算法(K=32)
    │   │           ├── ImageCompressUtils.java       # 图片压缩(Thumbnailator)
    │   │           ├── JwtUtils.java                 # JWT 生成/解析/验证
    │   │           └── UserContext.java              # ThreadLocal 用户上下文
    │   │
    │   └── resources/
    │       ├── application.yml                      # 应用配置
    │       ├── db/init_complete.sql                  # 数据库初始化(8张表)
    │       ├── db/migration_v2_upgrade.sql            # v2增量迁移(已有库执行)
    │       ├── picture/                             # 3张测试图片(模型探测用)
    │       ├── static/favicon.svg
    │       └── templates/                           # Thymeleaf 前端页面
    │           ├── base.html                        # 公共布局(侧边栏导航)
    │           ├── index.html                       # 登录/注册页
    │           ├── battle.html                      # 对战评测页(59KB,最大前端文件)
    │           ├── leaderboard.html                 # 排行榜页(含ELO趋势图)
    │           ├── history.html                     # 对战历史页
    │           └── admin.html                       # 后台管理页
    │
    └── test/
        └── java/.../ImageCompressUtilsTest.java     # 图片压缩单元测试
```

---

## 四、数据库设计 (8 张表)

### 4.1 ER 关系图

```
users(1) ──< tasks(N) ──< battles(N) ──< votes(N)
                              │               │
                              │           elo_history(N)
                              │
                         models(N:M via battles)
                              │
                         essay_images(预留)

quality_logs ── votes (1:N)
```

### 4.2 表结构摘要

| 表名 | 说明 | 关键字段 |
|------|------|----------|
| **users** | 用户表 | `id`, `username`, `password(BCrypt)`, `role(admin/teacher)` |
| **models** | AI 模型表 | `id`, `model_id(API调用)`, `name`, `company`, `elo_score(默认1500)`, `input_modalities`, `total_matches`, `win_count`, `lose_count`, `tie_count`, `status(active/inactive)`, `is_new`, `positioning_done` |
| **tasks** | 任务表(用户提交的作文) | `id`, `user_id`, `essay_title`, `essay_content(允许NULL)`, `grade_level(默认"初中")`, `has_images`, `images_json(LONGTEXT)`, `image_count` |
| **battles** | 对战表 | `id`, `task_id`, `model_a_id`, `model_b_id`, `display_order(normal/swapped)`, `status(generating/ready/voted/failed)`, `match_type`, `response_a`, `response_b`, `winner(A/B/tie)` |
| **votes** | 投票表 | `id`, `battle_id`, `user_id`, `winner`, 5 个子维度投票 + 5 个理由, `dim_overall(A/B/tie,决定winner)`, `dim_overall_reason`, `vote_time`, ELO 前后快照, `UNIQUE(battle_id, user_id)` |
| **elo_history** | ELO 积分变化历史 | `id`, `model_id`, `elo_score`, `battle_id`, `recorded_at` |
| **quality_logs** | 质量检查日志 | `id`, `vote_id`, `check_type`, `result(warning/error)`, `detail` |
| **essay_images** | 图片附件表(预留) | `id`, `task_id`, `filename`, `file_path`, `file_size` |

### 4.3 模型池当前分布 (v2.9, active=30, inactive=11, 合计 41)

| 厂商 | active 数量 | 代表模型 |
|------|------------|----------|
| OpenAI | 10 | gpt-5.4, gpt-5.4-mini, gpt-5.2, gpt-5.1, gpt-5, gpt-5-mini, gpt-4.1, gpt-4.1-mini, gpt-4o, gpt-4o-2024-11-20, gpt-4o-mini |
| Anthropic | 5 | claude-sonnet-4-5/-4-6/-4-0, claude-opus-4-5/-4-6/-4-7/-4-0/-4-1 |
| Google | 4 | gemini-3.1-pro-preview, gemini-2.5-pro, gemini-2.5-flash, gemini-3-flash-preview |
| xAI | 2 | grok-4, grok-4-fast-reasoning |
| Alibaba | 2 | qwen3.6-plus, qwen3.5-plus |
| Zhipu | 2 | glm-5v-turbo, glm-4.5v |
| 其他(原有未分类) | ~5 | — |

> 本次扩容使用 `scripts/model_manage.py` + `scripts/verify_and_fix.py` 自动化完成：
> 1. 调用 `/api/admin/models/probe` + 带本地图片的 chat 请求筛查多模态可用性；
> 2. 下架不能识别图片或超时的模型；
> 3. 用 AiHubMix 可用模型清单批量 POST 到 `/api/admin/models`，添加后立即用 base64 图片做可用性验证，不通过则回退；
> 4. 由于平台未提供 DELETE 接口，完全剔除模型通过 pymysql 直连 MySQL 执行 `DELETE` 完成。

---

## 五、API 接口清单

### 5.1 认证接口 (`AuthController`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/register` | 用户注册 | ❌ |
| POST | `/api/login` | 用户登录，返回 JWT | ❌ |

### 5.2 对战接口 (`BattleController`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| POST | `/api/battle/create` | 创建对战(提交题目+图片，图片必传) | ✅ |
| POST | `/api/battle/{id}/generate` | 生成批改结果(并行调用2模型) | ✅ |
| GET | `/api/battle/{id}` | 获取对战详情（投票前匿名隐藏模型名，投票后揭晓；已投票时带 `vote` 子对象，`vote.voter` 按当前用户角色脱敏） | ✅ |
| POST | `/api/battle/{id}/vote` | 投票(6维度+理由，整体评价决定胜负)，返回体附 `voter`/`voter_user_id` | ✅ |
| GET | `/api/battle/history` | 对战历史(分页)，记录携带 `voter`（按角色脱敏） | ✅ |

> **投票人脱敏策略**（服务端执行，见 `BattleController`）：
> - `admin` 角色看到全部真实投票人（displayName 优先，回退 username）
> - 其他角色（teacher）只有 `voterUserId == currentUserId` 时显示真名，其他投票一律返回 `voter="匿名"` 且不回传 `voter_user_id/voter_username/voter_display_name`
> - 脱敏放在 controller 层，`BattleServiceImpl` 写入缓存的是原始投票人，保证多角色共享缓存不会串号

### 5.3 排行榜接口 (`LeaderboardController`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/leaderboard` | 获取模型排行榜 | ✅ |
| GET | `/api/leaderboard/elo-history` | 获取ELO变化历史(前10模型) | ✅ |

### 5.4 管理接口 (`AdminController` + `AdminVoteController`)

| 方法 | 路径 | 说明 | 认证 |
|------|------|------|------|
| GET | `/api/admin/models` | 获取所有模型列表 | ✅ (admin) |
| POST | `/api/admin/models` | 添加模型(自动拉取API信息) | ✅ (admin) |
| PUT | `/api/admin/models/{id}/toggle` | 切换模型启用/禁用 | ✅ (admin) |
| GET | `/api/admin/stats` | 获取平台统计(总对战/总用户) | ✅ (admin) |
| GET | `/api/admin/export/dataset.zip` | **偏好数据集导出（唯一主接口）**：流式输出 ZIP，内含 `data.jsonl`（每条 battle 完整数据：作文/题目/年级/A&B 批改/六维度评分+理由/ELO 前后/投票时长）、`images/task_{id}/*`（作文图片按 task 去重）、`manifest.json`（元信息）。**仅导 `status=voted`**，脏数据自动过滤。查询参数：`winner / modelId(主键或 model_id) / startDate / endDate / battleId / includeImages / limit` | ✅ (admin) |
| POST | `/api/admin/models/probe` | 探测所有模型可用性 | ✅ (admin) |
| GET | `/api/admin/votes` | **后台投票记录分页查询**；参数 `page/size/userId/keyword/battleId/startDate/endDate`，admin 视角返回完整投票人与投票明细 | ✅ (admin) |

### 5.5 页面路由 (`PageController`)

| 路径 | 模板 | 说明 |
|------|------|------|
| `/` | `index.html` | 登录/注册页 |
| `/battle` | `battle.html` | 对战评测页 |
| `/leaderboard` | `leaderboard.html` | 排行榜页 |
| `/history` | `history.html` | 对战历史页 |
| `/admin` | `admin.html` | 后台管理页 |

---

## 六、核心类详解

### 6.1 `AiClient.java` — AI 模型调用客户端

- **位置**: `com.edu.arena.aiclient.AiClient`
- **职责**: 统一封装对 AI 模型的调用
- **核心方法**:
  - `generate(modelId, task)` — 同步调用模型生成批改内容
  - `generateStream(modelId, task)` — SSE 流式调用
  - `fetchModelInfo(modelId)` — 从 API 获取模型元信息
  - `buildProbeTask(images)` — 构建探测任务
  - `imageFileToBase64(bytes)` — 图片转 Base64
  - `buildPrompt(task)` — 纯文本 Prompt 构建（无 essayContent 时提示"以图片形式提供"）
  - `buildMessageContent(task)` — 多模态 Prompt 构建（含图片识别 4 步指引：辨认手写→按序拼接→关注工整度→标注模糊区域）
- **特点**:
  - 以**图片为主要输入方式**，强化手写体识别和段落分割指引
  - 支持文本 + 图片多模态输入（`MessageContentItem` 构建 content 数组）
  - 使用 OkHttp 发送 HTTP 请求
  - SSE 流式解析（逐行读取 `data:` 前缀）
  - 配置项: `ai.api-key`, `ai.base-url`

### 6.2 `BattleServiceImpl.java` — 对战核心逻辑

- **位置**: `com.edu.arena.service.impl.BattleServiceImpl`
- **是项目最大最核心的文件 (26KB, 642行)**
- **核心流程**:
  1. `createBattle()` — **图片必传验证** → 图片压缩 → 创建 Task（essayContent 可为空，gradeLevel 默认"初中"） → ELO 匹配选模型 → 创建 Battle
  2. `generateBattle()` — 并行调用 2 模型(线程池) → Fallback 机制 → 保存结果
  3. `vote()` — 投票转换(left/right→A/B) → **整体评价维度直接决定 winner** → ELO 计算 → 更新模型分数 → 记录历史 → 清缓存
  4. `getBattleDetail()` — 缓存优先查询
  5. `getBattleHistory()` — 分页查询
  6. `buildBattleVO()` — **匿名化处理**: status=ready 时不返回 modelLeft/modelRight，status=voted 时揭晓模型名
- **关键设计**:
  - **线程池**: 4核心/20最大/100队列/CallerRunsPolicy
  - **每日限流**: 每用户每天最多 50 次对战
  - **模型 Fallback**: 主模型失败，自动尝试备选模型(最多4个)
  - **显示顺序随机化**: `displayOrder` 为 `normal` 或 `swapped`，投票时需转换
  - **匿名化**: 通过后端条件性返回杜绝投票前通过 API/DevTools 获取模型名称

### 6.3 `EloMatchServiceImpl.java` — ELO 匹配策略

- **匹配算法**:
  1. 随机选一个基准模型
  2. 在 ELO ±100 范围内找候选
  3. 排除最近 50 场对战中已配对过的组合
  4. 按 ELO 差值加权随机选择（差值越小权重越高: `weight = 1/(|diff|+1)`）
  5. 若候选池为空，扩大到 ±200 → ±500 → 纯随机
- **匹配类型**: `elo`(正常匹配), `elo_expanded`(扩大范围), `random`(纯随机)

### 6.4 `EloCalculator.java` — ELO 积分算法

- K 因子 = 32
- 期望得分: `E_A = 1 / (1 + 10^((elo_B - elo_A) / 400))`
- 新分数: `new_elo = old_elo + K * (actual - expected)`
- 支持 A 胜(1.0)、B 胜(0.0)、平局(0.5)

### 6.5 `CacheService.java` — 统一缓存服务

- **缓存 Key 前缀**: `edu_arena:`
- **TTL 策略**:
  - `TTL_SHORT` = 5 分钟（对战详情）
  - `TTL_MEDIUM` = 15 分钟（排行榜、活跃模型列表）
  - `TTL_LONG` = 1 小时
- **功能**:
  - 排行榜缓存(`leaderboard`)
  - ELO 历史缓存(`elo_history`)
  - 活跃模型缓存(`active_models`)
  - 对战详情缓存(`battle:{id}`)
  - 用户每日对战计数限流(`user_battle_limit:{userId}:{date}`)
  - 平台统计计数器(`stats:total_battles`, `stats:total_votes`, `stats:daily_battles`)

### 6.6 `ImageCompressUtils.java` — 图片压缩

- 最大边长: 1600px（激进模式 1024px）
- JPEG 质量: 0.72（激进模式 0.58）
- 若压缩后体积未下降则回退原图
- 使用 Thumbnailator 库缩放

---

## 七、认证与安全

### 7.1 JWT 认证

- **生成**: 登录成功后返回 JWT Token
- **内容**: `subject=userId`, `claims={username, role}`
- **有效期**: 24 小时（86400000ms）
- **传递方式**: `Authorization: Bearer <token>` 请求头

### 7.2 拦截器 (`AuthInterceptor`)

- **放行路径**: `/api/login`, `/api/register`, 页面路由(`/`, `/battle`, `/leaderboard`, `/history`, `/admin`), Swagger 文档, 静态资源
- **拦截逻辑**: 验证 JWT → 解析用户信息 → 存入 `UserContext`(ThreadLocal) → 请求结束清除
- **调试旁路**: `edu-arena.auth-bypass-enabled=true` 时跳过认证（当前已关闭）

### 7.3 密码安全

- 使用 BCrypt 加密存储
- 默认管理员: `admin` / `admin123`

---

## 八、配置说明 (`application.yml`)

```yaml
server.port: 5001                    # 服务端口
spring.datasource.url: jdbc:mysql://... # MySQL 连接
spring.data.redis.host: ...          # Redis 连接

# HikariCP 连接池（v2.15.1 上调以支撑批量评审并发）
spring.datasource.hikari:
  maximum-pool-size: 80              # 最大连接数（默认10→20→80，支撑 agent-review-service 批量 -c 10~20 并发）
  minimum-idle: 10                   # 最小空闲连接
  idle-timeout: 300000               # 空闲超时 5min
  connection-timeout: 30000          # 获取连接超时 30s
  max-lifetime: 1800000              # 连接最大生命周期 30min
  leak-detection-threshold: 120000   # 连接泄漏检测阈值 2min（超过仍未归还会打 warn 日志）
  validation-timeout: 5000           # 连接校验超时 5s
  keepalive-time: 300000             # 空闲连接保活探测 5min

jwt.secret: ...                      # JWT 密钥(≥256bit)
jwt.expiration: 86400000             # JWT 有效期(24h)

ai.api-key: sk-...                   # AI API Key(AiHubMix)
ai.base-url: https://api.aihubmix.com/v1/chat/completions  # AI API 地址

edu-arena.auth-bypass-enabled: false # 认证旁路开关
```

> ✅ **长事务已在 v2.15.2 拆分**：`BattleServiceImpl.generateBattle` 已移除方法级 `@Transactional`，采用 "读事务 → 无事务 LLM 调用 → 写事务" 三段式（通过 `@Lazy` 自注入代理触发 `loadGenerateContextTx` / `persistGenerateResultTx`）；`createBattle` 的图片压缩也已移到事务外。现在事务内只剩毫秒级 DB 操作，HikariCP 连接不会再被慢 IO 长时间占用。

---

## 九、Maven 依赖

| 依赖 | 版本 | 用途 |
|------|------|------|
| `spring-boot-starter-web` | 3.2.3 | Web 框架 |
| `spring-boot-starter-validation` | 3.2.3 | 参数校验(@NotBlank/@Size/@Pattern) |
| `spring-boot-starter-thymeleaf` | 3.2.3 | 模板引擎 |
| `spring-boot-starter-data-redis` | 3.2.3 | Redis 客户端 |
| `mybatis-plus-spring-boot3-starter` | 3.5.7 | ORM 框架 |
| `mysql-connector-j` | 运行时 | MySQL 驱动 |
| `jjwt-api/impl/jackson` | 0.12.6 | JWT 库 |
| `okhttp` | 4.12.0 | HTTP 客户端(AI 调用) |
| `hutool-all` | 5.8.35 | 工具包(JSON 等) |
| `thumbnailator` | 0.4.20 | 图片缩放压缩 |
| `spring-security-crypto` | 6.2.2 | BCrypt 密码加密 |
| `knife4j-openapi3-jakarta-spring-boot-starter` | 4.5.0 | API 文档 |
| `lombok` | — | 代码简化 |

---

## 十、前端页面说明

| 页面 | 文件 | 功能 |
|------|------|------|
| 登录/注册 | `index.html` | 用户名+密码登录，注册新账号，JWT 存 localStorage |
| 对战评测 | `battle.html` | 提交作文(题目+图片，图片必传) → 等待生成 → **匿名显示左右批改(不显示模型名)** → **6 维度投票(整体评价决定胜负)** → **投票后揭晓模型名** |
| 排行榜 | `leaderboard.html` | 模型 ELO 排名表 + ELO 变化趋势图(Chart.js) + 模型详情弹窗 |
| 对战历史 | `history.html` | 分页浏览对战记录（已投票对战显示模型名；列表新增「投票人」列；详情弹窗顶部 chip + 投票详情区均显示投票人，全部按后端脱敏结果展示） |
| 后台管理 | `admin.html` | 模型管理(添加/启用/禁用) + 统计面板 + 偏好数据导出(JSON/JSONL) + 模型探测 + **投票记录 Tab**（按投票人/对战 ID/日期分页筛选 `GET /api/admin/votes`） |

**公共布局** (`base.html`): 左侧深色侧边栏(Logo + 导航链接 + 用户信息 + 登出)

---

## 十一、子项目: agent-review-service (Python)

> 详见 `agent-review-service/README.md`。此处为速览。

### 概述

独立的 Python 服务（端口 `8100`），提供两大协同能力：
1. **Multi-Agent 评审服务**：基于 LangGraph 的 DAG 工作流（预处理 → 6 维度 Agent 并行 → 仲裁 → 决策器），替代人类专家评审两份 AI 批改。
2. **离线批量处理系统**：读 JSONL 清单，批量调 Java 平台完成"创建→生成→评审→投票"全链路，支持断点续跑。

### 评审模式（v2.16）

服务运行时支持两种评审链路，通过环境变量 `REVIEW_MODE` 切换，默认 **single**：

| 模式 | LLM 调用次数 | 模型 | base_url | 配置项 | 适用场景 |
|------|---------------|------|----------|--------|----------|
| **single**（默认） | **1 次/场** | `deepseek-v4-flash`（默认）/ `deepseek-v4-pro` | `https://api.deepseek.com`（OpenAI 兼容） | `AI_API_KEY_SINGLE` / `AI_BASE_URL_SINGLE` / `AI_REVIEW_MODEL_SINGLE` | 默认链路，最快/最省/最不易被风控；按固定 5 步 CoT 一次性产出 6 维评分 + final_winner |
| **multi**（fallback） | 9~10 次/场 | `gpt-5-mini`（维度）/ `gpt-5`（仲裁） | `https://api.aihubmix.com/v1`（AiHubMix） | `AI_API_KEY` / `AI_BASE_URL` / `AI_REVIEW_MODEL` / `AI_ARBITRATOR_MODEL` | 旧链路，需要细粒度多 Agent 复盘时启用 |

实现要点：
- single 模式由 `app/review/single_agent.py::run_single_review` 完成；prompt 定义在 `prompts.py::SINGLE_AGENT_SYSTEM` + `single_agent_user`。
- 固定 5 步 CoT：① 通读 A 提炼优点/问题/建议 → ② 通读 B 同样提炼 → ③ 对 theme/imagination/logic/language/writing 五维度对比打分 → ④ 综合前 5 维评 overall → ⑤ 自检（分差 ≤0.5 必须 tie、final_winner==overall.winner、evidence 必须摘自原文）后输出严格 JSON。
- 输入仅含题目/年级/批改要求/A 全文/B 全文，**不带 skills、不带 RAG、不带作文图片**，最大化降低 token 与风控概率。
- `LLMClient` 已是 OpenAI 兼容协议，可直连 DeepSeek 端点；single 与 multi 各自持有独立 LLMClient 实例，互不干扰。
- `ReviewService` 在初始化时根据 `review_mode` 决定是否加载 LangGraph，single 模式下不加载，避免启动开销与不必要依赖。
- 对外契约（`ReviewResponse` / `VotePayload`）零变更，Java 端零感知。

### 技术栈

FastAPI + LangGraph + ChromaDB + OpenAI SDK（AiHubMix）+ Pydantic v2 + httpx + SQLite + loguru + tenacity + Pillow

### 核心功能

1. **LangGraph DAG 评审**：`review/graph.py` 编排 `START → preprocess → dispatch(6×Send) → dimension_agent → arbitrator → END`；通过 `Annotated[List, operator.add]` 合并 6 个并行维度结果。
2. **6 维度**：`theme/imagination/logic/language/writing/overall`，每维度 Agent 输出 `score_a/score_b/winner/reason/evidence/confidence`；**OVERALL 直接决定最终 winner**，仲裁强约束 `final_winner == OVERALL.winner`。
3. **RAG 知识库**：ChromaDB 三集合 `rubric/exemplar/gold_case`，按维度感知召回 + LRU 缓存；支持 `OpenAIEmbedding` 和 hash 伪向量降级。
4. **Skill 工具包**：6 个本地纯函数工具（`text_stats/grammar_check/duplicate_detect/feedback_compare/coverage_analyzer/hallucination_check`）通过 `SkillRegistry` 注册，不引入 MCP server 复杂度。
5. **投票决策器** `VoteMapper`：A/B → left/right；子维度按 `|score_a-score_b| < 0.5` 强制 tie；OVERALL 采信 Agent winner。
6. **断点续跑**：`SqliteTaskStore` 记录阶段 `pending/created/generated/reviewed/voted/done/failed`，`BatchOrchestrator` 按阶段排名重入。
7. **契约层共享**：`app/contracts/` Pydantic v2 DTO 严格对齐 Java 端 `JacksonConfig` snake_case，字段可直接 dump 成 REST 请求体。

### 与 Java 平台交互

完全通过 REST API，**不修改 Java 代码**：

| Java 接口 | 用途 | 对应 `ArenaClient` 方法 |
| --- | --- | --- |
| `POST /api/login` | 获取 JWT | `login()` |
| `POST /api/battle/create` | 创建对战（images 必传，纯 base64） | `create_battle()` |
| `GET  /api/battle/{id}/generate` | 触发生成 | `generate()` |
| `GET  /api/battle/{id}` | 查询详情（轮询用） | `get_battle()` |
| `POST /api/battle/{id}/vote` | 提交 6 维投票（left/right/tie） | `vote()` |

### 关键对齐点

- **投票值**：Java `VoteRequest` `@Pattern(^(left\|right\|tie)$)` 强校验，`VoteMapper` 负责把内部 A/B 转成 left/right。
- **图片**：纯 base64（不带 `data:image` 前缀），`ImageEncoder` 自动 Pillow 压缩至 ≤2MB/张。
- **响应字段**：`BattleVO` 只返回 `response_left/right`（无 `response_a/b`）；约定 `left==A，right==B`。
- **幂等**：重复投票遇 `409/"已投票"` 视为成功；同一 `item_id` 重跑从最后成功阶段继续。

### 快速启动

```bash
cd agent-review-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 配置 AI_API_KEY / ARENA_* 等

# 初始化 RAG（可选）
python scripts/init_rag.py --reset

# 准备批量数据：将图片放入 picture/，描述 txt 放入 resource/
# 生成 JSONL 清单（支持两种行格式，按行自动识别）
#   - 格式 A 空格分隔（label_cn.txt）：<图片> <题目> <5分> <总分> <评语>
#   - 格式 B 分号分隔（label_en.txt）：<图片>;<题目>;<分1>;...;<分5>;<总分>;<评语>
python scripts/gen_dataset.py                        # resource/*.txt + picture/ → data/dataset.jsonl
# 指定路径 + 按语种分开跑（图片目录不同）
python scripts/gen_dataset.py --txt resource/picture/label_cn.txt \
    --pictures resource/picture/chinese --output data/dataset_cn.jsonl --grade 初中
python scripts/gen_dataset.py --txt resource/picture/label_en.txt \
    --pictures resource/picture/english --output data/dataset_en.jsonl --grade 初中
cat data/dataset_cn.jsonl data/dataset_en.jsonl > data/dataset_all.jsonl  # 合并 100 条

# ---- 方式一：手动分步启动 ----

# 终端 1：启动 Multi-Agent 评审服务
python -m app.main                                   # http://localhost:8100/docs
# 等待 "Uvicorn running on http://0.0.0.0:8100"

# 终端 2：运行批量编排器
python -m batch.cli run -i data/sample_dataset.jsonl -c 3 --dry-run   # 只评审不投票
python -m batch.cli run -i data/sample_dataset.jsonl -c 3             # 正式评审 + 投票
python -m batch.cli status                                            # 查看任务状态

# ---- 方式二：一键脚本（推荐生产使用）----
# 自动启动评审服务(后台) → 等健康检查 → 批量任务 → 退出自动清理
./scripts/run_batch.sh -i data/sample_dataset.jsonl -c 3
./scripts/run_batch.sh -i data/sample_dataset.jsonl -c 3 --dry-run

# 前置条件：确保 Java 对战平台(:5001)已启动、.env 中 AI_API_KEY 和 ARENA_* 已配置
# 处理流程：pending → created → generated → reviewed → voted → done
# 断点续跑：SQLite 记录每条进度，中断后重启自动从最后成功阶段继续
```

---

## 十二、关键设计模式与注意事项

### 12.1 并发设计

- **模型调用线程池**: `BattleServiceImpl` 使用有界线程池（4核心/20最大/100队列）并行调用两个模型
- **CallerRunsPolicy**: 队列满时由调用者线程执行，避免任务丢失
- **优雅关闭**: `@PreDestroy` 关闭线程池，等待 60 秒

### 12.2 缓存策略

- 排行榜/模型列表: Redis 缓存 15 分钟
- 对战详情(已完成): Redis 缓存 5 分钟
- 生成中的对战: 不缓存，实时查询
- 投票后: 主动清除相关缓存(battle/model/leaderboard)

### 12.3 容错设计

- **模型 Fallback**: 主模型调用失败，自动尝试最多 4 个备选模型
- **图片压缩降级**: 压缩失败回退原图
- **唯一约束**: `votes` 表 `UNIQUE(battle_id, user_id)` 防重复投票，代码层捕获 `DuplicateKeyException`

### 12.4 显示顺序与投票转换

- 创建对战时可能随机交换 A/B 的显示顺序（`displayOrder=swapped`）
- 投票时前端提交 `left`/`right`，后端根据 `displayOrder` 转换为 `A`/`B`
- 查询详情时也需要根据 `displayOrder` 转换 winner 方向

### 12.5 匿名化设计

- **投票前（status=ready）**: 后端 `buildBattleVO()` 不返回 `modelLeft`/`modelRight`（置为 null）
- **投票后（status=voted）**: 后端返回完整模型信息，前端在"投票后"区域揭晓
- **设计原则**: 从后端源头阻断信息泄露，杜绝通过 API/DevTools 获取模型名称

### 12.6 JSON 序列化

- 全局使用 `snake_case` 命名策略（`JacksonConfig`）
- 日期格式: `yyyy-MM-dd HH:mm:ss`
- Redis 使用 Jackson JSON 序列化（含类型信息）

---

## 十三、快速上手

### 13.1 环境要求

- Java 17+
- MySQL 8.x
- Redis 6.x+
- Maven 3.x

### 13.2 启动步骤

```bash
# 1a. 全新安装 - 初始化数据库
mysql -u root -p < src/main/resources/db/init_complete.sql

# 1b. 已有数据库 - 执行v2增量迁移
mysql -u root -p < src/main/resources/db/migration_v2_upgrade.sql

# 2. 修改 application.yml 中的数据库/Redis/AI 配置

# 3. 启动
mvn spring-boot:run

# 4. 访问 http://localhost:5001
# 默认管理员: admin / admin123
```

### 13.3 启动 agent-review-service（可选）

```bash
cd agent-review-service
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # 配置 AI_API_KEY / ARENA_BASE_URL / ARENA_USERNAME / ARENA_PASSWORD 等

# 启动评审服务（端口 8100）
python -m app.main                                      # 或 uvicorn app.main:app --port 8100

# ---- 批量评审（需另起终端，且 Java 平台 :5001 已启动）----

# 方式一：手动分步
python -m batch.cli run -i data/sample_dataset.jsonl --dry-run   # 只评审不投票
python -m batch.cli run -i data/sample_dataset.jsonl -c 3        # 正式评审 + 投票
python -m batch.cli status                                       # 查看任务状态

# 方式二：一键脚本（自动启服务 + 等就绪 + 跑批 + 退出清理）
./scripts/run_batch.sh -i data/sample_dataset.jsonl -c 3
```

详见 `agent-review-service/README.md`。

---

## 十四、文件修改影响范围速查

| 要修改的功能 | 涉及文件 |
|-------------|----------|
| 新增 API 接口 | `controller/` + `service/` + `service/impl/` + 可能的 `dto/` |
| 新增数据库表 | `entity/` + `mapper/` + `db/init_complete.sql` |
| 修改投票维度 | `VoteRequest.java` + `Vote.java` + `BattleServiceImpl.vote()` + `battle.html` + `init_complete.sql` + `agent-review-service/app/contracts/` + `app/review/` |
| 修改胜负判定逻辑 | `BattleServiceImpl.vote()` — 当前基于 `dimOverall` 字段 |
| 修改评审 Agent / LLM 行为 | `agent-review-service/app/review/`（`prompts.py` / `nodes/` / `graph.py` / `single_agent.py` / `service.py`） |
| 切换评审模式 / 替换评审模型 | `agent-review-service/.env`（`REVIEW_MODE` / `AI_API_KEY_SINGLE` / `AI_BASE_URL_SINGLE` / `AI_REVIEW_MODEL_SINGLE`），无需改代码 |
| 修改离线批量流程 | `agent-review-service/batch/`（`orchestrator.py` / `arena_client.py` / `cli.py`） |
| 修改匿名化行为 | `BattleServiceImpl.buildBattleVO()` + `battle.html` + `history.html` |
| 修改投票人追溯/脱敏逻辑 | `BattleController.desensitize*()` + `BattleServiceImpl.loadBattleVote()/vote()` + `BattleMapper.selectHistoryPage` + `VoteMapper.selectVotePage` + `BattleVoteVO`/`AdminVoteItemVO` |
| 修改 ELO 算法 | `EloCalculator.java` + `BattleServiceImpl.vote()` |
| 修改模型匹配策略 | `EloMatchServiceImpl.java` |
| 修改 AI Prompt/调用逻辑 | `AiClient.java`（`buildPrompt()` 和 `buildMessageContent()`） |
| 修改认证逻辑 | `AuthInterceptor.java` + `JwtUtils.java` + `WebConfig.java` |
| 修改前端页面 | `templates/*.html`（注意 base.html 是公共布局） |
| 修改缓存策略 | `CacheService.java` |
| 修改偏好数据集导出 | `controller/AdminController.java`（`/api/admin/export/dataset.zip`）+ `service/ExportService(Impl).java` + `dto/request/ExportQuery.java` + `templates/admin.html`（数据导出 Tab） |
| 新增模型字段 | `Model.java` + `models` 表 + `AddModelRequest.java` + `LeaderboardVO.java` + `admin.html` |

---

## 十五、版本变更记录

### v2.17.3 (2026-05-11) — 偏好数据集导出跨境慢优化（剔除 LONGTEXT + 并发拉图）

- **现象**：4 条 voted 数据导出耗时 ~11s，单看代码逻辑根本不应该这么慢。
- **根因实测**：
  - app 服务器（`8.219.130.23`，阿里云海外）↔ MySQL（`180.76.229.245`，百度云国内）`ping` RTT = **207ms**，跨境跨云链路。
  - `ExportServiceImpl.writeJsonl` 第一遍批量拉 task 用了 `taskMapper.selectBatchIds(taskIds)`，MyBatis-Plus 默认 `select *` 把 `tasks.images_json`（LONGTEXT，每条最多 ~5MB base64）一并跨境拉回；
  - 第二遍打包图片时 `taskMapper.selectById(taskId)` 又把同一字段再拉一次。
  - 4 条数据 ≈ 20MB base64 × 2 遍 = 40MB 跨境，加上 RTT 串行叠加，正好 ~11s。
- **改动文件**：仅 `src/main/java/com/edu/arena/service/impl/ExportServiceImpl.java`。
- **核心优化**：
  1. **第一遍排除 LONGTEXT 列**：批量拉 task 改用 `taskMapper.selectList(new LambdaQueryWrapper<Task>().select(Task::getId, Task::getUserId, Task::getEssayTitle, Task::getEssayContent, Task::getGradeLevel, Task::getRequirements, Task::getHasImages, Task::getImageCount, Task::getCreatedAt).in(Task::getId, taskIds))`，**显式不取 `images_json`**。jsonl 阶段只需要 `image_count/has_images` 即可决定文件路径数。
  2. **第二遍并发拉单条 imagesJson**：新增 `writeImagesParallel(Set<Long> taskIdsWithImages, ZipOutputStream zip)`，使用固定线程池 `IMAGE_FETCH_CONCURRENCY=4`（daemon 线程，名 `export-img-fetch`）一次性 `pool.submit(() -> taskMapper.selectById(taskId).getImagesJson())`，主线程按提交顺序 `future.get()` 串行写 ZIP，**串行 N×RTT 变成 ≈ N/4 × RTT**。注意：并发线程从连接池单独借连接，独立于外层 `@Transactional(readOnly=true)` 的事务连接，结束立即归还，不会触发 HikariCP leak 告警。
  3. **路径推断方式调整**：新方法 `computeImageRelPathsByCount(Task task)` 仅依赖 `image_count/has_images` 生成 `images/task_{id}/{NN}.jpg` 路径列表（统一标 .jpg）；真实后缀在第二遍解码时由 `detectImageExt(b64)` 按 base64 魔数（`/9j/`→jpg、`iVBOR`→png、`UklGR`→webp、`R0lGOD`→gif）重新决定并写入 ZIP entry。**已知偏差**：jsonl 内 `essay_images` 字段后缀与 ZIP 实际文件后缀可能不一致；消费方应按 `images/task_{id}/{NN}.*` 通配定位。
  4. **去掉 v2.17.2 的内存缓存**：不再用 `Map<Long,String> taskImagesJson` 缓存原文（既然第一遍根本没拉 imagesJson 回来），改回轻量 `Set<Long> taskIdsWithImages`，内存峰值进一步下降。
  5. **细粒度耗时日志**：每页输出 `[导出] page=N 拉取耗时 battle(X)=Xms task(Y-noBlob)=Yms vote(Z)=Zms model(W)=Wms`；每个 task 输出 `[导出] task=ID fetch=Ams decode+zip=Bms 写入 K 张 解码后字节=...`，下次性能回归可立即定位是 SQL 慢、网络慢还是解码慢。
- **预期收益**：4 条数据 ~11s → ~2s（第一遍少传 ~20MB base64 / 第二遍 4 路并发把 4×0.5s = 2s 的 LONGTEXT 拉取压成 ~0.5s）；数据量越大、图片越多收益越显著（线性 → 1/4）。
- **未触动**：`@Transactional(readOnly=true, timeout=1800)`、`StreamingResponseBody`、Nginx/异步超时配置、ZIP 顺序（仍是 data.jsonl → images → manifest）、对外接口/响应结构均无变化，前端无感。
- **后续可选优化**（本次未做）：① 把 `tasks.images_json` 拆到独立表或对象存储 URL，根治跨境 LONGTEXT 传输；② 给前端加下载进度条（需新增 `/api/admin/export/preview` 估算总字节 + `fetch` 监听 `received/total`）。

### v2.17 (2026-05-11) — 偏好数据集导出接口重做（仅保留 ZIP 主接口）

- **背景**：旧的 `GET /api/admin/export/preference`（JSON）/ `GET /api/admin/export/jsonl` 仅返回 5 个字段（`battleId / modelA(主键ID) / modelB(主键ID) / result / createdAt`），下游既不知道是哪个模型、也拿不到作文/批改/六维度评分；实现上 `ModelServiceImpl.exportPreferenceJson/Jsonl` 直接 `battleMapper.selectList(null)` 一次性拉全表 → 序列化为字符串 → `getBytes()` 返回，体量大就 OOM；且不过滤脏数据，会把 `generating / ready / failed` 也导出去。
- **目标**：用一个**唯一主接口**完整覆盖训练/标注/分析三类用户需求，强制只导 `voted` 数据，可流式应对大库存。
- **改动**：
  - **删除接口**：`/api/admin/export/preference`、`/api/admin/export/jsonl` 整体移除；`ModelService` 与 `ModelServiceImpl` 同步删除 `exportPreferenceJson()` / `exportPreferenceJsonl()` 两个方法及残留 `cn.hutool.json.JSONUtil`、`Battle`、`HashMap`/`Map` 导入。
  - **新增主接口**：`GET /api/admin/export/dataset.zip`，唯一导出端点，admin 鉴权。
  - **新增 DTO**：`dto/request/ExportQuery.java`（`winner / modelId / startDate / endDate / battleId / includeImages / limit`，全部可选）。
  - **新增服务**：`service/ExportService.java` + `service/impl/ExportServiceImpl.java`。
  - **前端重做**：`templates/admin.html` 「数据导出」Tab 改为下拉/日期/复选框筛选 + `fetch + Blob` 携 JWT 下载（旧 `<a download>` 链接无法带 token）。
- **导出 ZIP 包结构**：
  ```
  preference_export_yyyyMMdd_HHmmss.zip
  ├── manifest.json   # schema_version / exported_at / total_battles / total_images / include_images / filter
  ├── data.jsonl      # 每行一条 battle 完整数据
  └── images/
      └── task_{taskId}/01.jpg, 02.jpg, ...   # 按 task 去重，多场 battle 共享只存一份
  ```
- **`data.jsonl` 单行 schema（`schema_version=1.0`）**：
  - `battle`: `battle_id / status / match_type / display_order / created_at / winner / error_message`
  - `task`: `task_id / essay_title / essay_content / grade_level / requirements / has_images / image_count / essay_images[]`（`essay_images` 是相对路径数组，指向 ZIP 内 `images/task_{id}/...`）
  - `model_a` / `model_b`: `id / model_id / name / company`（既给 DB 主键又给 `model_id` 字符串，下游可读）
  - `responses`: `response_a / response_b`（A、B 模型完整批改原文）
  - `vote`: `vote_id / voter_user_id / winner / dimensions{theme,imagination,logic,language,writing,overall}{winner,reason} / vote_time_seconds / elo{a_before,a_after,b_before,b_after} / created_at`
- **关键工程要点**：
  - **强制只导 `status=voted`**：在 `LambdaQueryWrapper` 中硬编码 `eq("status", "voted")`，脏数据永不外泄。
  - **分页 200 条/页**：`battleMapper.selectPage(...)`，避免一次性加载全表。
  - **临时文件落 jsonl**：先把所有行写到 `Files.createTempFile(...)`，最后再整体放进 ZIP；不然 `ZipOutputStream` 同时只能写一个 entry，jsonl 写一半要切去写图片就会破坏 entry 结构；finally 删除临时文件。
  - **图片不缓存到内存**：第一遍只把"有图片的 task_id"收集成 `LinkedHashSet<Long>`；第二遍按 task_id 单条 `taskMapper.selectById(...)` → 解析 `imagesJson` → `Base64.decode` → 直接 `zip.write(bin)`；写完即释放。
  - **每页处理完后释放大对象**：`taskMap.values().forEach(t -> t.setImagesJson(null))` 主动置空 LONGTEXT 字段。
  - **图片格式探测**：从 base64 头/魔数（`/9j/`→jpg、`iVBOR`→png、`UklGR`→webp、`R0lGOD`→gif）选后缀，未识别回退 `.jpg`。
  - **流式下载**：Controller 返回 `StreamingResponseBody`，`Content-Disposition: attachment; filename=preference_export_yyyyMMdd_HHmmss.zip`。
  - **Jackson**：`ExportServiceImpl` 内置 ObjectMapper 与 `JacksonConfig` 对齐（`SNAKE_CASE` + `JavaTimeModule`），不复用全局 mapper 避免被请求/响应序列化策略干扰。
  - **N+1 防护**：每页内 `taskMapper.selectBatchIds` / `voteMapper.selectList(in battleIds)` / `modelMapper.selectBatchIds` 批量预取；同一场对战取最早一条 vote（与 `BattleServiceImpl.loadBattleVote` 一致）。
- **过滤参数（Query）**：
  | 参数 | 说明 |
  | --- | --- |
  | `winner` | A/B/tie，缺省不过滤 |
  | `modelId` | 限定参与方（A 或 B 任一匹配即纳入），可传 DB 主键 ID 或 `models.model_id` 字符串；后者会自动 lookup 主键，找不到则强制空集 |
  | `startDate` / `endDate` | 按 `battles.created_at` 闭区间，`endDate` 内部下推到次日 00:00 不含；格式 `yyyy-MM-dd` |
  | `battleId` | 精确导出某条 |
  | `includeImages` | 默认 `true`；设 `false` 时 ZIP 内不打 `images/` 目录，仅 `data.jsonl` 内仍保留路径引用便于核对 |
  | `limit` | 最多导出条数；<=0 或缺省不限 |
- **影响面**：
  - **DB schema**：零变更；`essay_images` 表仍保持预留（实际图片仍以 base64 在 `tasks.images_json` 中）。
  - **缓存**：零变更。
  - **鉴权**：维持 admin 强校验（`AdminController.checkAdmin()`）。
  - **下游消费**：旧 5 字段 JSON/JSONL 不再可用；如果有外部 cron 在依赖 `/api/admin/export/preference`，需要切换到 `/api/admin/export/dataset.zip`。
- **文件清单**：
  - 新增：`dto/request/ExportQuery.java`、`service/ExportService.java`、`service/impl/ExportServiceImpl.java`。
  - 修改：`controller/AdminController.java`（删两端点、加一个 ZIP 端点、注入 `ExportService`）、`service/ModelService.java`（删两个方法）、`service/impl/ModelServiceImpl.java`（删实现 + 清未用 import）、`templates/admin.html`（导出 Tab 重做 + `downloadExportZip` / `resetExportFilters` 两个 JS 函数）。
- **快速验证**：
  ```bash
  # 1. 编译
  mvn -q compile -DskipTests   # 已通过
  # 2. 运行后获取管理员 JWT
  TOKEN=$(curl -s -X POST http://localhost:5001/api/login \
       -H 'Content-Type: application/json' \
       -d '{"username":"admin","password":"admin123"}' | jq -r .data.token)
  # 3. 全量导出（含图片）
  curl -fSL -H "Authorization: Bearer $TOKEN" \
       'http://localhost:5001/api/admin/export/dataset.zip' \
       -o preference_export.zip
  # 4. 仅导 A 胜 + 不打图片 + 限 100 条
  curl -fSL -H "Authorization: Bearer $TOKEN" \
       'http://localhost:5001/api/admin/export/dataset.zip?winner=A&includeImages=false&limit=100' \
       -o preference_export_top100.zip
  # 5. 查看
  unzip -l preference_export.zip
  ```

#### v2.17.1 (2026-05-11) — HikariCP 连接泄漏告警修复

- **现象**：调用 `/api/admin/export/dataset.zip` 后约 2 分钟，HikariCP 抛 `Apparent connection leak detected`，调用栈定位到 `ExportServiceImpl.writeJsonl` 内的 `selectBatchIds(...)`。
- **根因**：`exportZip` 走在 `StreamingResponseBody` 异步线程里，原本未加 `@Transactional`，每次 mapper 调用各自借/还连接；但整个导出过程持续秒级到分钟级，期间长时间持有多次 SqlSession，叠加 `application.yml` 中 `leak-detection-threshold=120000` 的 2 分钟阈值，触发误报告警（并非真正资源泄漏）。
- **修复**：
  1. **加只读事务**：`ExportServiceImpl.exportZip(...)` 增加 `@Transactional(readOnly = true, timeout = 1800)`，让一次导出只持有一段连续 SqlSession，结束后由事务统一释放。
  2. **放宽 leak 阈值**：`application.yml` 中 `spring.datasource.hikari.leak-detection-threshold` 由 `120000` 调整为 `1800000`（30 分钟，与 `max-lifetime` 同量级），避免对该长任务产生噪声告警；普通业务调用远小于该阈值，不影响其他场景。
- **验证**：`mvn -q -o compile -DskipTests` 通过；后续导出大批量 voted 数据无 HikariCP 告警。

### v2.16 (2026-05-11) — DeepSeek 单 Agent 评审链路（默认启用）

- **背景**：旧 LangGraph 多 Agent 流程（preprocess×2 + dimension_agent×6 + arbitrator）每场对战会触发约 9~10 次 LLM 调用，AiHubMix 网关多次因调用过密被风控/封禁（参见 v2.15.4 的全量 key 轮换事件）；同时维度 Agent 间缺乏全局视角易出现自相矛盾。
- **目标**：用 1 次 LLM 调用完成全部评审；调用 DeepSeek 新模型；与旧链路并存可切换。
- **改动**：
  - 新增 `agent-review-service/app/review/single_agent.py`：封装"DeepSeek 单 Agent + 固定 5 步 CoT + 严格 JSON 输出 → 解析为 `List[DimensionScore] + ArbitrationResult`"；模型 / base_url / api_key 全部从 settings 读取；缺失维度自动以 `tie` 兜底，winner 与分差不一致时按分差强制修正，final_winner 强约束等于 overall.winner。
  - `agent-review-service/app/review/prompts.py` 追加 `SINGLE_AGENT_SYSTEM` 与 `single_agent_user(...)`：写明 6 维度 key、0~5 评分准则、tie 阈值、固定 5 步 CoT（通读 A→通读 B→五维对比→overall→自检后输出 JSON）、输出 JSON schema（dimensions 顺序固定）。
  - `agent-review-service/app/review/service.py` 改造：`ReviewService.__init__` 根据 `settings.review_mode` 决定加载 LangGraph（multi 模式延迟导入）或仅注册 VoteMapper（single 模式）；`arun()` 内按 `_run_single` / `_run_multi` 分支；新增 `_build_report_from_parts` 复用维度合并与 final_winner 决议逻辑。
  - `agent-review-service/app/settings.py` 新增字段：`review_mode`（默认 `"single"`）、`ai_api_key_single`（DeepSeek key，留空待用户填）、`ai_base_url_single`（默认 `https://api.deepseek.com`）、`ai_review_model_single`（默认 `deepseek-v4-flash`）。原 AiHubMix 相关字段保留供 multi 模式 fallback。
  - `agent-review-service/.env` 同步新增 `REVIEW_MODE / AI_API_KEY_SINGLE / AI_BASE_URL_SINGLE / AI_REVIEW_MODEL_SINGLE` 4 项，DeepSeek key 留空；附 DeepSeek 控制台申请链接注释。
  - `agent-review-service/app/review/llm.py` 无需改动 —— 已经是 OpenAI 兼容 `AsyncOpenAI` + `response_format=json_object` + tenacity 重试，可直接连 DeepSeek 端点。
- **设计取舍**：
  - 不接 skills / 不接 RAG / 不传作文图片：最大化降低单次调用 token 与风控概率（用户明确选择"全部去掉"）。
  - 不做 pro 模型 fallback：保持单点最简；如需切 pro 直接改 `AI_REVIEW_MODEL_SINGLE=deepseek-v4-pro`。
  - 6 维度顺序与 `DimensionKey` 枚举严格一致；模型解析层做了字段容错（数值越界裁剪、winner 大小写归一、evidence 取前 3 条）。
- **影响面**：
  - **对外契约（`ReviewResponse` / `VotePayload` / `ReviewReport`）零变更**，Java 端无任何调整。
  - 旧 LangGraph 节点（`graph.py` / `nodes/*` / 旧 prompts）一行未动；通过 `REVIEW_MODE=multi` 即可完整切回 v2.15 行为。
  - DeepSeek API key 缺失时，仅 single 链路在调用瞬间抛 `ReviewServiceError`，不影响进程启动与 multi 模式。
- **使用方式**：
  ```bash
  # 在 agent-review-service/.env 中填入 DeepSeek API Key
  REVIEW_MODE=single                           # 默认；改为 multi 切回旧 LangGraph 流程
  AI_API_KEY_SINGLE=sk-xxxxxxxx                # DeepSeek 控制台申请
  AI_BASE_URL_SINGLE=https://api.deepseek.com  # OpenAI 兼容端点
  AI_REVIEW_MODEL_SINGLE=deepseek-v4-flash     # 或 deepseek-v4-pro
  ```
  之后正常 `python -m app.main` / `python -m batch.cli run -i ...` 即可，外部调用方无感切换。
- **预期收益**：每场对战 LLM 调用从 9~10 次降至 1 次（成本与封禁概率同步下降至原来的 ~10%）；端到端延迟取决于 DeepSeek flash 模型耗时（通常 <10s/场）。

### v2.15 (2026-05-04) — 泰安市高二期末作文批量评审数据集支持
- **背景**：需要批量跑通一份特殊来源数据（泰安市高二年级期末考试作文扫描件，共 11111 张"背面"图），作文题为"英雄与选择"。图片命名规范：`姓名-学号-正面.jpg` / `姓名-学号-背面.jpg`；本批次仅存在"背面"图且存在约 213 个重名/同学号覆盖、10 个未下完 `.downloading` 文件。原 `gen_dataset.py` 依赖 `resource/*.txt` 评分清单，不适用此场景。
- **改动**：
  - 新增 `agent-review-service/scripts/gen_dataset_taian.py`：
    - 直接扫描图片目录，正则 `^(.+)-(\d{6,})-(正面|背面)\.jpg$` 按学号聚合；
    - 自动跳过 `.downloading` 与命名不符文件；
    - 按学号去重，同学号重复名自动覆盖（最终保留字典序最后一个）；
    - 兼容"仅正面 / 仅背面 / 正背齐全"三种图片形态，全部照常生成 `images` 列表；
    - 固化作文题到 `ESSAY_TITLE` 常量（含完整材料 + 写作要求，中文引号 U+201C/U+201D，已规避 Python 字符串转义问题）；
    - 输出 6 字段 `DatasetItem`（与 `gen_dataset.py` v2.12 对齐）+ `metadata.student_name / student_id / source=taian-gaoer-qimo`。
  - 参数：`--pictures`（必填）、`--output`（必填）、`--grade`（默认"高中"）、`--limit`（默认 0 不限）。
- **输出数据**：`agent-review-service/data/dataset_taian_hero.jsonl`，共 **11559 条**（其中正背面齐全 0 / 仅正面 0 / 仅背面 11559）。
- **配套文档**：新增 `agent-review-service/泰安作文使用说明.md`（共 8 节）：
  1. 前置准备（环境变量、图片目录规范）
  2. 清单生成（全量 / 小样本 / 参数表 / 条目结构）
  3. 批量评审启动（一键脚本 / 分步手动）
  4. 进度监控 & 断点续跑（`status` / `--retry-failed`）
  5. 结果查看（jq 统计模板）
  6. 注意事项（费用、限流、Java Arena 依赖）
  7. 速查命令（复制即用：调试 20 条 / 全量 / 失败重跑）
  8. 关键路径一览
- **典型命令**：
  ```bash
  cd agent-review-service
  python3 scripts/gen_dataset_taian.py \
      --pictures picture/泰安市高二年级期末考试 \
      --output  data/dataset_taian_hero.jsonl
  # → ✅ 生成 11559 条
  python3 -m batch.cli run \
      -i data/dataset_taian_hero.jsonl -c 5 \
      --store data/batch_tasks_taian.sqlite \
      -o      data/results_taian.jsonl
  ```
- **影响面**：无 Java 代码改动；无 DB schema 改动；`agent-review-service` 仅新增脚本与说明文档，原 `gen_dataset.py` 流程完全不受影响。

### v2.14.1 (2026-04-25) — v2.14 缺陷修复
- **问题 ①：`BattleMapper.selectHistoryPage` 投票人串号**
  - 原实现：`MAX(v.user_id) / MAX(u.username) / MAX(u.display_name)` 配合 `GROUP BY b.id` 聚合，一场对战存在多条 votes 记录时（唯一约束是 `(battle_id, user_id)`，允许多人投同场），三个 MAX 可能分别来自不同行，导致历史页显示的 id/username/displayName 不属于同一用户。
  - 修复：移除 GROUP BY 与 MAX 聚合，改为 `LEFT JOIN votes v ON v.id = (SELECT MIN(v2.id) FROM votes v2 WHERE v2.battle_id = b.id)` 定位每场对战最早一条投票作为"主投票人"，再 `LEFT JOIN users u ON u.id = v.user_id`。三字段由此保证来自同一行，且语义与 `BattleServiceImpl.loadBattleVote()` 取 `orderByAsc(id) LIMIT 1` 对齐。
- **问题 ②：`BattleController.getBattle` 脱敏污染缓存**
  - 原实现：`desensitizeBattleVote(vo)` 直接 setter 修改 `BattleVO.vote` 的字段。`BattleServiceImpl.getBattleDetail()` 通过 `cacheService.getOrLoad(...)` 返回的 VO，在 Redis 命中时是新反序列化对象（安全），但如果未来改造为本地/进程内缓存将直接暴露真实投票人或永久脱敏。
  - 修复：`getBattle` 在调用 `desensitizeBattleVote` 前新增 `cloneVote(...)` 对 `BattleVoteVO` 做浅拷贝，脱敏只作用在副本上，彻底解耦"缓存持有对象"与"响应对象"。
- **影响面**：无 schema 变化、无接口字段变化；两处皆为后端内部实现加固。

### v2.14 (2026-04-25) — 投票人追溯与后台投票记录 Tab
- **背景**：`votes` 表已有 `user_id`，但前台/后台未回显"谁投的票"，导致评测复盘、异常排查、数据审计时无法追溯到具体投票人。
- **产品口径**：
  - 身份展示统一为 `displayName` 优先、回退 `username`（与侧边栏一致）。
  - 服务端脱敏：`admin` 看全部真实投票人；普通 `teacher` 仅 `voterUserId == currentUserId` 时显示真名，其他一律返回 `voter="匿名"` 且不带 `voter_user_id/voter_username/voter_display_name`。
- **后端改动**：
  - 新增 DTO：`BattleVoteVO`（对战详情-投票子对象，含 6 维度 + 理由 + voter）、`AdminVoteItemVO`（后台投票记录条目）、`AdminVoteQuery`（筛选条件）。
  - `BattleVO` 新增 `vote`（已投票对战挂接）；`BattleHistoryVO` 新增 `voter / voter_user_id / voter_username / voter_display_name`；`VoteResultVO` 新增 `voter / voter_user_id`。
  - `BattleMapper.selectHistoryPage` SQL 追加 `LEFT JOIN users u ON u.id = v.user_id`，SELECT 携带 `voterUserId/voterUsername/voterDisplayName`。
  - `VoteMapper.selectVotePage` 新增（动态 `<script>` SQL，JOIN `users/battles/tasks/models`，日期闭区间 `DATE_ADD(endDate, INTERVAL 1 DAY)`，按 `keyword` 模糊匹配 username/displayName）。
  - `BattleServiceImpl.buildBattleVO` 在 `status=voted` 时调用新方法 `loadBattleVote(battleId)` 组装 `BattleVoteVO`（服务层保存**原始**投票人字段，缓存亦存原始数据）；`vote()` 方法末尾给 `VoteResultVO` 注入 voter。
  - `BattleController` 在 `GET /api/battle/{id}` 与 `GET /api/battle/history` 返回前按当前 `UserContext.getRole()` 对 `vote.voter` / `record.voter` 做角色脱敏。
  - 新增 `VoteQueryService / VoteQueryServiceImpl` 与 `AdminVoteController`（`GET /api/admin/votes`，内置 `checkAdmin()` 双保险）。
- **前端改动**：
  - `history.html`：表格 thead 新增"投票人"列（`colspan` 8 → 9），单元格渲染 `b.voter`；详情弹窗 `battle-info-bar` 增加投票人 chip；"投票详情"区标题右侧新增「投票人：xxx」；修复既有 bug —— 原代码读 `detail.vote`（后端没返回）导致投票详情区永不显示、且维度值硬编码 `left/right`，现改为 `A/B/tie` 语义正确。
  - `admin.html`：Tab 栏新增"投票记录"按钮 + `#panel-votes` 面板（筛选：投票人关键字 / 对战 ID / 起止日期；表格：时间/对战/投票人/作文题目/模型 A/模型 B/获胜方/整体/耗时 + 分页按钮）；新增 JS `loadAdminVotes / resetVoteFilters`，`switchAdminTab` 首次切到 `votes` 懒加载。
- **影响面**：
  - 不改 DB schema，不改 `vote` 落库链路，不影响 ELO 计算。
  - `BattleVO` 结构新增字段，Jackson snake_case 自然命名 `vote`；老前端忽略该字段不受影响。
  - 缓存无需失效：`cacheService.invalidateBattle(battleId)` 在投票时已存在；脱敏不入缓存，不会引发跨角色串号。
- **文件清单**：
  - 新增：`controller/AdminVoteController.java`、`service/VoteQueryService.java`、`service/impl/VoteQueryServiceImpl.java`、`dto/response/BattleVoteVO.java`、`dto/response/AdminVoteItemVO.java`、`dto/request/AdminVoteQuery.java`。
  - 修改：`controller/BattleController.java`、`service/impl/BattleServiceImpl.java`、`mapper/BattleMapper.java`、`mapper/VoteMapper.java`、`dto/response/BattleVO.java`、`dto/response/BattleHistoryVO.java`、`dto/response/VoteResultVO.java`、`templates/history.html`、`templates/admin.html`。

### v2.12 (2026-04-25) — `gen_dataset.py` 输出精简到 6 个字段
- **背景**：数据集 JSONL 被下游批量评审脚本消费，下游并不使用 txt 里附带的人工评分与评语。保留 `metadata.human_scores / human_comment` 只会徒增体积并引入"看似可参考的标签"干扰。
- **改动**：
  - `_build_item()` 输出仅保留 6 个字段：`item_id` / `essay_title` / `images` / `essay_content` / `grade_level` / `requirements`。
  - `_parse_line()` 仍按格式 A/B 识别并定位评分起点（用于切出 `essay_title` 的右边界），但**解析出的评分数字与评语一律丢弃，不再传入 `_build_item`**。
  - 删除死代码常量 `_DIM_NAMES` 及 `_build_item` 里对应的参数。
  - 文件头 docstring 明确标注"评分/评语仅用于定位边界，不会写入输出 JSON"。
- **影响面**：`data/dataset_cn.jsonl` / `data/dataset_en.jsonl` / `data/dataset_all.jsonl` 重新生成。若此前有代码读取 `metadata.human_scores`，需改为离线对照原始 txt。
- **输出样例**：
  ```json
  {
    "item_id": "essay-0001",
    "essay_title": "读下面的材料，然后作文。一只蜗牛……不少于600字。②文中不得出现真实的人名、校名、地名。",
    "images": [{"kind": "local", "path": ".../chinese/0001.jpg"}],
    "essay_content": null,
    "grade_level": "初中",
    "requirements": null
  }
  ```

### v2.11 (2026-04-25) — `gen_dataset.py` 字段语义调整
- **背景**：原实现会调用 `_extract_title()` 把作文题目截成一个短 "title"（如 `《生命的意义》`），再把原文塞进 `requirements`。但真实数据里"图片名与第一个评分数字之间"的整段文字就是作文题目本身（含材料、提示、字数要求等），不应再拆。
- **改动**：
  - `agent-review-service/scripts/gen_dataset.py` 的 `_build_item()`：`essay_title` 直接使用解析出的完整原文；`requirements` 统一写为 `None`。
  - 删除死代码函数 `_extract_title()`（书名号/"以…为题"等启发式规则全部不再需要）。
  - 解析日志里的预览长度截到 40 字，避免整条题目刷屏。
- **影响面**：
  - `data/dataset_cn.jsonl` / `data/dataset_en.jsonl` / `data/dataset_all.jsonl` 重新生成，每条 `essay_title` 变长，`requirements` 一律为 `null`。
  - 下游批量评审 prompt 里原本拼接 `essay_title + requirements` 的逻辑不受影响（原来 requirements 本就常为 null）。
- **示例**：
  ```json
  {
    "item_id": "essay-0001",
    "essay_title": "读下面的材料，然后作文。一只蜗牛……要求：①除诗歌外，文体不限。不少于600字。②文中不得出现真实的人名、校名、地名。",
    "requirements": null,
    "metadata": { "human_scores": {"theme":8,"imagination":6,"logic":8,"language":8,"writing":3,"total":33}, ... }
  }
  ```

### v2.10 (2026-04-25) — `gen_dataset.py` 支持英文分号格式
- **背景**：`resource/picture/label_en.txt` 每行使用 `;` 作为字段分隔符（共 9 段），与中文 `label_cn.txt` 的空格格式不一致，直接跑 `gen_dataset.py` 会 50 条全部"未找到评分数字"。
- **改动**：
  - `agent-review-service/scripts/gen_dataset.py` 的 `_parse_line()` 增加分号格式分支，自动识别"`.jpg;` 开头且分号分段数 ≥9"的行；共用 `_build_item()` 组装 DatasetItem。
  - 文件顶部 docstring 同步补充两种格式示例。
- **影响面**：中文原格式无回归，英文 `label_en.txt` 50 条全部成功解析。
- **配套数据**：生成 `data/dataset_cn.jsonl`（50 条）、`data/dataset_en.jsonl`（50 条）、`data/dataset_all.jsonl`（100 条），所有图片就位到 `resource/picture/{chinese,english}/`。
- **典型用法**：
  ```bash
  python3 scripts/gen_dataset.py --txt resource/picture/label_en.txt \
      --pictures resource/picture/english --output data/dataset_en.jsonl --grade 初中
  ```

### v2.9 (2026-04-23) — 模型池扩展到 30 个
- **目标**：将可参与对战的 active 模型数量从 17 个扩展到 30 个，并保证所有 active 模型都能正确识别图片（多模态可用）。
- **下架模型（4 个，多模态表现不佳）**：
  - `gpt-5.4-pro`：带图片请求超时
  - `gpt-5.2-high`：带图片请求超时
  - `qwen3-235b-a22b`：返回"未接收到图片"
  - `mimo-v2-pro`：返回"未接收到图片"
- **新增成功（17 个，均通过 base64 图片验证）**：
  - OpenAI 系列：`gpt-4o`, `gpt-4o-2024-11-20`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-5`, `gpt-5-mini`, `gpt-5.1`, `gpt-5.2`, `gpt-5.4-mini`
  - Anthropic：`claude-sonnet-4-5`, `claude-opus-4-1`
  - Google：`gemini-2.5-flash`, `gemini-2.5-flash-lite`, `gemini-3-flash-preview`
  - xAI：`grok-4-fast-reasoning`
  - 其他：1 个
- **添加失败/拒绝（2 个）**：
  - `claude-3-5-sonnet-20240620`：AiHubMix 返回 HTTP 404（已下线）
  - `gemini-2.0-flash`：HTTP 429 限流，不稳定
- **平台调用要点**（踩坑记录）：
  - `POST /api/admin/models` 请求体字段**必须为 snake_case**（`model_id` / `input_modalities` / `context_length` / `max_output`），因为项目 Jackson 配置了全局 `PropertyNamingStrategies.SNAKE_CASE`；返回体同理。
  - 平台未提供 `DELETE /api/admin/models/{id}`；只能 `PUT /toggle` 将模型置为 inactive，如需彻底删除需直连 MySQL。
- **影响面**：
  - `models` 表：总记录 24→41，active 17→30
  - 无 Java 代码改动，仅数据变更
  - 工具脚本：新增 `scripts/model_manage.py`, `scripts/verify_and_fix.py`
  - **`scripts/model_manage.py` 子命令**：
    - 默认运行：下架问题模型 + 用 `CANDIDATE_MODELS` 填充到目标 active 数
    - `add-list`：使用脚本内 `EXTRA_MODEL_IDS` 列表，"先做图片多模态测试 → 通过才调用平台 `/api/admin/models` 添加 → 失败不动数据库"，最后输出汇总（候选数 / 已存在跳过 / 测试通过添加成功 / 测试通过添加失败 / 测试失败 / 当前 active 总数）
    - `add-list <id1> <id2> ...`：直接命令行传 model_id，覆盖 EXTRA_MODEL_IDS

### v2.8 (2026-04-23) — 升级评审/仲裁 Agent LLM
- 评审 Agent：gpt-4o-mini → gpt-5-mini
- 仲裁 Agent：gpt-4o → gpt-5

