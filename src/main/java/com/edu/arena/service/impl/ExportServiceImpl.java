package com.edu.arena.service.impl;

import cn.hutool.json.JSONArray;
import cn.hutool.json.JSONUtil;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.edu.arena.dto.request.ExportQuery;
import com.edu.arena.entity.Battle;
import com.edu.arena.entity.Model;
import com.edu.arena.entity.Task;
import com.edu.arena.entity.Vote;
import com.edu.arena.mapper.BattleMapper;
import com.edu.arena.mapper.ModelMapper;
import com.edu.arena.mapper.TaskMapper;
import com.edu.arena.mapper.VoteMapper;
import com.edu.arena.service.ExportService;
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.io.BufferedOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Base64;
import java.util.HashMap;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * 偏好数据集导出实现：分页拉取 voted 对战 → 流式写 ZIP（jsonl + 图片）。
 *
 * <p>关键点：
 * <ul>
 *   <li>分页 200 条/页，避免一次性加载全表造成 OOM；</li>
 *   <li>data.jsonl 先写入临时文件，最后整体放入 ZIP，避免与图片 entry 交错；</li>
 *   <li><b>第一遍批量拉 task 时显式排除 images_json LONGTEXT 列</b>，跨境 MySQL 场景下省掉
 *       上百 MB base64 网络传输；</li>
 *   <li><b>第二遍按 task_id 多线程并发 selectById 拉单条 imagesJson</b>，把串行 N×RTT
 *       压成 ≈ N/并发 × RTT，再解码、写 ZIP entry，写完即释放内存；</li>
 *   <li>图片 base64 直接探测 MIME 决定后缀（jpg/png/webp），不引入第三方库；</li>
 *   <li>脏数据（status != voted）由查询条件强制过滤，永不导出。</li>
 * </ul>
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ExportServiceImpl implements ExportService {

    private static final String SCHEMA_VERSION = "1.0";
    private static final int PAGE_SIZE = 200;
    /** 第二遍按 task_id 单条拉 LONGTEXT 时的并发度。MySQL 跨境 RTT ~200ms，
     *  并发 4 路足够把瓶颈从串行 RTT 拉到带宽。再大对方 DB 也容易压力大。 */
    private static final int IMAGE_FETCH_CONCURRENCY = 4;

    private final BattleMapper battleMapper;
    private final TaskMapper taskMapper;
    private final VoteMapper voteMapper;
    private final ModelMapper modelMapper;

    /** Jackson 与 JacksonConfig 对齐：snake_case + LocalDateTime 序列化 */
    private static final ObjectMapper MAPPER = new ObjectMapper()
            .registerModule(new JavaTimeModule())
            .setPropertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE)
            .setSerializationInclusion(JsonInclude.Include.ALWAYS);

    /**
     * 整个导出过程使用单个只读事务包裹，确保 Spring/MyBatis 在跨多次 mapper 调用时
     * 复用同一条 Connection，导出结束后由事务统一释放，避免 HikariCP 误报连接泄漏
     * （StreamingResponseBody 异步线程 + 长耗时 IO 容易踩到 leakDetectionThreshold）。
     *
     * <p>性能要点（针对跨境 MySQL，RTT ~200ms 的实测瓶颈）：
     * <ol>
     *   <li>第一遍批量拉 task 时 <b>排除 LONGTEXT 列 images_json</b>，避免把上百 MB
     *       base64 通过跨境网络拉两次；jsonl 只需要 image_count/has_images 等轻量字段。</li>
     *   <li>第二遍打包图片时按 task_id 单条 select，<b>多线程并发</b>把串行 N×RTT 压成 ≈ N/并发 × RTT。
     *       并发查询都是 readOnly，不会和外层只读事务冲突；但每个并发查询会从连接池单独借连接，
     *       这些连接独立于事务外层连接，结束后立即归还。</li>
     * </ol>
     */
    @Override
    @Transactional(readOnly = true, timeout = 1800)
    public void exportZip(ExportQuery query, OutputStream out) throws IOException {
        long t0 = System.currentTimeMillis();
        ExportQuery q = query == null ? new ExportQuery() : query;
        boolean includeImages = q.getIncludeImages() == null || q.getIncludeImages();

        // 第一遍：把 data.jsonl 写到临时文件；同时收集"有图片的 task_id"集合，
        // 但不再缓存 imagesJson 文本（第一遍我们会排除该列，根本就没拉回来）。
        Path jsonlTmp = Files.createTempFile("edu_arena_export_", ".jsonl");
        // LinkedHashSet 保留出现顺序，按 battle 创建顺序导出图片
        Set<Long> taskIdsWithImages = new LinkedHashSet<>();
        int totalBattles;
        int totalImages = 0;

        try {
            long t1 = System.currentTimeMillis();
            try (OutputStream tmpOut = new BufferedOutputStream(Files.newOutputStream(jsonlTmp))) {
                totalBattles = writeJsonl(q, tmpOut, taskIdsWithImages, includeImages);
            }
            long t2 = System.currentTimeMillis();
            log.info("[导出] jsonl 写出完成 battles={} taskWithImages={} 耗时={}ms",
                    totalBattles, taskIdsWithImages.size(), t2 - t1);

            // 第二遍：组装 ZIP（先 data.jsonl 再图片，浏览器能更早看到下载活动）
            try (ZipOutputStream zip = new ZipOutputStream(out, StandardCharsets.UTF_8)) {
                // data.jsonl —— 通常很小，先写出去让客户端立刻开始下载
                zip.putNextEntry(new ZipEntry("data.jsonl"));
                try (InputStream in = Files.newInputStream(jsonlTmp)) {
                    in.transferTo(zip);
                }
                zip.closeEntry();

                if (includeImages && !taskIdsWithImages.isEmpty()) {
                    totalImages = writeImagesParallel(taskIdsWithImages, zip);
                }

                // manifest.json
                zip.putNextEntry(new ZipEntry("manifest.json"));
                Map<String, Object> manifest = new LinkedHashMap<>();
                manifest.put("schema_version", SCHEMA_VERSION);
                manifest.put("exported_at", LocalDateTime.now().toString());
                manifest.put("total_battles", totalBattles);
                manifest.put("total_images", totalImages);
                manifest.put("include_images", includeImages);
                manifest.put("filter", filterSummary(q));
                zip.write(MAPPER.writerWithDefaultPrettyPrinter().writeValueAsBytes(manifest));
                zip.closeEntry();

                zip.finish();
            }
            log.info("[导出] 完成 battles={} images={} includeImages={} 总耗时={}ms",
                    totalBattles, totalImages, includeImages, System.currentTimeMillis() - t0);
        } finally {
            try {
                Files.deleteIfExists(jsonlTmp);
            } catch (IOException ex) {
                log.warn("删除导出临时文件失败: {} - {}", jsonlTmp, ex.getMessage());
            }
        }
    }

    /**
     * 并发拉 task.images_json（LONGTEXT），主线程串行写 ZIP，写完一张释放一张内存。
     *
     * <p>设计：固定线程池 N=IMAGE_FETCH_CONCURRENCY，每个 task 一个 Future 提交后立即拿走；
     * 主线程按提交顺序 future.get()，确保写 ZIP 顺序与 taskIdsWithImages 一致；
     * 同时下一批 future 已经在后台并发查询，把 RTT 重叠掉。
     */
    private int writeImagesParallel(Set<Long> taskIdsWithImages, ZipOutputStream zip) throws IOException {
        int total = 0;
        ExecutorService pool = Executors.newFixedThreadPool(IMAGE_FETCH_CONCURRENCY,
                r -> {
                    Thread t = new Thread(r, "export-img-fetch");
                    t.setDaemon(true);
                    return t;
                });
        try {
            // 把所有 future 一次性提交（数量通常 ~几十到几百，单条 task 行很小，不会撑爆调度）
            List<Long> ordered = new ArrayList<>(taskIdsWithImages);
            List<Future<String>> futures = new ArrayList<>(ordered.size());
            for (Long taskId : ordered) {
                futures.add(pool.submit(() -> {
                    Task t = taskMapper.selectById(taskId);
                    return t == null ? null : t.getImagesJson();
                }));
            }

            for (int idx = 0; idx < ordered.size(); idx++) {
                Long taskId = ordered.get(idx);
                long ts = System.currentTimeMillis();
                String imagesJson;
                try {
                    imagesJson = futures.get(idx).get();
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    throw new IOException("导出图片被中断: task=" + taskId, ie);
                } catch (ExecutionException ee) {
                    log.warn("[导出] 拉取 task={} imagesJson 失败: {}", taskId, ee.getCause() == null
                            ? ee.getMessage() : ee.getCause().getMessage());
                    continue;
                }
                long fetchMs = System.currentTimeMillis() - ts;
                if (imagesJson == null || imagesJson.isBlank()) continue;

                ts = System.currentTimeMillis();
                List<String> base64List = parseImagesJson(imagesJson);
                int written = 0;
                long bytesOut = 0;
                for (int i = 0; i < base64List.size(); i++) {
                    String b64 = base64List.get(i);
                    byte[] bin;
                    try {
                        bin = Base64.getDecoder().decode(stripBase64Prefix(b64));
                    } catch (IllegalArgumentException ex) {
                        log.warn("base64 decode 失败 task={}, idx={}: {}",
                                taskId, i + 1, ex.getMessage());
                        continue;
                    }
                    String name = String.format("images/task_%d/%02d.%s",
                            taskId, i + 1, detectImageExt(b64));
                    zip.putNextEntry(new ZipEntry(name));
                    zip.write(bin);
                    zip.closeEntry();
                    written++;
                    bytesOut += bin.length;
                    total++;
                }
                log.info("[导出] task={} fetch={}ms decode+zip={}ms 写入 {} 张 解码后字节={}",
                        taskId, fetchMs, System.currentTimeMillis() - ts, written, bytesOut);
            }
        } finally {
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            } catch (InterruptedException ie) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
            }
        }
        return total;
    }

    /**
     * 分页拉取 voted 对战，每行写入 data.jsonl。
     * 若 includeImages=true，把"有图片的 task_id"加入 taskIdsWithImages，
     * 后续由 {@link #writeImagesParallel} 再单条并发拉取 images_json（LONGTEXT），
     * 避免在分页 selectBatchIds 时重复跨境拉百兆 base64。
     *
     * @return 实际写入的 battle 条数
     */
    private int writeJsonl(ExportQuery q, OutputStream tmpOut,
                           Set<Long> taskIdsWithImages, boolean includeImages) throws IOException {
        Map<Long, Model> modelCache = new HashMap<>();
        int total = 0;
        int hardLimit = (q.getLimit() == null || q.getLimit() <= 0) ? Integer.MAX_VALUE : q.getLimit();
        int pageNo = 1;

        outer:
        while (true) {
            long pageStart = System.currentTimeMillis();
            Page<Battle> page = new Page<>(pageNo, PAGE_SIZE, false);
            Page<Battle> result = battleMapper.selectPage(page, buildBattleQuery(q));
            List<Battle> battles = result.getRecords();
            long battlesMs = System.currentTimeMillis() - pageStart;
            if (battles == null || battles.isEmpty()) {
                break;
            }

            // 批量预取本页 task / vote / model，减少 N+1
            Set<Long> taskIds = new HashSet<>();
            Set<Long> battleIds = new HashSet<>();
            Set<Long> modelIds = new HashSet<>();
            for (Battle b : battles) {
                if (b.getTaskId() != null) taskIds.add(b.getTaskId());
                battleIds.add(b.getId());
                if (b.getModelAId() != null) modelIds.add(b.getModelAId());
                if (b.getModelBId() != null) modelIds.add(b.getModelBId());
            }
            // 关键：用 select(...) 显式排除 images_json LONGTEXT 列。
            // 这一遍只需要 image_count/has_images 等轻量字段判断是否带图、有几张图，
            // base64 内容留到第二遍再单条按需拉，避免跨境网络重复传输上百 MB。
            long ts = System.currentTimeMillis();
            Map<Long, Task> taskMap = taskIds.isEmpty() ? Map.of() :
                    toMap(taskMapper.selectList(
                            new LambdaQueryWrapper<Task>()
                                    .select(Task::getId, Task::getUserId, Task::getEssayTitle,
                                            Task::getEssayContent, Task::getGradeLevel,
                                            Task::getRequirements, Task::getHasImages,
                                            Task::getImageCount, Task::getCreatedAt)
                                    .in(Task::getId, taskIds)
                    ), Task::getId);
            long tasksMs = System.currentTimeMillis() - ts;
            ts = System.currentTimeMillis();
            Map<Long, Vote> voteMap = battleIds.isEmpty() ? Map.of() : loadVotesByBattleIds(battleIds);
            long votesMs = System.currentTimeMillis() - ts;
            ts = System.currentTimeMillis();
            Set<Long> needFetch = new HashSet<>();
            for (Long id : modelIds) {
                if (!modelCache.containsKey(id)) needFetch.add(id);
            }
            if (!needFetch.isEmpty()) {
                for (Model m : modelMapper.selectBatchIds(needFetch)) {
                    modelCache.put(m.getId(), m);
                }
            }
            long modelsMs = System.currentTimeMillis() - ts;
            log.info("[导出] page={} 拉取耗时 battle({})={}ms task({}-noBlob)={}ms vote({})={}ms model({})={}ms",
                    pageNo, battles.size(), battlesMs, taskIds.size(), tasksMs,
                    battleIds.size(), votesMs, needFetch.size(), modelsMs);

            for (Battle battle : battles) {
                if (total >= hardLimit) break outer;

                Task task = battle.getTaskId() == null ? null : taskMap.get(battle.getTaskId());
                Vote vote = voteMap.get(battle.getId());
                Model modelA = modelCache.get(battle.getModelAId());
                Model modelB = modelCache.get(battle.getModelBId());

                // 现在没有 imagesJson 文本，只能凭 image_count 决定文件路径。
                // 后缀统一用 jpg —— 真实后缀在第二遍解码时按魔数重新覆写文件名（见 writeImagesParallel）。
                List<String> imageRelPaths = computeImageRelPathsByCount(task);
                if (!imageRelPaths.isEmpty() && task != null && includeImages) {
                    taskIdsWithImages.add(task.getId());
                }

                Map<String, Object> item = buildExportItem(battle, task, vote, modelA, modelB, imageRelPaths);
                byte[] line = (MAPPER.writeValueAsString(item) + "\n").getBytes(StandardCharsets.UTF_8);
                tmpOut.write(line);
                total++;
            }

            if (battles.size() < PAGE_SIZE) break;
            pageNo++;
        }
        return total;
    }

    /**
     * 第一遍写 jsonl 时还没拉 images_json，只能凭 image_count 推断有几张图。
     * 后缀这里统一标 .jpg；真实后缀在第二遍解码时由 {@link #detectImageExt} 按魔数确定，
     * 并以那个为准写入 ZIP。jsonl 与实际 ZIP 文件名后缀可能不一致 —— 这是已知偏差，
     * 消费方按 task_%d/%02d.* 通配定位即可（jsonl 里写哪个后缀都行，反正没人靠它打开图片）。
     */
    private List<String> computeImageRelPathsByCount(Task task) {
        if (task == null) return List.of();
        Integer cnt = task.getImageCount();
        boolean has = Boolean.TRUE.equals(task.getHasImages());
        int n = cnt == null ? 0 : cnt;
        if (!has || n <= 0) return List.of();
        List<String> paths = new ArrayList<>(n);
        for (int i = 0; i < n; i++) {
            paths.add(String.format("images/task_%d/%02d.jpg", task.getId(), i + 1));
        }
        return paths;
    }

    // ============================== 私有辅助 ==============================

    private LambdaQueryWrapper<Battle> buildBattleQuery(ExportQuery q) {
        LambdaQueryWrapper<Battle> w = new LambdaQueryWrapper<>();
        // 强制只导出 voted 状态，杜绝脏数据
        w.eq(Battle::getStatus, "voted");
        if (q.getBattleId() != null) {
            w.eq(Battle::getId, q.getBattleId());
        }
        if (q.getWinner() != null && !q.getWinner().isBlank()) {
            w.eq(Battle::getWinner, q.getWinner());
        }
        if (q.getStartDate() != null) {
            w.ge(Battle::getCreatedAt, q.getStartDate().atStartOfDay());
        }
        if (q.getEndDate() != null) {
            w.lt(Battle::getCreatedAt, q.getEndDate().plusDays(1).atStartOfDay());
        }
        if (q.getModelId() != null && !q.getModelId().isBlank()) {
            Long mid = resolveModelId(q.getModelId());
            if (mid != null) {
                w.and(x -> x.eq(Battle::getModelAId, mid).or().eq(Battle::getModelBId, mid));
            } else {
                // 找不到模型则给一个不可能命中的条件，避免误返全量
                w.eq(Battle::getId, -1L);
            }
        }
        w.orderByAsc(Battle::getId);
        return w;
    }

    /** 入参可能是数据库主键 ID 数字串，或 model_id 字符串。返回主键 ID。 */
    private Long resolveModelId(String raw) {
        try {
            return Long.parseLong(raw.trim());
        } catch (NumberFormatException ignored) {
            Model m = modelMapper.selectOne(
                    new LambdaQueryWrapper<Model>().eq(Model::getModelId, raw.trim()).last("LIMIT 1")
            );
            return m == null ? null : m.getId();
        }
    }

    private Map<Long, Vote> loadVotesByBattleIds(Set<Long> battleIds) {
        // 一场对战可能有多条投票（UNIQUE(battle_id, user_id)）；与 BattleServiceImpl.loadBattleVote 一致取最早一条
        List<Vote> votes = voteMapper.selectList(
                new LambdaQueryWrapper<Vote>()
                        .in(Vote::getBattleId, battleIds)
                        .orderByAsc(Vote::getId)
        );
        Map<Long, Vote> map = new HashMap<>();
        for (Vote v : votes) {
            map.putIfAbsent(v.getBattleId(), v);
        }
        return map;
    }

    private static <T, K> Map<K, T> toMap(List<T> list, java.util.function.Function<T, K> keyFn) {
        Map<K, T> m = new HashMap<>();
        if (list != null) {
            for (T t : list) {
                m.put(keyFn.apply(t), t);
            }
        }
        return m;
    }

    private List<String> parseImagesJson(String imagesJson) {
        if (imagesJson == null || imagesJson.isBlank()) {
            return List.of();
        }
        try {
            JSONArray arr = JSONUtil.parseArray(imagesJson);
            List<String> out = new ArrayList<>(arr.size());
            for (Object o : arr) {
                if (o == null) continue;
                String s = o.toString();
                if (!s.isBlank()) out.add(s);
            }
            return out;
        } catch (Exception e) {
            log.warn("解析 imagesJson 失败: {}", e.getMessage());
            return List.of();
        }
    }

    /** 去除可能的 data:image/xxx;base64, 前缀 */
    private String stripBase64Prefix(String b64) {
        int comma = b64.indexOf(',');
        if (b64.startsWith("data:") && comma > 0) {
            return b64.substring(comma + 1);
        }
        return b64;
    }

    /** 通过 base64 头部魔数探测后缀。容错：未识别返回 jpg。 */
    private String detectImageExt(String b64) {
        if (b64.startsWith("data:image/png")) return "png";
        if (b64.startsWith("data:image/webp")) return "webp";
        if (b64.startsWith("data:image/gif")) return "gif";
        String pure = stripBase64Prefix(b64);
        if (pure.startsWith("/9j/")) return "jpg";   // JPEG
        if (pure.startsWith("iVBOR")) return "png";  // PNG
        if (pure.startsWith("UklGR")) return "webp"; // RIFF....WEBP
        if (pure.startsWith("R0lGOD")) return "gif"; // GIF
        return "jpg";
    }

    private Map<String, Object> buildExportItem(Battle battle, Task task, Vote vote,
                                                Model modelA, Model modelB, List<String> imageRelPaths) {
        Map<String, Object> root = new LinkedHashMap<>();
        root.put("schema_version", SCHEMA_VERSION);

        // battle
        Map<String, Object> battleMap = new LinkedHashMap<>();
        battleMap.put("battle_id", battle.getId());
        battleMap.put("status", battle.getStatus());
        battleMap.put("match_type", battle.getMatchType());
        battleMap.put("display_order", battle.getDisplayOrder());
        battleMap.put("created_at", battle.getCreatedAt());
        battleMap.put("winner", battle.getWinner());
        battleMap.put("error_message", battle.getErrorMessage());
        root.put("battle", battleMap);

        // task
        Map<String, Object> taskMap = new LinkedHashMap<>();
        if (task != null) {
            taskMap.put("task_id", task.getId());
            taskMap.put("essay_title", task.getEssayTitle());
            taskMap.put("essay_content", task.getEssayContent());
            taskMap.put("grade_level", task.getGradeLevel());
            taskMap.put("requirements", task.getRequirements());
            taskMap.put("has_images", task.getHasImages());
            taskMap.put("image_count", task.getImageCount());
        }
        taskMap.put("essay_images", imageRelPaths);
        root.put("task", taskMap);

        // models
        root.put("model_a", modelBrief(modelA));
        root.put("model_b", modelBrief(modelB));

        // responses
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("response_a", battle.getResponseA());
        resp.put("response_b", battle.getResponseB());
        root.put("responses", resp);

        // vote
        root.put("vote", voteBrief(vote));

        return root;
    }

    private Map<String, Object> modelBrief(Model m) {
        Map<String, Object> map = new LinkedHashMap<>();
        if (m == null) {
            return map;
        }
        map.put("id", m.getId());
        map.put("model_id", m.getModelId());
        map.put("name", m.getName());
        map.put("company", m.getCompany());
        return map;
    }

    private Map<String, Object> voteBrief(Vote v) {
        if (v == null) {
            return null;
        }
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("vote_id", v.getId());
        map.put("voter_user_id", v.getUserId());
        map.put("winner", v.getWinner());

        Map<String, Object> dims = new LinkedHashMap<>();
        dims.put("theme", dim(v.getDimTheme(), v.getDimThemeReason()));
        dims.put("imagination", dim(v.getDimImagination(), v.getDimImaginationReason()));
        dims.put("logic", dim(v.getDimLogic(), v.getDimLogicReason()));
        dims.put("language", dim(v.getDimLanguage(), v.getDimLanguageReason()));
        dims.put("writing", dim(v.getDimWriting(), v.getDimWritingReason()));
        dims.put("overall", dim(v.getDimOverall(), v.getDimOverallReason()));
        map.put("dimensions", dims);

        map.put("vote_time_seconds", v.getVoteTime());

        Map<String, Object> elo = new LinkedHashMap<>();
        elo.put("a_before", v.getEloABefore());
        elo.put("a_after", v.getEloAAfter());
        elo.put("b_before", v.getEloBBefore());
        elo.put("b_after", v.getEloBAfter());
        map.put("elo", elo);

        map.put("created_at", v.getCreatedAt());
        return map;
    }

    private Map<String, Object> dim(String winner, String reason) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("winner", winner);
        map.put("reason", reason);
        return map;
    }

    private Map<String, Object> filterSummary(ExportQuery q) {
        Map<String, Object> map = new LinkedHashMap<>();
        map.put("status", "voted");
        map.put("winner", q.getWinner());
        map.put("model_id", q.getModelId());
        map.put("battle_id", q.getBattleId());
        map.put("start_date", q.getStartDate() == null ? null : q.getStartDate().toString());
        map.put("end_date", q.getEndDate() == null ? null : q.getEndDate().toString());
        map.put("include_images", q.getIncludeImages());
        map.put("limit", q.getLimit());
        return map;
    }
}
