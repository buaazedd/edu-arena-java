# 📚 edu-arena-java 项目 Wiki

> **最后更新**: 2026-04-25 (v2.14.1: 修复 v2.14 两处隐性缺陷 —— ① `BattleMapper.selectHistoryPage` 原用 `MAX(v.user_id)+MAX(u.username)+MAX(u.display_name)` 聚合，一场对战有多条投票时三字段可能来自不同行造成"身份串号"，改为子查询 `MIN(v2.id)` 定位主投票行后 LEFT JOIN；② `BattleController.getBattle` 脱敏前对 `BattleVoteVO` 做浅拷贝，避免修改缓存命中持有的 VO 对象跨角色/跨请求污染)  
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
│   │   ├── review/                                  # 多智能体核心
│   │   │   ├── graph.py                             # LangGraph StateGraph 装配
│   │   │   ├── state.py                             # GraphState TypedDict (Annotated[List,add] 并行合并)
│   │   │   ├── llm.py                               # AsyncOpenAI 封装(JSON mode + 多模态)
│   │   │   ├── prompts.py                           # preprocess/dim/arbitrator prompt
│   │   │   ├── decision.py                          # VoteMapper (A/B → left/right)
│   │   │   ├── service.py                           # ReviewService 外观类
│   │   │   └── nodes/                               # preprocess/dispatch/dimension_agent/arbitrator
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
│   ├── scripts/                                     # init_rag.py / gen_dataset.py / run_batch.sh
│   ├── resource/                                    # 作文描述 txt（人工评分+评语）
│   ├── picture/                                     # 作文原图（0001.jpg, 0002.jpg...）
│   ├── tests/                                       # pytest 146 个测试
│   └── data/                                        # sample_dataset.jsonl 样例 + images/
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
    │   │   │   ├── request/                         # 7 个请求 DTO
    │   │   │   │   ├── LoginRequest.java
    │   │   │   │   ├── RegisterRequest.java
    │   │   │   │   ├── CreateBattleRequest.java
    │   │   │   │   ├── VoteRequest.java
    │   │   │   │   ├── AddModelRequest.java
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
| GET | `/api/admin/export/preference.json` | 导出偏好数据(JSON) | ✅ (admin) |
| GET | `/api/admin/export/preference.jsonl` | 导出偏好数据(JSONL) | ✅ (admin) |
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

jwt.secret: ...                      # JWT 密钥(≥256bit)
jwt.expiration: 86400000             # JWT 有效期(24h)

ai.api-key: sk-...                   # AI API Key(AiHubMix)
ai.base-url: https://api.aihubmix.com/v1/chat/completions  # AI API 地址

edu-arena.auth-bypass-enabled: false # 认证旁路开关
```

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
| 修改评审 Agent / LLM 行为 | `agent-review-service/app/review/`（`prompts.py` / `nodes/` / `graph.py`） |
| 修改离线批量流程 | `agent-review-service/batch/`（`orchestrator.py` / `arena_client.py` / `cli.py`） |
| 修改匿名化行为 | `BattleServiceImpl.buildBattleVO()` + `battle.html` + `history.html` |
| 修改投票人追溯/脱敏逻辑 | `BattleController.desensitize*()` + `BattleServiceImpl.loadBattleVote()/vote()` + `BattleMapper.selectHistoryPage` + `VoteMapper.selectVotePage` + `BattleVoteVO`/`AdminVoteItemVO` |
| 修改 ELO 算法 | `EloCalculator.java` + `BattleServiceImpl.vote()` |
| 修改模型匹配策略 | `EloMatchServiceImpl.java` |
| 修改 AI Prompt/调用逻辑 | `AiClient.java`（`buildPrompt()` 和 `buildMessageContent()`） |
| 修改认证逻辑 | `AuthInterceptor.java` + `JwtUtils.java` + `WebConfig.java` |
| 修改前端页面 | `templates/*.html`（注意 base.html 是公共布局） |
| 修改缓存策略 | `CacheService.java` |
| 新增模型字段 | `Model.java` + `models` 表 + `AddModelRequest.java` + `LeaderboardVO.java` + `admin.html` |

---

## 十五、版本变更记录

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

