package com.edu.arena.entity;

import com.baomidou.mybatisplus.annotation.*;
import lombok.Data;
import lombok.ToString;

import java.time.LocalDateTime;
import java.util.List;

/**
 * 任务实体(作文题目)
 */
@Data
@TableName("tasks")
public class Task {

    @TableId(type = IdType.AUTO)
    private Long id;

    /**
     * 用户ID
     */
    private Long userId;

    /**
     * 作文题目
     */
    private String essayTitle;

    /**
     * 作文内容
     */
    private String essayContent;

    /**
     * 年级
     */
    private String gradeLevel;

    /**
     * 批改要求
     */
    private String requirements;

    /**
     * 是否有图片
     */
    private Boolean hasImages;

    /**
     * 图片Base64列表(JSON数组格式存储)
     */
    @ToString.Exclude
    private String imagesJson;

    /**
     * 图片数量
     */
    private Integer imageCount;

    /**
     * 创建时间
     */
    @TableField(fill = FieldFill.INSERT)
    private LocalDateTime createdAt;

    // ========== 非数据库字段 ==========

    /**
     * 图片Base64列表(运行时使用，从imagesJson解析)
     * 图片大小限制：单张不超过20MB
     * 支持格式：PNG, JPEG, WEBP
     */
    @TableField(exist = false)
    @ToString.Exclude
    private List<String> imageBase64List;

}
