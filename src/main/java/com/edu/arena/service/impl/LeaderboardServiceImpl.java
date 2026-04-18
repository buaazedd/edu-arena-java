package com.edu.arena.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.edu.arena.common.cache.CacheService;
import com.edu.arena.dto.response.LeaderboardVO;
import com.edu.arena.entity.EloHistory;
import com.edu.arena.entity.Model;
import com.edu.arena.mapper.EloHistoryMapper;
import com.edu.arena.mapper.ModelMapper;
import com.edu.arena.service.LeaderboardService;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

/**
 * Leaderboard Service Implementation
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class LeaderboardServiceImpl implements LeaderboardService {

    private final ModelMapper modelMapper;
    private final EloHistoryMapper eloHistoryMapper;
    private final CacheService cacheService;

    @Override
    @SuppressWarnings("unchecked")
    public List<LeaderboardVO> getLeaderboard() {
        return cacheService.getOrLoad(
                CacheService.LEADERBOARD_KEY,
                CacheService.TTL_MEDIUM,
                () -> {
                    log.debug("Leaderboard cache miss, querying database");
                    long start = System.currentTimeMillis();

                    List<Model> models = modelMapper.selectList(
                            new LambdaQueryWrapper<Model>()
                                    .eq(Model::getStatus, "active")
                                    .orderByDesc(Model::getEloScore)
                    );

                    List<LeaderboardVO> result = new ArrayList<>();
                    for (int i = 0; i < models.size(); i++) {
                        Model m = models.get(i);
                        LeaderboardVO vo = new LeaderboardVO();
                        vo.setRank(i + 1);
                        vo.setId(m.getId());
                        vo.setName(m.getName());
                        vo.setCompany(m.getCompany());
                        vo.setEloScore(m.getEloScore());
                        vo.setTotalMatches(m.getTotalMatches());
                        vo.setWinCount(m.getWinCount());
                        vo.setLoseCount(m.getLoseCount());
                        vo.setTieCount(m.getTieCount());

                        if (m.getTotalMatches() > 0) {
                            vo.setWinRate(BigDecimal.valueOf(m.getWinCount() * 100.0 / m.getTotalMatches())
                                    .setScale(1, RoundingMode.HALF_UP));
                        } else {
                            vo.setWinRate(BigDecimal.ZERO);
                        }

                        // 模型详情字段
                        vo.setModelId(m.getModelId());
                        vo.setDescription(m.getDescription());
                        vo.setInputModalities(m.getInputModalities());
                        vo.setFeatures(m.getFeatures());
                        vo.setContextLength(m.getContextLength());
                        vo.setMaxOutput(m.getMaxOutput());
                        vo.setInputPrice(m.getInputPrice());
                        vo.setOutputPrice(m.getOutputPrice());
                        vo.setIsNew(m.getIsNew());

                        result.add(vo);
                    }

                    log.debug("Leaderboard query took {}ms", System.currentTimeMillis() - start);
                    return result;
                }
        );
    }

    @Override
    public void refreshCache() {
        cacheService.invalidateLeaderboard();
        log.info("Leaderboard cache refreshed");
    }

    @Override
    @SuppressWarnings("unchecked")
    public Map<String, List<Map<String, Object>>> getEloHistory() {
        return cacheService.getOrLoad(
                CacheService.ELO_HISTORY_KEY,
                CacheService.TTL_MEDIUM,
                () -> {
                    log.debug("ELO history cache miss, querying database");
                    Map<String, List<Map<String, Object>>> history = new HashMap<>();

                    List<Model> models = modelMapper.selectList(
                            new LambdaQueryWrapper<Model>()
                                    .eq(Model::getStatus, "active")
                                    .orderByDesc(Model::getEloScore)
                                    .last("LIMIT 10")
                    );

                    if (models.isEmpty()) {
                        return history;
                    }

                    Map<Long, String> modelNameMap = new HashMap<>();
                    for (Model model : models) {
                        modelNameMap.put(model.getId(), model.getName());
                        history.put(model.getName(), new ArrayList<>());
                    }

                    List<EloHistory> records = eloHistoryMapper.selectList(
                            new LambdaQueryWrapper<EloHistory>()
                                    .in(EloHistory::getModelId, modelNameMap.keySet())
                                    .orderByAsc(EloHistory::getBattleId)
                                    .orderByAsc(EloHistory::getRecordedAt)
                    );

                    for (EloHistory record : records) {
                        String modelName = modelNameMap.get(record.getModelId());
                        if (modelName == null) {
                            continue;
                        }

                        Map<String, Object> point = new HashMap<>();
                        point.put("score", record.getEloScore());
                        point.put("battle_id", record.getBattleId());
                        point.put("time", record.getRecordedAt());
                        history.get(modelName).add(point);
                    }

                    return history;
                }
        );
    }

}
