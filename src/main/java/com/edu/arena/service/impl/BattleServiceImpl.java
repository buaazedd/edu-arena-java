package com.edu.arena.service.impl;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.edu.arena.aiclient.AiClient;
import com.edu.arena.common.cache.CacheService;
import com.edu.arena.common.exception.BusinessException;
import com.edu.arena.common.utils.EloCalculator;
import com.edu.arena.common.utils.ImageCompressUtils;
import com.edu.arena.dto.request.CreateBattleRequest;
import com.edu.arena.dto.request.VoteRequest;
import com.edu.arena.dto.response.BattleHistoryVO;
import com.edu.arena.dto.response.BattleVO;
import com.edu.arena.dto.response.MatchResultVO;
import com.edu.arena.dto.response.ModelSimpleVO;
import com.edu.arena.dto.response.VoteResultVO;
import com.edu.arena.entity.Battle;
import com.edu.arena.entity.EloHistory;
import com.edu.arena.entity.Model;
import com.edu.arena.entity.Task;
import com.edu.arena.entity.Vote;
import com.edu.arena.mapper.BattleMapper;
import com.edu.arena.mapper.EloHistoryMapper;
import com.edu.arena.mapper.ModelMapper;
import com.edu.arena.mapper.TaskMapper;
import com.edu.arena.mapper.VoteMapper;
import com.edu.arena.service.BattleService;
import com.edu.arena.service.EloMatchService;
import com.edu.arena.service.LeaderboardService;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 对战服务实现
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class BattleServiceImpl implements BattleService {

    private final TaskMapper taskMapper;
    private final BattleMapper battleMapper;
    private final ModelMapper modelMapper;
    private final VoteMapper voteMapper;
    private final EloHistoryMapper eloHistoryMapper;
    private final AiClient aiClient;
    private final LeaderboardService leaderboardService;
    private final CacheService cacheService;
    private final EloMatchService eloMatchService;
    
    /** 每日对战限流：每用户每天最多50次 */
    private static final int DAILY_BATTLE_LIMIT = 50;
    private static final int MAX_SLOT_RETRY = 2;
    private static final int FALLBACK_MODEL_COUNT = 4;
    
    /**
     * 有界线程池 - 用于并行调用模型
     * 核心线程数: 4 (支持同时处理多对战)
     * 最大线程数: 20
     * 队列容量: 100
     */
    private final ExecutorService executor = new ThreadPoolExecutor(
            4,                                      // 核心线程数
            20,                                     // 最大线程数
            60L,                                    // 空闲线程存活时间
            TimeUnit.SECONDS,
            new ArrayBlockingQueue<>(100),          // 有界队列
            new ThreadPoolExecutor.CallerRunsPolicy()  // 拒绝策略: 调用者执行
    );

    /**
     * 应用关闭时优雅关闭线程池
     */
    @PreDestroy
    public void shutdown() {
        log.info("关闭BattleService线程池...");
        executor.shutdown();
        try {
            if (!executor.awaitTermination(60, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(60, TimeUnit.SECONDS)) {
                    log.error("线程池未能完全关闭");
                }
            }
        } catch (InterruptedException e) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
        }
        log.info("BattleService线程池已关闭");
    }

    @Override
    @Transactional
    public Long createBattle(Long userId, CreateBattleRequest request) {
        // 用户每日对战限流检查
        int battleCount = cacheService.checkAndIncrementUserBattleLimit(userId, DAILY_BATTLE_LIMIT);
        if (battleCount > DAILY_BATTLE_LIMIT) {
            throw new BusinessException("您今日的对战次数已达上限(" + DAILY_BATTLE_LIMIT + "次)，请明天再试");
        }
        
        // 验证内容
        if ((request.getEssayContent() == null || request.getEssayContent().isEmpty()) 
                && (request.getImages() == null || request.getImages().isEmpty())) {
            throw new BusinessException("请提供作文内容或上传图片");
        }

        if (request.getEssayContent() != null && request.getEssayContent().trim().length() < 10) {
            if (request.getImages() == null || request.getImages().isEmpty()) {
                throw new BusinessException("内容至少10字");
            }
            log.info("纯图片作文模式: essayContent长度不足10，自动置空，依赖图片输入");
            request.setEssayContent(null);
        }

        // 验证图片并压缩
        if (request.getImages() != null && !request.getImages().isEmpty()) {
            if (request.getImages().size() > 10) {
                throw new BusinessException("最多上传10张图片");
            }

            List<String> compressedImages = new ArrayList<>();
            for (int i = 0; i < request.getImages().size(); i++) {
                String base64 = request.getImages().get(i);
                if (base64 == null || base64.isBlank()) {
                    log.warn("图片内容为空，跳过压缩: index={}", i);
                    continue;
                }

                try {
                    int originalLen = base64.length();
                    String compressed = ImageCompressUtils.compressBase64Image(base64);
                    if (compressed == null || compressed.isBlank()) {
                        log.warn("图片压缩结果为空，回退原图: index={}, originalLen={}", i, originalLen);
                        compressedImages.add(base64);
                        continue;
                    }

                    compressedImages.add(compressed);
                    log.info("图片压缩完成: index={}, originalBase64Len={}, compressedBase64Len={}, savedRatio={}%, hasChange={}",
                            i,
                            originalLen,
                            compressed.length(),
                            String.format("%.1f", compressed.length() * 100.0 / originalLen),
                            !compressed.equals(base64));
                } catch (Exception e) {
                    log.warn("图片压缩失败，回退原图: index={}, err={}", i, e.getMessage(), e);
                    compressedImages.add(base64);
                }
            }
            request.setImages(compressedImages);
        }

        // 创建Task
        Task task = new Task();
        task.setUserId(userId);
        task.setEssayTitle(request.getEssayTitle());
        task.setEssayContent(request.getEssayContent() != null ? request.getEssayContent() : null);
        task.setGradeLevel(request.getGradeLevel());
        task.setRequirements(request.getRequirements());
        
        // 处理图片
        boolean hasImages = request.getImages() != null && !request.getImages().isEmpty();
        task.setHasImages(hasImages);
        if (hasImages) {
            // 将图片列表转为JSON存储
            task.setImagesJson(cn.hutool.json.JSONUtil.toJsonStr(request.getImages()));
            task.setImageCount(request.getImages().size());
        }
        
        taskMapper.insert(task);

        // 随机选择两个模型
        List<Model> activeModels = modelMapper.selectList(
                new LambdaQueryWrapper<Model>().eq(Model::getStatus, "active")
        );

        // 如果有图片，筛选支持图片输入的模型
        if (hasImages) {
            activeModels = new ArrayList<>(activeModels.stream()
                    .filter(Model::supportsImageInput)
                    .toList());
        }

        if (activeModels.size() < 2) {
            String msg = hasImages ? "支持图片输入的模型不足" : "可用模型不足";
            throw new BusinessException(msg);
        }

        // 使用ELO匹配服务选择两个模型
        MatchResultVO matchResult = eloMatchService.matchModels(activeModels);
        Model modelA = matchResult.getModelA();
        Model modelB = matchResult.getModelB();
        List<Model> fallbackModels = buildFallbackModels(activeModels, modelA, modelB);

        // 创建Battle
        Battle battle = new Battle();
        battle.setTaskId(task.getId());
        battle.setModelAId(modelA.getId());
        battle.setModelBId(modelB.getId());
        battle.setDisplayOrder("normal");
        battle.setStatus("generating");
        battle.setMatchType(matchResult.getMatchType()); // 使用匹配类型：elo, elo_expanded, random

        battleMapper.insert(battle);

        // 更新统计计数器：总对战数、今日对战数
        cacheService.increment(CacheService.STATS_TOTAL_BATTLES);
        cacheService.increment(CacheService.STATS_DAILY_BATTLES);

        cacheService.set(getFallbackKey(battle.getId()), fallbackModels, CacheService.TTL_SHORT);

        log.info("创建对战: battleId={}, modelA={}, modelB={}, matchType={}, eloDiff={}, hasImages={}, fallbackCount={}, userTodayCount={}", 
                battle.getId(), modelA.getName(), modelB.getName(), matchResult.getMatchType(),
                matchResult.getEloDiff(), hasImages, fallbackModels.size(), battleCount);
        return battle.getId();
    }

    @Override
    @Transactional
    public BattleVO generateBattle(Long battleId) {
        Battle battle = battleMapper.selectById(battleId);
        if (battle == null) {
            throw new BusinessException("对战不存在");
        }
        if (!"generating".equals(battle.getStatus())) {
            throw new BusinessException("状态不正确");
        }

        Task task = taskMapper.selectById(battle.getTaskId());
        if (task == null) {
            throw new BusinessException("对战任务不存在");
        }

        Model modelA = modelMapper.selectById(battle.getModelAId());
        Model modelB = modelMapper.selectById(battle.getModelBId());
        if (modelA == null || modelB == null) {
            throw new BusinessException("参与对战的模型不存在");
        }

        if (task.getImagesJson() != null && !task.getImagesJson().isEmpty()) {
            List<String> images = cn.hutool.json.JSONUtil.toList(task.getImagesJson(), String.class);
            task.setImageBase64List(images);
        }

        List<Model> fallbackModels = cacheService.getOrLoad(getFallbackKey(battleId), CacheService.TTL_SHORT, ArrayList::new);
        SlotResponses slotResponses = callBothSlotsInParallel(modelA, modelB, fallbackModels, task, battleId);
        String responseA = slotResponses.responseA();
        String responseB = slotResponses.responseB();

        battle.setResponseA(responseA);
        battle.setResponseB(responseB);
        battle.setStatus("ready");
        battle.setUpdatedAt(LocalDateTime.now());
        battleMapper.updateById(battle);
        cacheService.delete(getFallbackKey(battleId));

        return buildBattleVO(battle);
    }

    private SlotResponses callBothSlotsInParallel(Model modelA, Model modelB, List<Model> fallbackModels, Task task, Long battleId) {
        long parallelStartNs = System.nanoTime();
        Future<SlotCallResult> slotAFuture = executor.submit(() -> callSlotWithTiming("A", modelA, fallbackModels, task, battleId));
        Future<SlotCallResult> slotBFuture = executor.submit(() -> callSlotWithTiming("B", modelB, fallbackModels, task, battleId));
        try {
            SlotCallResult slotAResult = slotAFuture.get();
            SlotCallResult slotBResult = slotBFuture.get();
            long totalCostMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - parallelStartNs);
            log.info("并行模型调用完成: battleId={}, totalCostMs={}, slotACostMs={}, slotBCostMs={}",
                    battleId, totalCostMs, slotAResult.costMs(), slotBResult.costMs());
            return new SlotResponses(slotAResult.response(), slotBResult.response());
        } catch (InterruptedException e) {
            slotAFuture.cancel(true);
            slotBFuture.cancel(true);
            Thread.currentThread().interrupt();
            log.error("并行生成被中断: battleId={}", battleId, e);
            throw new BusinessException("模型生成失败，请稍后重试");
        } catch (ExecutionException e) {
            slotAFuture.cancel(true);
            slotBFuture.cancel(true);
            log.error("并行生成失败: battleId={}, message={}", battleId, e.getCause() != null ? e.getCause().getMessage() : e.getMessage(), e);
            throw new BusinessException("模型生成失败，请稍后重试");
        }
    }

    private SlotCallResult callSlotWithTiming(String slotName, Model model, List<Model> fallbackModels, Task task, Long battleId) {
        long slotStartNs = System.nanoTime();
        String response = callModelSyncWithFallback(slotName, model, fallbackModels, task, battleId);
        long costMs = TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - slotStartNs);
        return new SlotCallResult(response, costMs);
    }

    private String getFallbackKey(Long battleId) {
        return "edu_arena:battle:fallback:" + battleId;
    }

    private List<Model> buildFallbackModels(List<Model> activeModels, Model modelA, Model modelB) {
        List<Model> fallbackModels = new ArrayList<>();
        for (Model model : activeModels) {
            if (model == null || model.getId() == null) {
                continue;
            }
            if (model.getId().equals(modelA.getId()) || model.getId().equals(modelB.getId())) {
                continue;
            }
            fallbackModels.add(model);
            if (fallbackModels.size() >= FALLBACK_MODEL_COUNT) {
                break;
            }
        }
        return fallbackModels;
    }

    private String callModelSyncWithFallback(String slotName, Model model, List<Model> fallbackModels, Task task, Long battleId) {
        List<Model> candidates = new ArrayList<>();
        candidates.add(model);
        if (fallbackModels != null) {
            candidates.addAll(fallbackModels);
        }
        for (int i = 0; i < candidates.size(); i++) {
            Model candidate = candidates.get(i);
            try {
                log.info("[槽位{}] 同步调用模型: battleId={}, modelId={}, attempt={}", slotName, battleId, candidate.getModelId(), i + 1);
                String result = aiClient.generate(candidate.getModelId(), task);
                if (result != null && !result.isBlank()) {
                    return result;
                }
                log.warn("[槽位{}] 模型返回空内容: battleId={}, modelId={}", slotName, battleId, candidate.getModelId());
            } catch (Exception e) {
                log.warn("[槽位{}] 模型调用失败: battleId={}, modelId={}, message={}", slotName, battleId, candidate.getModelId(), e.getMessage());
            }
        }
        throw new BusinessException("模型生成失败，请稍后重试");
    }

    private record SlotResponses(String responseA, String responseB) {
    }

    private record SlotCallResult(String response, long costMs) {
    }

    /**
     * 保存对战结果
     */
    private void saveBattleResult(Battle battle, String responseA, String responseB, String status) {
        try {
            battle.setResponseA(responseA);
            battle.setResponseB(responseB);
            battle.setStatus(status);
            battle.setUpdatedAt(LocalDateTime.now());
            battleMapper.updateById(battle);
            log.info("保存对战结果: battleId={}, status={}, lenA={}, lenB={}", 
                    battle.getId(), status, responseA.length(), responseB.length());
        } catch (Exception e) {
            log.error("保存对战结果失败: battleId={}", battle.getId(), e);
        }
    }

    @Override
    public BattleVO getBattleDetail(Long battleId) {
        // 尝试从缓存获取已完成的对战详情
        Battle battle = battleMapper.selectById(battleId);
        if (battle == null) {
            throw new BusinessException("对战不存在");
        }

        // 对于已完成的对战，使用缓存
        if ("ready".equals(battle.getStatus()) || "voted".equals(battle.getStatus())) {
            return cacheService.getOrLoad(
                    cacheService.getBattleKey(battleId),
                    CacheService.TTL_SHORT,
                    () -> buildBattleVO(battle)
            );
        }

        // 生成中的对战不缓存，实时查询
        return buildBattleVO(battle);
    }

    /**
     * 构建对战详情VO
     */
    private BattleVO buildBattleVO(Battle battle) {
        Task task = taskMapper.selectById(battle.getTaskId());
        if (task == null) {
            throw new BusinessException("对战任务不存在");
        }
        
        Model modelA = modelMapper.selectById(battle.getModelAId());
        Model modelB = modelMapper.selectById(battle.getModelBId());

        BattleVO vo = new BattleVO();
        vo.setBattleId(battle.getId());
        vo.setStatus(battle.getStatus());
        vo.setEssayTitle(task.getEssayTitle());
        vo.setEssayContent(task.getEssayContent());
        vo.setGradeLevel(task.getGradeLevel());
        vo.setRequirements(task.getRequirements());
        
        // 解析图片数据
        if (task.getImagesJson() != null && !task.getImagesJson().isEmpty()) {
            try {
                List<String> images = cn.hutool.json.JSONUtil.toList(task.getImagesJson(), String.class);
                vo.setImages(images);
            } catch (Exception e) {
                log.warn("解析图片数据失败: battleId={}", battle.getId());
            }
        }

        if ("ready".equals(battle.getStatus()) || "voted".equals(battle.getStatus())) {
            // 根据显示顺序设置左右响应
            if ("swapped".equals(battle.getDisplayOrder())) {
                vo.setResponseLeft(battle.getResponseB());
                vo.setResponseRight(battle.getResponseA());
                vo.setModelLeft(createModelVO(modelB));
                vo.setModelRight(createModelVO(modelA));
                // winner也需要转换：A->right, B->left
                if ("A".equals(battle.getWinner())) {
                    vo.setWinner("right");
                } else if ("B".equals(battle.getWinner())) {
                    vo.setWinner("left");
                } else {
                    vo.setWinner(battle.getWinner()); // tie 或 null
                }
            } else {
                vo.setResponseLeft(battle.getResponseA());
                vo.setResponseRight(battle.getResponseB());
                vo.setModelLeft(createModelVO(modelA));
                vo.setModelRight(createModelVO(modelB));
                // 正常顺序：A->left, B->right
                if ("A".equals(battle.getWinner())) {
                    vo.setWinner("left");
                } else if ("B".equals(battle.getWinner())) {
                    vo.setWinner("right");
                } else {
                    vo.setWinner(battle.getWinner()); // tie 或 null
                }
            }
        }

        return vo;
    }

    private ModelSimpleVO createModelVO(Model model) {
        ModelSimpleVO vo = new ModelSimpleVO();
        if (model != null) {
            vo.setName(model.getName());
            vo.setCompany(model.getCompany());
        } else {
            vo.setName("未知模型");
            vo.setCompany("");
        }
        return vo;
    }

    @Override
    @Transactional
    public VoteResultVO vote(Long userId, Long battleId, VoteRequest request) {
        Battle battle = battleMapper.selectById(battleId);
        if (battle == null) {
            throw new BusinessException("对战不存在");
        }

        if (!"ready".equals(battle.getStatus()) && !"voted".equals(battle.getStatus())) {
            throw new BusinessException("无法投票，当前状态: " + battle.getStatus());
        }

        // 转换投票结果
        String dimTheme = convertVote(request.getDimTheme(), battle.getDisplayOrder());
        String dimImagination = convertVote(request.getDimImagination(), battle.getDisplayOrder());
        String dimLogic = convertVote(request.getDimLogic(), battle.getDisplayOrder());
        String dimLanguage = convertVote(request.getDimLanguage(), battle.getDisplayOrder());
        String dimWriting = convertVote(request.getDimWriting(), battle.getDisplayOrder());

        // 计算总体获胜方
        int aWins = countWins(dimTheme, dimImagination, dimLogic, dimLanguage, dimWriting);
        int bWins = 5 - aWins - countTies(dimTheme, dimImagination, dimLogic, dimLanguage, dimWriting);
        String winner = aWins > bWins ? "A" : (bWins > aWins ? "B" : "tie");

        // 计算ELO变化 - 使用悲观锁查询模型，防止并发更新
        Model modelA = modelMapper.selectById(battle.getModelAId());
        Model modelB = modelMapper.selectById(battle.getModelBId());
        
        if (modelA == null || modelB == null) {
            throw new BusinessException("参与对战的模型不存在，可能已被删除");
        }

        BigDecimal[] newElos = EloCalculator.calculate(modelA.getEloScore(), modelB.getEloScore(), winner);

        // 保存投票
        Vote vote = new Vote();
        vote.setBattleId(battleId);
        vote.setUserId(userId);
        vote.setWinner(winner);
        vote.setDimTheme(dimTheme);
        vote.setDimImagination(dimImagination);
        vote.setDimLogic(dimLogic);
        vote.setDimLanguage(dimLanguage);
        vote.setDimWriting(dimWriting);
        vote.setDimThemeReason(request.getDimThemeReason());
        vote.setDimImaginationReason(request.getDimImaginationReason());
        vote.setDimLogicReason(request.getDimLogicReason());
        vote.setDimLanguageReason(request.getDimLanguageReason());
        vote.setDimWritingReason(request.getDimWritingReason());
        vote.setVoteTime(request.getVoteTime());
        vote.setEloABefore(modelA.getEloScore());
        vote.setEloBBefore(modelB.getEloScore());
        vote.setEloAAfter(newElos[0]);
        vote.setEloBAfter(newElos[1]);

        try {
            voteMapper.insert(vote);
        } catch (DuplicateKeyException e) {
            // 捕获唯一约束冲突，说明该用户已投过票
            throw new BusinessException("您已对此对战投过票");
        }

        // 更新模型ELO（基于当前数据库值计算，避免并发问题）
        int updatedA = modelMapper.updateEloAndStats(modelA.getId(), newElos[0], winner.equals("A"), winner.equals("tie"));
        int updatedB = modelMapper.updateEloAndStats(modelB.getId(), newElos[1], winner.equals("B"), winner.equals("tie"));
        
        if (updatedA == 0 || updatedB == 0) {
            log.error("ELO更新失败: modelAId={}, modelBId={}", modelA.getId(), modelB.getId());
            throw new BusinessException("ELO更新失败，请重试");
        }

        // 记录ELO历史
        saveEloHistory(modelA.getId(), newElos[0], battleId);
        saveEloHistory(modelB.getId(), newElos[1], battleId);

        // 更新battle状态和获胜方
        battle.setStatus("voted");
        battle.setWinner(winner);
        battleMapper.updateById(battle);

        // 更新统计计数器：总投票数
        cacheService.increment(CacheService.STATS_TOTAL_VOTES);

        // 清除相关缓存
        cacheService.invalidateBattle(battleId);
        cacheService.invalidateModelDetail(modelA.getId());
        cacheService.invalidateModelDetail(modelB.getId());
        cacheService.invalidateLeaderboard();

        log.info("投票成功: battleId={}, winner={}, eloA={}->{}, eloB={}->{}", 
                battleId, winner, vote.getEloABefore(), newElos[0], vote.getEloBBefore(), newElos[1]);

        VoteResultVO result = new VoteResultVO();
        result.setMessage("投票成功");
        result.setOverallWinner(winner);
        result.setAWins(aWins);
        result.setBWins(bWins);
        if ("A".equals(winner)) {
            result.setWinnerSide("swapped".equals(battle.getDisplayOrder()) ? "right" : "left");
        } else if ("B".equals(winner)) {
            result.setWinnerSide("swapped".equals(battle.getDisplayOrder()) ? "left" : "right");
        } else {
            result.setWinnerSide("tie");
        }
        result.setWinnerLabel("A".equals(winner) ? "A方" : "B".equals(winner) ? "B方" : "平局");
        if ("swapped".equals(battle.getDisplayOrder())) {
            result.setLeftModelSlot("B");
            result.setRightModelSlot("A");
        } else {
            result.setLeftModelSlot("A");
            result.setRightModelSlot("B");
        }
        result.setEloABefore(vote.getEloABefore());
        result.setEloAAfter(vote.getEloAAfter());
        result.setEloBBefore(vote.getEloBBefore());
        result.setEloBAfter(vote.getEloBAfter());

        return result;
    }

    /**
     * 保存ELO历史记录
     */
    private void saveEloHistory(Long modelId, BigDecimal eloScore, Long battleId) {
        try {
            EloHistory history = new EloHistory();
            history.setModelId(modelId);
            history.setEloScore(eloScore);
            history.setBattleId(battleId);
            eloHistoryMapper.insert(history);
            log.debug("保存ELO历史: modelId={}, elo={}, battleId={}", modelId, eloScore, battleId);
        } catch (Exception e) {
            log.error("保存ELO历史失败: modelId={}, battleId={}", modelId, battleId, e);
        }
    }

    private String convertVote(String vote, String displayOrder) {
        if ("tie".equals(vote)) {
            return "tie";
        }
        boolean isSwapped = "swapped".equals(displayOrder);
        if ("left".equals(vote)) {
            return isSwapped ? "B" : "A";
        } else {
            return isSwapped ? "A" : "B";
        }
    }

    private int countWins(String... dims) {
        int count = 0;
        for (String dim : dims) {
            if ("A".equals(dim)) count++;
        }
        return count;
    }

    private int countTies(String... dims) {
        int count = 0;
        for (String dim : dims) {
            if ("tie".equals(dim)) count++;
        }
        return count;
    }

    @Override
    public IPage<BattleHistoryVO> getBattleHistory(int page, int size) {
        return battleMapper.selectHistoryPage(new Page<>(page, size));
    }

}
