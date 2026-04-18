package com.edu.arena.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;

import java.time.LocalDateTime;

/**
 * 对战实体
 */
@Data
@TableName("battles")
public class Battle {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 任务ID
     */
    private Long taskId;

    /**
     * 模型A ID
     */
    private Long modelAId;

    /**
     * 模型B ID
     */
    private Long modelBId;

    /**
     * 显示顺序: normal, swapped
     */
    private String displayOrder;

    /**
     * 状态: generating, ready, voted, failed
     */
    private String status;

    /**
     * 比赛类型
     */
    private String matchType;

    /**
     * 模型A响应
     */
    private String responseA;

    /**
     * 模型B响应
     */
    private String responseB;

    /**
     * 错误信息
     */
    private String errorMessage;

    /**
     * 获胜方: A, B, tie
     */
    private String winner;

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

    // ========== 非数据库字段 ==========

    /**
     * 关联任务
     */
    @TableField(exist = false)
    private Task task;

    /**
     * 模型A
     */
    @TableField(exist = false)
    private Model modelA;

    /**
     * 模型B
     */
    @TableField(exist = false)
    private Model modelB;

}
