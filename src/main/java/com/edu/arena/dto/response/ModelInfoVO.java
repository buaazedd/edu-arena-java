package com.edu.arena.dto.response;

import lombok.Data;

import java.math.BigDecimal;

/**
 * 模型平台API返回的模型信息
 */
@Data
public class ModelInfoVO {

    private String modelId;

    private String modelName;

    private String desc;

    private String types;

    private String features;

    private String inputModalities;

    private Integer contextLength;

    private Integer maxOutput;

    private Pricing pricing;

    @Data
    public static class Pricing {
        private BigDecimal input;
        private BigDecimal output;
        private BigDecimal cacheRead;
        private BigDecimal cacheWrite;
    }

}
