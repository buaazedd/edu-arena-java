package com.edu.arena.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.math.BigDecimal;
import java.time.LocalDateTime;

/**
 * ELO历史记录
 */
@Data
@TableName("elo_history")
public class EloHistory {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 模型ID
     */
    private Long modelId;

    /**
     * ELO分数
     */
    private BigDecimal eloScore;

    /**
     * 对战ID
     */
    private Long battleId;

    /**
     * 记录时间
     */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime recordedAt;

    /**
     * 关联模型
     */
    @TableField(exist = false)
    private Model model;

}
