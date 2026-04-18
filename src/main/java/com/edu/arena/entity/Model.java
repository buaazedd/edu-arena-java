package com.edu.arena.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * AI模型实体
 */
@Data
@TableName("models")
public class Model {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 模型ID(调用API用)
     */
    private String modelId;

    /**
     * 模型名称
     */
    private String name;

    /**
     * 所属公司
     */
    private String company;

    /**
     * ELO分数
     */
    private BigDecimal eloScore = new BigDecimal("1500");

    /**
     * 总比赛场次
     */
    private Integer totalMatches = 0;

    /**
     * 胜场
     */
    private Integer winCount = 0;

    /**
     * 负场
     */
    private Integer loseCount = 0;

    /**
     * 平局场数
     */
    private Integer tieCount = 0;

    /**
     * 状态: active, inactive
     */
    private String status;

    /**
     * 是否新模型
     */
    private Boolean isNew;

    /**
     * 定位是否完成
     */
    private Boolean positioningDone;

    /**
     * 模型描述
     */
    private String description;

    /**
     * 输入模态: text,image,audio,video
     */
    private String inputModalities;

    /**
     * 功能特性: thinking,tools,function_calling等
     */
    private String features;

    /**
     * 上下文长度
     */
    private Integer contextLength;

    /**
     * 判断模型是否支持图片输入
     */
    public boolean supportsImageInput() {
        return inputModalities != null && inputModalities.contains("image");
    }

    /**
     * 最大输出Token
     */
    private Integer maxOutput;

    /**
     * 输入价格(每1K Token)
     */
    private BigDecimal inputPrice;

    /**
     * 输出价格(每1K Token)
     */
    private BigDecimal outputPrice;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    /**
     * 更新时间
     */
    @TableField(fill = FieldFill.INSERT_UPDATE)
    private LocalDateTime updatedAt;

}
