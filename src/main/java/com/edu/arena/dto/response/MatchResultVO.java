package com.edu.arena.dto.response;

import com.edu.arena.entity.Model;
import lombok.Data;

import java.math.BigDecimal;

/**
 * ELO匹配结果
 */
@Data
public class MatchResultVO {

    /**
     * 模型A（基准模型）
     */
    private Model modelA;

    /**
     * 模型B（匹配的对手）
     */
    private Model modelB;

    /**
     * 匹配类型: elo(基于ELO匹配), random(纯随机)
     */
    private String matchType;

    /**
     * ELO分差（绝对值）
     */
    private Integer eloDiff;

    /**
     * 候选池大小（用于调试/分析）
     */
    private Integer candidatePoolSize;

    /**
     * 创建成功匹配结果
     */
    public static MatchResultVO of(Model modelA, Model modelB, String matchType, int candidatePoolSize) {
        MatchResultVO result = new MatchResultVO();
        result.setModelA(modelA);
        result.setModelB(modelB);
        result.setMatchType(matchType);
        result.setEloDiff(Math.abs(modelA.getEloScore().subtract(modelB.getEloScore()).intValue()));
        result.setCandidatePoolSize(candidatePoolSize);
        return result;
    }
}
