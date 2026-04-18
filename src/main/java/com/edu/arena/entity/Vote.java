package com.edu.arena.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * 投票实体
 */
@Data
@TableName("votes")
public class Vote {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 对战ID
     */
    private Long battleId;

    /**
     * 用户ID
     */
    private Long userId;

    /**
     * 总体获胜方: A, B, tie
     */
    private String winner;

    /**
     * 主旨维度: A, B, tie
     */
    private String dimTheme;

    /**
     * 想象维度
     */
    private String dimImagination;

    /**
     * 逻辑维度
     */
    private String dimLogic;

    /**
     * 语言维度
     */
    private String dimLanguage;

    /**
     * 书写维度
     */
    private String dimWriting;

    /**
     * 主旨维度评分理由
     */
    private String dimThemeReason;

    /**
     * 想象维度评分理由
     */
    private String dimImaginationReason;

    /**
     * 逻辑维度评分理由
     */
    private String dimLogicReason;

    /**
     * 语言维度评分理由
     */
    private String dimLanguageReason;

    /**
     * 书写维度评分理由
     */
    private String dimWritingReason;

    /**
     * 投票耗时(秒)
     */
    private Double voteTime;

    /**
     * 模型A投票前ELO
     */
    private BigDecimal eloABefore;

    /**
     * 模型B投票前ELO
     */
    private BigDecimal eloBBefore;

    /**
     * 模型A投票后ELO
     */
    private BigDecimal eloAAfter;

    /**
     * 模型B投票后ELO
     */
    private BigDecimal eloBAfter;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    // ========== 非数据库字段 ==========

    /**
     * 关联对战
     */
    @TableField(exist = false)
    private Battle battle;

    /**
     * 关联用户
     */
    @TableField(exist = false)
    private User user;

}
