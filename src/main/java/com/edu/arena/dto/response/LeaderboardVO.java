package com.edu.arena.dto.response;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 排行榜项
 */
@Data
public class LeaderboardVO {

    private Integer rank;
    private Long id;
    private String name;
    private String company;
    private BigDecimal eloScore;
    private Integer totalMatches;
    private Integer winCount;
    private Integer loseCount;
    private Integer tieCount;
    private BigDecimal winRate;
    
    // 模型详情字段
    private String modelId;
    private String description;
    private String inputModalities;
    private String features;
    private Integer contextLength;
    private Integer maxOutput;
    private BigDecimal inputPrice;
    private BigDecimal outputPrice;
    private Boolean isNew;

}
