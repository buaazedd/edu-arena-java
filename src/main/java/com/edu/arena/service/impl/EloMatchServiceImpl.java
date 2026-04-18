package com.edu.arena.service.impl;

import com.edu.arena.dto.response.MatchResultVO;
import com.edu.arena.entity.Model;
import com.edu.arena.mapper.BattleMapper;
import com.edu.arena.service.EloMatchService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.util.*;
import java.util.stream.Collectors;

/**
 * ELO匹配服务实现
 * 
 * 匹配策略：
 * 1. 筛选ELO在±100范围内的候选池
 * 2. 排除最近N场对战中已配对过的模型组合
 * 3. 按ELO差值加权随机选择（差值越小，权重越高）
 * 4. 若候选池为空，扩大范围或回退到纯随机
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class EloMatchServiceImpl implements EloMatchService {

    private final BattleMapper battleMapper;

    /** ELO匹配初始范围 */
    private static final int INITIAL_ELO_RANGE = 100;
    
    /** ELO匹配第一次扩大范围 */
    private static final int EXPANDED_ELO_RANGE_1 = 200;
    
    /** ELO匹配第二次扩大范围 */
    private static final int EXPANDED_ELO_RANGE_2 = 500;
    
    /** 历史避让：查询最近多少场对战的配对记录 */
    private static final int RECENT_BATTLE_LIMIT = 50;

    @Override
    public MatchResultVO matchModels(List<Model> candidateModels) {
        if (candidateModels == null || candidateModels.size() < 2) {
            throw new IllegalArgumentException("候选模型数量不足，至少需要2个模型");
        }

        // Step 1: 随机选择一个基准模型
        Collections.shuffle(candidateModels);
        Model baseModel = candidateModels.get(0);
        
        log.debug("开始ELO匹配: baseModel={}, elo={}", baseModel.getName(), baseModel.getEloScore());

        // Step 2: 尝试在不同范围内匹配
        MatchResultVO result = tryMatchWithRange(candidateModels, baseModel, INITIAL_ELO_RANGE);
        if (result != null) {
            return result;
        }

        // 扩大范围到200
        result = tryMatchWithRange(candidateModels, baseModel, EXPANDED_ELO_RANGE_1);
        if (result != null) {
            log.info("ELO匹配扩大范围成功: range=±{}", EXPANDED_ELO_RANGE_1);
            return result;
        }

        // 扩大范围到500
        result = tryMatchWithRange(candidateModels, baseModel, EXPANDED_ELO_RANGE_2);
        if (result != null) {
            log.info("ELO匹配扩大范围成功: range=±{}", EXPANDED_ELO_RANGE_2);
            return result;
        }

        // Step 3: 回退到纯随机
        log.warn("ELO匹配失败，回退到纯随机匹配");
        return fallbackToRandom(candidateModels, baseModel);
    }

    /**
     * 在指定ELO范围内尝试匹配
     */
    private MatchResultVO tryMatchWithRange(List<Model> allModels, Model baseModel, int eloRange) {
        // 筛选ELO范围内的模型
        BigDecimal baseElo = baseModel.getEloScore();
        BigDecimal minElo = baseElo.subtract(BigDecimal.valueOf(eloRange));
        BigDecimal maxElo = baseElo.add(BigDecimal.valueOf(eloRange));

        List<Model> eloCandidates = allModels.stream()
                .filter(m -> !m.getId().equals(baseModel.getId())) // 排除自己
                .filter(m -> m.getEloScore().compareTo(minElo) >= 0 
                          && m.getEloScore().compareTo(maxElo) <= 0)
                .collect(Collectors.toList());

        if (eloCandidates.isEmpty()) {
            log.debug("ELO范围±{}内无候选模型", eloRange);
            return null;
        }

        // 排除最近配对过的模型
        List<Long> recentOpponents = getRecentOpponentIds(baseModel.getId(), RECENT_BATTLE_LIMIT);
        List<Model> filteredCandidates = eloCandidates.stream()
                .filter(m -> !recentOpponents.contains(m.getId()))
                .collect(Collectors.toList());

        // 如果过滤后为空，使用未过滤的候选池
        if (filteredCandidates.isEmpty()) {
            log.debug("排除历史配对后无候选模型，使用原始候选池");
            filteredCandidates = eloCandidates;
        }

        // 加权随机选择
        Model opponent = weightedRandomSelect(baseModel, filteredCandidates);
        if (opponent == null) {
            return null;
        }

        String matchType = eloRange == INITIAL_ELO_RANGE ? "elo" : "elo_expanded";
        log.info("ELO匹配成功: modelA={}, modelB={}, eloDiff={}, range=±{}", 
                baseModel.getName(), opponent.getName(),
                Math.abs(baseElo.subtract(opponent.getEloScore()).intValue()), eloRange);

        return MatchResultVO.of(baseModel, opponent, matchType, filteredCandidates.size());
    }

    /**
     * 加权随机选择
     * 权重 = 1 / (|elo_diff| + 1)
     */
    private Model weightedRandomSelect(Model baseModel, List<Model> candidates) {
        if (candidates.isEmpty()) {
            return null;
        }

        BigDecimal baseElo = baseModel.getEloScore();
        
        // 计算每个候选模型的权重
        List<Double> weights = candidates.stream()
                .map(m -> {
                    int eloDiff = Math.abs(baseElo.subtract(m.getEloScore()).intValue());
                    return 1.0 / (eloDiff + 1.0);
                })
                .collect(Collectors.toList());

        // 计算总权重
        double totalWeight = weights.stream().mapToDouble(Double::doubleValue).sum();
        
        // 随机选择
        double random = Math.random() * totalWeight;
        double cumulative = 0.0;
        
        for (int i = 0; i < candidates.size(); i++) {
            cumulative += weights.get(i);
            if (random <= cumulative) {
                return candidates.get(i);
            }
        }

        // 理论上不会走到这里，返回最后一个
        return candidates.get(candidates.size() - 1);
    }

    /**
     * 回退到纯随机匹配
     */
    private MatchResultVO fallbackToRandom(List<Model> allModels, Model baseModel) {
        // 排除自己
        List<Model> candidates = allModels.stream()
                .filter(m -> !m.getId().equals(baseModel.getId()))
                .collect(Collectors.toList());

        if (candidates.isEmpty()) {
            throw new IllegalStateException("无法找到可匹配的模型");
        }

        // 纯随机选择
        Collections.shuffle(candidates);
        Model opponent = candidates.get(0);

        log.info("纯随机匹配: modelA={}, modelB={}", baseModel.getName(), opponent.getName());

        return MatchResultVO.of(baseModel, opponent, "random", candidates.size());
    }

    @Override
    public List<Long> getRecentOpponentIds(Long modelId, int limit) {
        if (modelId == null) {
            return Collections.emptyList();
        }
        return battleMapper.selectRecentOpponentIds(modelId, limit);
    }
}
